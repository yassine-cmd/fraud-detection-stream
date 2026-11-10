"""Accès aux dépendances externes : MongoDB, Kafka, simulateur.

RealBackend : vraies dépendances.
MockBackend : données simulées en mémoire (MOCK_MODE=1) pour développer le front sans infra.
"""
import json
import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx

from . import config
from .utils import iso_s, now_iso_ms

log = logging.getLogger("api.backend")


class BackendError(Exception):
    """Dépendance indisponible -> HTTP 503."""


# --------------------------------------------------------------------------- real
class RealBackend:
    mode = "real"

    def __init__(self):
        from pymongo import MongoClient
        self.mongo = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=2000)
        self.db = self.mongo[config.MONGO_DB]
        self._producer = None
        self._http = httpx.Client(timeout=3.0)

    # ---- Kafka (producteur créé à la demande : l'API démarre même si Kafka est KO)
    def _get_producer(self):
        if self._producer is None:
            from confluent_kafka import Producer
            self._producer = Producer({
                "bootstrap.servers": config.KAFKA_BOOTSTRAP,
                "socket.timeout.ms": 3000, "message.timeout.ms": 5000,
                "linger.ms": 5,
            })
        return self._producer

    def publish(self, tx: dict) -> None:
        """Publie avec transaction_id comme Record Key (cahier des charges §5.2)."""
        try:
            p = self._get_producer()
            errors: List[str] = []

            def cb(err, _msg):
                if err:
                    errors.append(str(err))

            p.produce(config.KAFKA_TOPIC, key=tx["transaction_id"].encode(),
                      value=json.dumps(tx).encode(), on_delivery=cb)
            p.flush(5)
            if errors:
                raise BackendError(f"Kafka : {errors[0]}")
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(f"Kafka indisponible : {e}") from e

    # ---- MongoDB
    def persist_prediction(self, doc: dict) -> None:
        try:
            self.db.transactions.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        except Exception as e:
            raise BackendError(f"MongoDB indisponible : {e}") from e

    def stats(self) -> dict:
        """Lit uniquement les compteurs pré-agrégés (stats_buckets)."""
        try:
            agg = list(self.db.stats_buckets.aggregate([{"$group": {
                "_id": None, "tx": {"$sum": "$total_tx"}, "fr": {"$sum": "$total_frauds"},
                "amt": {"$sum": "$fraud_amount"}, "last": {"$max": "$_id"}}}]))
        except Exception as e:
            raise BackendError(f"MongoDB indisponible : {e}") from e
        a = agg[0] if agg else {"tx": 0, "fr": 0, "amt": 0.0, "last": None}
        tx = int(a["tx"])
        return {"total_tx": tx, "total_frauds": int(a["fr"]),
                "fraud_rate": round(a["fr"] / tx, 6) if tx else 0.0,
                "fraud_amount": float(a["amt"]), "last_update": a["last"]}

    def timeseries(self, window_s: int, bucket_s: int) -> List[dict]:
        base = config.STATS_BASE_BUCKET_SECONDS
        start = datetime.now(timezone.utc) - timedelta(seconds=window_s)
        try:
            docs = list(self.db.stats_buckets.find({"_id": {"$gte": iso_s(start)}}).sort("_id", 1))
        except Exception as e:
            raise BackendError(f"MongoDB indisponible : {e}") from e
        step = max(bucket_s, base)
        out: Dict[int, dict] = {}
        for d in docs:
            ts = int(datetime.strptime(d["_id"], "%Y-%m-%dT%H:%M:%SZ")
                     .replace(tzinfo=timezone.utc).timestamp())
            k = ts - ts % step
            o = out.setdefault(k, {"tx": 0, "frauds": 0})
            o["tx"] += int(d.get("total_tx", 0))
            o["frauds"] += int(d.get("total_frauds", 0))
        return [{"t": iso_s(datetime.fromtimestamp(k, timezone.utc)), **v} for k, v in sorted(out.items())]

    def latest_alerts(self, limit: int) -> List[dict]:
        try:
            docs = self.db.fraud_alerts.find().sort("scored_at", -1).limit(limit)
            return [{
                "transaction_id": str(d["_id"] if "transaction_id" not in d else d["transaction_id"]),
                "timestamp": _iso(d.get("scored_at")),   # scored_at exposé sous le nom timestamp
                "type": d.get("type", ""), "amount": float(d.get("amount", 0)),
                "probability": float(d.get("probability", 0)),
                "model_version": str(d.get("model_version", "")),
            } for d in docs]
        except Exception as e:
            raise BackendError(f"MongoDB indisponible : {e}") from e

    # ---- simulateur (serveur HTTP interne, réseau Docker)
    def stream_control(self, payload: dict) -> dict:
        try:
            r = self._http.post(f"{config.SIMULATOR_URL}/control", json=payload)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise BackendError(f"Simulateur indisponible : {e}") from e

    def stream_status(self) -> dict:
        try:
            r = self._http.get(f"{config.SIMULATOR_URL}/status")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise BackendError(f"Simulateur indisponible : {e}") from e

    def health(self) -> Dict[str, str]:
        res = {}
        try:
            self.mongo.admin.command("ping")
            res["mongodb"] = "up"
        except Exception:
            res["mongodb"] = "down"
        try:
            md = self._get_producer().list_topics(timeout=2)
            res["kafka"] = "up" if md.brokers else "down"
        except Exception:
            res["kafka"] = "down"
        return res


def _iso(v) -> str:
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return str(v) if v is not None else ""


# --------------------------------------------------------------------------- mock
class MockBackend:
    """Générateur en mémoire : un thread simule le flux tant que le simulateur est 'démarré'."""
    mode = "mock"

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets: Dict[str, dict] = {}
        self._alerts: List[dict] = []
        self._sim = {"running": False, "rate_tx_per_sec": 500, "fraud_ratio": 0.02, "sent": 0}
        self._sent: List[dict] = []
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(1)
            with self._lock:
                if not self._sim["running"]:
                    continue
                n = int(self._sim["rate_tx_per_sec"] * random.uniform(0.9, 1.0))
                fr = sum(1 for _ in range(min(n, 5000)) if random.random() < self._sim["fraud_ratio"])
                amt = sum(random.uniform(5e4, 5e5) for _ in range(fr))
                now = datetime.now(timezone.utc)
                k = iso_s(now.replace(second=now.second - now.second % config.STATS_BASE_BUCKET_SECONDS, microsecond=0))
                b = self._buckets.setdefault(k, {"tx": 0, "frauds": 0, "amt": 0.0})
                b["tx"] += n; b["frauds"] += fr; b["amt"] += amt
                self._sim["sent"] += n
                for _ in range(min(fr, 3)):
                    self._alerts.insert(0, {
                        "transaction_id": f"tx_mock_{random.getrandbits(32):08x}",
                        "timestamp": now_iso_ms(), "type": random.choice(["TRANSFER", "CASH_OUT"]),
                        "amount": round(random.uniform(5e4, 5e5), 2),
                        "probability": round(random.uniform(0.5, 0.999), 4), "model_version": "mock"})
                del self._alerts[200:]

    def publish(self, tx: dict) -> None:
        with self._lock:
            self._sent.append(tx)

    def persist_prediction(self, doc: dict) -> None:
        pass

    def stats(self) -> dict:
        with self._lock:
            tx = sum(b["tx"] for b in self._buckets.values())
            fr = sum(b["frauds"] for b in self._buckets.values())
            amt = sum(b["amt"] for b in self._buckets.values())
            last = max(self._buckets) if self._buckets else None
        return {"total_tx": tx, "total_frauds": fr, "fraud_rate": round(fr / tx, 6) if tx else 0.0,
                "fraud_amount": round(amt, 2), "last_update": last}

    def timeseries(self, window_s: int, bucket_s: int) -> List[dict]:
        limit = datetime.now(timezone.utc) - timedelta(seconds=window_s)
        step = max(bucket_s, config.STATS_BASE_BUCKET_SECONDS)
        out: Dict[int, dict] = {}
        with self._lock:
            for k, b in sorted(self._buckets.items()):
                dt = datetime.strptime(k, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if dt < limit:
                    continue
                ts = int(dt.timestamp()); ts -= ts % step
                o = out.setdefault(ts, {"tx": 0, "frauds": 0})
                o["tx"] += b["tx"]; o["frauds"] += b["frauds"]
        return [{"t": iso_s(datetime.fromtimestamp(k, timezone.utc)), **v} for k, v in sorted(out.items())]

    def latest_alerts(self, limit: int) -> List[dict]:
        with self._lock:
            return list(self._alerts[:limit])

    def stream_control(self, payload: dict) -> dict:
        with self._lock:
            if payload["action"] == "start":
                self._sim["running"] = True
                for k in ("rate_tx_per_sec", "fraud_ratio"):
                    if payload.get(k) is not None:
                        self._sim[k] = payload[k]
            else:
                self._sim["running"] = False
            return dict(self._sim)

    def stream_status(self) -> dict:
        with self._lock:
            return dict(self._sim)

    def health(self) -> Dict[str, str]:
        return {"mongodb": "mock", "kafka": "mock"}


def make_backend():
    return MockBackend() if config.MOCK_MODE else RealBackend()
