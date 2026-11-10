"""Chargement et inférence du pipeline model.joblib.

Le prétraitement fait partie du pipeline exporté : on lui passe un DataFrame brut
avec les colonnes listées dans `pipeline.features` (float64), exactement comme Spark.
"""
import logging
import threading
from typing import Optional

import joblib
import pandas as pd

log = logging.getLogger("api.model")

DEFAULT_FEATURES = ["step", "type", "amount", "oldbalanceOrg",
                    "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]


class ModelService:
    def __init__(self, path: str):
        self.path = path
        self.pipeline = None
        self.loaded = False
        self.threshold = 0.5
        self.version: Optional[str] = None
        self.features = DEFAULT_FEATURES
        self._lock = threading.Lock()

    def load(self) -> None:
        try:
            self.pipeline = joblib.load(self.path)
            self.threshold = float(getattr(self.pipeline, "threshold", 0.5))
            self.version = str(getattr(self.pipeline, "model_version", "unknown"))
            self.features = list(getattr(self.pipeline, "features", DEFAULT_FEATURES))
            self.loaded = True
            log.info("Modèle chargé : version=%s seuil=%s", self.version, self.threshold)
        except Exception:
            log.exception("Impossible de charger le modèle (%s)", self.path)
            self.loaded = False

    def predict_proba(self, row: dict) -> float:
        if not self.loaded:
            raise RuntimeError("model_not_loaded")
        df = pd.DataFrame([row])[self.features]
        for c in self.features:
            if c != "type":
                df[c] = df[c].astype("float64")
        with self._lock:  # sklearn est thread-safe en lecture, verrou par prudence (XGBoost/n_jobs)
            return float(self.pipeline.predict_proba(df)[0, 1])

    def decide(self, p: float) -> bool:
        # NB : >= ; à aligner avec le job Spark (même règle des deux côtés).
        return p >= self.threshold
