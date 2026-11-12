"""API REST FastAPI — Détection de fraude en flux (Projet N°6).

Préfixe /api/v1 ; Swagger sur /docs ; CORS activé pour l'origine du front-end.
Le front ne communique qu'avec cette API : aucune logique ML côté navigateur.
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from . import config
from .backends import BackendError, make_backend
from .model import ModelService
from .schemas import (
    AlertOut,
    BreakdownOut,
    HealthOut,
    LatencyOut,
    ModelInfoOut,
    PredictionOut,
    QueuedOut,
    StatsOut,
    StreamControlIn,
    StreamStatusOut,
    TimeseriesOut,
    TransactionIn,
)
from .utils import now_iso_ms, now_utc, parse_duration

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")

state: dict = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    state["started_at"] = time.time()
    model = ModelService(config.MODEL_PATH, config.MODEL_METADATA_PATH)
    model.load()
    state["model"] = model
    state["backend"] = make_backend()
    log.info(
        "API démarrée en mode %s | modèle=%s | seuil=%s",
        state["backend"].mode,
        model.version,
        model.threshold,
    )
    yield
    log.info("API arrêtée")


app = FastAPI(
    title="Fraud Detection Streaming API",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "API REST de supervision, prédiction unitaire et contrôle de la plateforme "
        "de détection de fraude en flux (Kafka → Spark → MongoDB)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api/v1")


@app.exception_handler(BackendError)
async def backend_error_handler(_req, exc: BackendError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


def _tx_dict(tx: TransactionIn) -> dict:
    data = tx.model_dump()
    data["transaction_id"] = data.get("transaction_id") or f"tx_{uuid.uuid4()}"
    # nameOrig/nameDest sont optionnels : on ne publie pas de clés nulles
    # (contrat Kafka : chaînes typées quand elles sont présentes).
    return {key: value for key, value in data.items() if value is not None}


def _window(value: str) -> int:
    try:
        seconds = parse_duration(value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if seconds <= 0:
        raise HTTPException(422, "window doit être strictement positif")
    return seconds


@router.get("/health", response_model=HealthOut, tags=["system"])
def health():
    model: ModelService = state["model"]
    backend = state["backend"]
    deps = backend.health()
    deps_ok = all(bool(deps.get(key)) for key in ("kafka_connected", "mongodb_connected"))
    # Si le pipeline accuse un retard important, le service est dégradé (pas de mensonge "healthy")
    pipeline_ok = bool(deps.get("pipeline_synced", True))
    healthy = bool(model.loaded and deps_ok and pipeline_ok)
    return HealthOut(
        status="healthy" if healthy else "degraded",
        mode=backend.mode,
        model_loaded=model.loaded,
        model_version=model.version,
        threshold=model.threshold,
        uptime_s=round(time.time() - state.get("started_at", time.time()), 2),
        **deps,
    )


@router.get("/model/info", response_model=ModelInfoOut, tags=["system"])
def model_info():
    return state["model"].info()


@router.post("/predict", response_model=PredictionOut, tags=["prediction"])
def predict(
    tx: TransactionIn,
    persist: bool = Query(False, description="Écrit dans MongoDB (source: api)"),
):
    """Prédiction synchrone en mémoire, sans Kafka.

    `persist=false` par défaut pour garantir P95 < 200 ms (SNF2). Avec
    `persist=true`, le document est écrit dans `transactions` (source: "api").
    """
    model: ModelService = state["model"]
    if not model.loaded:
        raise HTTPException(503, "Modèle non chargé")

    data = _tx_dict(tx)
    produced_at = now_utc()
    started = time.perf_counter()
    try:
        probability = model.predict_proba(data)
    except Exception as exc:
        log.exception("Erreur d'inférence")
        raise HTTPException(500, f"Erreur d'inférence : {exc}") from exc
    is_fraud = model.decide(probability)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    decision = "BLOCKED" if is_fraud else "ALLOWED"

    if persist:
        written_at = now_utc()
        doc = {
            **data,
            "_id": data["transaction_id"],
            "probability": probability,
            "threshold": model.threshold,
            "is_fraud": is_fraud,
            "decision": decision,
            "model_version": model.version,
            "produced_at": produced_at,
            "scored_at": written_at,
            "written_at": written_at,
            "pipeline_latency_ms": round(max(0.0, (written_at - produced_at).total_seconds() * 1000), 2),
            "source": "api",
        }
        state["backend"].persist_prediction(doc)

    return PredictionOut(
        transaction_id=data["transaction_id"],
        is_fraud=is_fraud,
        probability=round(probability, 6),
        decision=decision,
        threshold=model.threshold,
        model_version=model.version,
        latency_ms=latency_ms,
    )


@router.post("/transactions", response_model=QueuedOut, status_code=202, tags=["prediction"])
def post_transaction(tx: TransactionIn):
    """Publie la transaction dans Kafka (clé = transaction_id) pour traitement par Spark."""
    data = _tx_dict(tx)
    data["produced_at"] = now_iso_ms()
    state["backend"].publish(data)
    return QueuedOut(transaction_id=data["transaction_id"])


@router.get("/stats", response_model=StatsOut, tags=["stats"])
def stats():
    return state["backend"].stats()


@router.get("/stats/timeseries", response_model=TimeseriesOut, tags=["stats"])
def timeseries(
    window: str = Query("15m", description="Fenêtre temporelle (ex. 5m, 15m, 1h)"),
    bucket: str = Query("10s", description="Granularité demandée (ex. 10s, 30s, 1m)"),
):
    window_s = _window(window)
    bucket_s = _window(bucket)
    if bucket_s < config.STATS_BASE_BUCKET_SECONDS:
        raise HTTPException(
            422,
            f"bucket trop fin : la granularité minimale est {config.STATS_BASE_BUCKET_SECONDS}s "
            "(largeur des documents stats_buckets écrits par Spark)",
        )
    if window_s // bucket_s > 5000:
        raise HTTPException(422, "window/bucket incohérents (trop de points)")
    return {"bucket": bucket, "points": state["backend"].timeseries(window_s, bucket_s)}


@router.get("/stats/breakdown", response_model=BreakdownOut, tags=["stats"])
def breakdown(window: str = Query("15m", description="Fenêtre d'analyse (ex. 15m, 1h)")):
    window_s = _window(window)
    return {"window": window, "by_type": state["backend"].breakdown(window_s)}


@router.get("/stats/latency", response_model=LatencyOut, tags=["stats"])
def latency(window: str = Query("15m", description="Fenêtre d'analyse (ex. 15m, 1h)")):
    window_s = _window(window)
    payload = state["backend"].latency(window_s)
    return {"window": window, **payload}


@router.get("/alerts/latest", response_model=list[AlertOut], tags=["stats"])
def alerts_latest(limit: int = Query(20, ge=1, le=100)):
    return state["backend"].latest_alerts(limit)


@router.post("/stream/control", response_model=StreamStatusOut, tags=["simulator"])
def stream_control(cmd: StreamControlIn):
    return state["backend"].stream_control(cmd.model_dump(exclude_none=True))


@router.get("/stream/status", response_model=StreamStatusOut, tags=["simulator"])
def stream_status():
    return state["backend"].stream_status()


app.include_router(router)
