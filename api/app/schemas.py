"""Schémas Pydantic — contrat d'interface (cahier des charges §5).

Les réponses respectent le contrat OpenAPI de l'équipe. Quelques champs
d'observabilité sont ajoutés (seuil, uptime, latences, métriques du modèle)
sans jamais retirer les champs contractuels.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

TxType = Literal["PAYMENT", "TRANSFER", "CASH_OUT", "DEBIT", "CASH_IN"]


class TransactionIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "step": 650,
                "type": "TRANSFER",
                "amount": 300000.0,
                "nameOrig": "C123456789",
                "oldbalanceOrg": 300000.0,
                "newbalanceOrig": 0.0,
                "nameDest": "C987654321",
                "oldbalanceDest": 0.0,
                "newbalanceDest": 300000.0,
            }
        }
    )

    transaction_id: Optional[str] = Field(
        None, description="Généré (tx_<uuid4>) s'il est omis. Doit commencer par 'tx_'."
    )
    step: int = Field(..., ge=1, description="Pas de temps PaySim (1 unité = 1 heure)")
    type: TxType
    amount: float = Field(..., ge=0, allow_inf_nan=False)
    oldbalanceOrg: float = Field(..., ge=0, allow_inf_nan=False)
    newbalanceOrig: float = Field(..., ge=0, allow_inf_nan=False)
    oldbalanceDest: float = Field(..., ge=0, allow_inf_nan=False)
    newbalanceDest: float = Field(..., ge=0, allow_inf_nan=False)
    nameOrig: Optional[str] = Field(None, description="Identifiant client (non utilisé par le modèle)")
    nameDest: Optional[str] = Field(None, description="Identifiant destinataire (non utilisé par le modèle)")

    @field_validator("transaction_id")
    @classmethod
    def _validate_transaction_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.startswith("tx_"):
            raise ValueError("transaction_id doit commencer par 'tx_' (contrat Kafka/Spark)")
        if len(value) > 128:
            raise ValueError("transaction_id trop long (128 caractères maximum)")
        return value


class PredictionOut(BaseModel):
    transaction_id: str
    is_fraud: bool
    probability: float
    decision: Literal["BLOCKED", "ALLOWED"]
    threshold: float
    model_version: str
    latency_ms: float


class QueuedOut(BaseModel):
    status: Literal["queued"] = "queued"
    transaction_id: str


class StatsOut(BaseModel):
    total_tx: int
    total_frauds: int
    fraud_rate: float
    fraud_amount: float
    last_update: Optional[str] = None


class TimePoint(BaseModel):
    t: str
    tx: int
    frauds: int


class TimeseriesOut(BaseModel):
    bucket: str
    points: List[TimePoint]


class AlertOut(BaseModel):
    transaction_id: str
    timestamp: str
    type: str
    amount: float
    probability: float
    decision: Literal["BLOCKED", "ALLOWED"] = "BLOCKED"
    model_version: str
    oldbalanceOrg: Optional[float] = None
    newbalanceOrig: Optional[float] = None
    oldbalanceDest: Optional[float] = None
    newbalanceDest: Optional[float] = None
    nameOrig: Optional[str] = None
    nameDest: Optional[str] = None


class StreamControlIn(BaseModel):
    action: Literal["start", "stop"]
    rate_tx_per_sec: Optional[int] = Field(None, ge=1, le=5000, description="100–1000 recommandé, 5000 max")
    fraud_ratio: Optional[float] = Field(None, ge=0, le=1)


class StreamStatusOut(BaseModel):
    """État normalisé du simulateur (compatible producteur P2).

    `running` et `sent` sont conservés comme alias de compatibilité pour les
    anciens clients ; les champs de référence restent `is_running` et
    `total_sent`, conformes au contrat OpenAPI.
    """

    is_running: bool = False
    running: bool = False
    rate_tx_per_sec: Optional[int] = None
    fraud_ratio: Optional[float] = None
    total_sent: int = 0
    sent: int = 0
    total_delivered: int = 0
    errors_count: int = 0
    dataset_rows: int = 0
    last_error: Optional[str] = None


class HealthOut(BaseModel):
    status: Literal["healthy", "degraded"]
    mode: Literal["real", "mock"]
    model_loaded: bool
    model_version: Optional[str] = None
    threshold: float = 0.5
    kafka: str
    mongodb: str
    kafka_connected: bool = False
    mongodb_connected: bool = False
    uptime_s: float = 0.0
    pipeline_lag_seconds: Optional[float] = None
    pipeline_synced: Optional[bool] = None


class ModelInfoOut(BaseModel):
    loaded: bool
    model_version: str
    model_type: str
    threshold: float
    features: List[str]
    created_at: Optional[str] = None
    test_metrics: Dict[str, Any] = Field(default_factory=dict)
    validation_metrics: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TypeBreakdownItem(BaseModel):
    type: str
    total: int
    frauds: int
    fraud_rate: float
    amount: float
    fraud_amount: float


class BreakdownOut(BaseModel):
    window: str
    by_type: List[TypeBreakdownItem]


class LatencyOut(BaseModel):
    window: str
    count: int
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0
