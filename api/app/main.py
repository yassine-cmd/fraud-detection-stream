"""API REST FastAPI — Détection de fraude en flux (Projet N°6).

Préfixe /api/v1 ; Swagger sur /docs ; CORS activé pour l'origine du front-end.
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .backends import BackendError, make_backend
from .model import ModelService
from .schemas import (AlertOut, HealthOut, PredictionOut, QueuedOut, StatsOut,
                      StreamControlIn, StreamStatusOut, TimeseriesOut, TransactionIn)
from .utils import now_iso_ms, parse_duration

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")

state = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    model = ModelService(config.MODEL_PATH)
    model.load()
    state["model"] = model
    state["backend"] = make_backend()
    log.info("API démarrée en mode %s", state["backend"].mode)
    yield


app = FastAPI(title="Fraud Detection API", version="1.0.0", lifespan=lifespan,
              description="Prédiction unitaire, injection Kafka, statistiques et contrôle du simulateur.")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

router = APIRouter(prefix="/api/v1")


@app.exception_handler(BackendError)
async def backend_error_handler(_req, exc: BackendError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def _tx_dict(tx: TransactionIn) -> dict:
    d = tx.model_dump()
    d["transaction_id"] = d["transaction_id"] or f"tx_{uuid.uuid4()}"
    return d


@router.get("/health", response_model=HealthOut, tags=["system"])
def health():
    model: ModelService = state["model"]
    backend = state["backend"]
    deps = backend.health()
    ok = model.loaded and all(v in ("up", "mock") for v in deps.values())
    return HealthOut(status="healthy" if ok else "degraded", mode=backend.mode,
                     model_loaded=model.loaded, model_version=model.version, **deps)


@router.post("/predict", response_model=PredictionOut, tags=["prediction"])
def predict(tx: TransactionIn, persist: bool = Query(False, description="Écrit dans MongoDB (source: api)")):
    """Prédiction synchrone en mémoire, sans Kafka. `persist=false` par défaut (P95 < 200 ms)."""
    model: ModelService = state["model"]
    if not model.loaded:
        raise HTTPException(503, "Modèle non chargé")
    t0 = time.perf_counter()
    d = _tx_dict(tx)
    prob = model.predict_proba(d)
    is_fraud = model.decide(prob)
    latency = round((time.perf_counter() - t0) * 1000, 2)
    out = PredictionOut(transaction_id=d["transaction_id"], is_fraud=is_fraud, probability=round(prob, 6),
                        decision="BLOCKED" if is_fraud else "ALLOWED", threshold=model.threshold,
                        model_version=model.version, latency_ms=latency)
    if persist:
        now = datetime.now(timezone.utc)
        doc = {**d, "_id": d["transaction_id"], "probability": prob, "threshold": model.threshold,
               "is_fraud": is_fraud, "decision": out.decision, "model_version": model.version,
               "produced_at": now_iso_ms(), "scored_at": now, "pipeline_latency_ms": None, "source": "api"}
        state["backend"].persist_prediction(doc)
    return out


@router.post("/transactions", response_model=QueuedOut, status_code=202, tags=["prediction"])
def post_transaction(tx: TransactionIn):
    """Publie la transaction dans Kafka (clé = transaction_id) pour traitement par Spark."""
    d = _tx_dict(tx)
    d["produced_at"] = now_iso_ms()
    state["backend"].publish(d)
    return QueuedOut(transaction_id=d["transaction_id"])


@router.get("/stats", response_model=StatsOut, tags=["stats"])
def stats():
    return state["backend"].stats()


@router.get("/stats/timeseries", response_model=TimeseriesOut, tags=["stats"])
def timeseries(window: str = Query("15m"), bucket: str = Query("10s")):
    try:
        w, b = parse_duration(window), parse_duration(bucket)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if b <= 0 or w <= 0 or w // b > 5000:
        raise HTTPException(422, "window/bucket incohérents (trop de points)")
    return {"bucket": bucket, "points": state["backend"].timeseries(w, b)}


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
