"""Chargement et inférence du pipeline `model.joblib`.

Le préprocessing fait partie du pipeline exporté par l'équipe ML : l'API lui
passe un DataFrame brut avec les colonnes `features` (float64), exactement
comme le job Spark via sa `pandas_udf`. Aucune transformation n'est dupliquée
côté API, ce qui garantit la parité des scores.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd

log = logging.getLogger("api.model")

DEFAULT_FEATURES = [
    "step",
    "type",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
]


def _resolve_model_path(path: str) -> str:
    """Tolère les différents contextes d'exécution (local, Docker, tests)."""
    candidates = [
        path,
        "ml/artifacts/model.joblib",
        "../ml/artifacts/model.joblib",
        "model/model.joblib",
        "api/model/model.joblib",
    ]
    for candidate in candidates:
        try:
            if Path(candidate).is_file():
                return candidate
        except OSError:
            continue
    return path


def _load_metadata(model_path: str, metadata_path: str = "") -> Dict[str, Any]:
    candidates: List[Path] = []
    if metadata_path:
        candidates.append(Path(metadata_path))
    model = Path(model_path)
    candidates.extend(
        [
            model.with_name("metadata.json"),
            model.parent.parent / "metadata.json",
        ]
    )
    for path in candidates:
        try:
            if path.is_file():
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    log.info("Métadonnées du modèle chargées depuis %s", path)
                    return data
        except (OSError, ValueError):
            log.warning("Métadonnées illisibles : %s", path, exc_info=True)
    return {}


def _model_type(pipeline: Any, metadata: Dict[str, Any]) -> str:
    if metadata.get("model_type"):
        return str(metadata["model_type"])
    try:
        classifier = pipeline.named_steps.get("classifier") or pipeline.steps[-1][1]
        return type(classifier).__name__
    except Exception:
        return type(pipeline).__name__


class ModelService:
    def __init__(self, path: str, metadata_path: str = ""):
        self.path = path
        self.metadata_path = metadata_path
        self.pipeline: Any = None
        self.loaded = False
        self.threshold = 0.5
        self.version: Optional[str] = None
        self.features = list(DEFAULT_FEATURES)
        self.metadata: Dict[str, Any] = {}
        self.model_type = "unknown"
        self.created_at: Optional[str] = None
        self.load_error: Optional[str] = None

    def load(self) -> bool:
        try:
            self.path = _resolve_model_path(self.path)
            self.metadata = _load_metadata(self.path, self.metadata_path)
            self.pipeline = joblib.load(self.path)
            self.threshold = float(
                getattr(self.pipeline, "threshold", None)
                or getattr(self.pipeline, "optimal_threshold", None)
                or self.metadata.get("optimal_threshold")
                or (self.metadata.get("validation_metrics") or {}).get("threshold")
                or 0.5
            )
            self.version = str(
                getattr(self.pipeline, "model_version", None)
                or self.metadata.get("model_version")
                or "unknown"
            )
            features = (
                getattr(self.pipeline, "input_features", None)
                or getattr(self.pipeline, "features", None)
                or self.metadata.get("input_features")
            )
            self.features = list(features) if features else list(DEFAULT_FEATURES)
            self.model_type = _model_type(self.pipeline, self.metadata)
            self.created_at = self.metadata.get("created_at")
            self.loaded = True
            self.load_error = None
            log.info(
                "Modèle chargé : version=%s type=%s seuil=%.4f features=%s",
                self.version,
                self.model_type,
                self.threshold,
                self.features,
            )
            self._warmup()
            return True
        except Exception as exc:  # pragma: no cover - dépend de l'artefact
            self.loaded = False
            self.load_error = str(exc)
            log.exception("Impossible de charger le modèle (%s)", self.path)
            return False

    def _warmup(self) -> None:
        """Premier appel XGBoost plus lent : on préchauffe le pipeline."""
        try:
            row = {c: 0.0 for c in self.features}
            if "type" in row:
                row["type"] = "TRANSFER"
            if "step" in row:
                row["step"] = 1.0
            self.predict_proba(row)
            log.info("Warm-up du modèle terminé")
        except Exception:
            log.debug("Warm-up impossible", exc_info=True)

    def predict_proba(self, row: dict) -> float:
        if not self.loaded or self.pipeline is None:
            raise RuntimeError("model_not_loaded")
        df = pd.DataFrame([row])
        missing = [c for c in self.features if c not in df.columns]
        if missing:
            raise ValueError(f"colonnes manquantes : {missing}")
        df = df[self.features]
        for column in self.features:
            if column != "type":
                df[column] = pd.to_numeric(df[column], errors="coerce").astype("float64")
        # sklearn/XGBoost sont thread-safe en lecture après fit : pas de verrou,
        # ce qui préserve la latence P95 sous charge (SNF2).
        return float(self.pipeline.predict_proba(df)[0, 1])

    def decide(self, probability: float) -> bool:
        # Règle identique au job Spark : probability >= threshold -> BLOCKED.
        return probability >= self.threshold

    def info(self) -> Dict[str, Any]:
        metadata = dict(self.metadata)
        return {
            "loaded": self.loaded,
            "model_version": self.version or "unknown",
            "model_type": self.model_type,
            "threshold": self.threshold,
            "features": list(self.features),
            "created_at": self.created_at,
            "test_metrics": dict(metadata.get("test_metrics") or {}),
            "validation_metrics": dict(metadata.get("validation_metrics") or {}),
            "metadata": metadata,
        }
