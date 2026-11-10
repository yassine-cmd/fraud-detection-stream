import os
os.environ["MOCK_MODE"] = "1"
os.environ["MODEL_PATH"] = os.path.join(os.path.dirname(__file__), "..", "model", "model.joblib")

import pytest
from fastapi.testclient import TestClient
from app.main import app

P = "/api/v1"
TX = {"step": 650, "type": "TRANSFER", "amount": 300000, "oldbalanceOrg": 300000,
      "newbalanceOrig": 0, "oldbalanceDest": 0, "newbalanceDest": 300000}


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def test_health(c):
    j = c.get(f"{P}/health").json()
    assert j["model_loaded"] is True and j["mode"] == "mock" and j["model_version"]


def test_predict_contract(c):
    j = c.post(f"{P}/predict", json=TX).json()
    assert set(j) == {"transaction_id", "is_fraud", "probability", "decision", "threshold", "model_version", "latency_ms"}
    assert j["transaction_id"].startswith("tx_")
    assert j["decision"] == ("BLOCKED" if j["probability"] >= j["threshold"] else "ALLOWED")


@pytest.mark.parametrize("patch", [{"type": "FOO"}, {"amount": -1}, {"step": 0}, {"oldbalanceOrg": None}])
def test_predict_422(c, patch):
    assert c.post(f"{P}/predict", json={**TX, **patch}).status_code == 422


def test_transactions_queued(c):
    j = c.post(f"{P}/transactions", json={**TX, "transaction_id": "tx_abc"}).json()
    assert j == {"status": "queued", "transaction_id": "tx_abc"}


def test_stream_stats_alerts(c):
    import time
    c.post(f"{P}/stream/control", json={"action": "start", "rate_tx_per_sec": 500, "fraud_ratio": 0.5})
    assert c.get(f"{P}/stream/status").json()["running"] is True
    time.sleep(2.5)
    s = c.get(f"{P}/stats").json()
    assert s["total_tx"] > 0
    ts = c.get(f"{P}/stats/timeseries?window=15m&bucket=10s").json()
    assert ts["bucket"] == "10s" and ts["points"]
    a = c.get(f"{P}/alerts/latest?limit=5").json()
    assert 0 < len(a) <= 5 and "timestamp" in a[0]
    c.post(f"{P}/stream/control", json={"action": "stop"})
    assert c.get(f"{P}/stream/status").json()["running"] is False


def test_limits(c):
    assert c.get(f"{P}/alerts/latest?limit=101").status_code == 422
    assert c.get(f"{P}/stats/timeseries?window=xx").status_code == 422
