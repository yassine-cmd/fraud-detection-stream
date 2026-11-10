"""Schémas Pydantic — contrat d'interface (cahier des charges §5)."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TxType = Literal["PAYMENT", "TRANSFER", "CASH_OUT", "DEBIT", "CASH_IN"]


class TransactionIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "step": 650, "type": "TRANSFER", "amount": 300000.0,
        "nameOrig": "C123456789", "oldbalanceOrg": 300000.0, "newbalanceOrig": 0.0,
        "nameDest": "C987654321", "oldbalanceDest": 0.0, "newbalanceDest": 300000.0}})

    transaction_id: Optional[str] = Field(None, description="Généré (tx_<uuid4>) s'il est omis")
    step: int = Field(..., ge=1)
    type: TxType
    amount: float = Field(..., ge=0)
    oldbalanceOrg: float = Field(..., ge=0)
    newbalanceOrig: float = Field(..., ge=0)
    oldbalanceDest: float = Field(..., ge=0)
    newbalanceDest: float = Field(..., ge=0)
    nameOrig: Optional[str] = None
    nameDest: Optional[str] = None


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
    model_version: str


class StreamControlIn(BaseModel):
    action: Literal["start", "stop"]
    rate_tx_per_sec: Optional[int] = Field(None, ge=1, le=1000, description="100–1000 recommandé")
    fraud_ratio: Optional[float] = Field(None, ge=0, le=1)


class StreamStatusOut(BaseModel):
    running: bool
    rate_tx_per_sec: Optional[int] = None
    fraud_ratio: Optional[float] = None
    sent: Optional[int] = None


class HealthOut(BaseModel):
    status: Literal["healthy", "degraded"]
    mode: Literal["real", "mock"]
    model_loaded: bool
    model_version: Optional[str] = None
    kafka: str
    mongodb: str
