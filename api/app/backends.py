"""Accès aux dépendances externes : MongoDB, Kafka, simulateur.

`RealBackend` parle aux vrais services du docker-compose (MongoDB, Kafka,
producteur HTTP). `MockBackend` génère un flux cohérent en mémoire pour
développer le front-end sans infrastructure (`MOCK_MODE=1`).

Les agrégations MongoDB sont alignées sur le schéma réel du job Spark :
`stats_buckets._id = batch_id`, le temps est porté par `bucket_start`.
"""
import json
import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from . import config
from .utils import iso_s, now_iso_ms, parse_iso, timestamp_to_iso

log = logging.getLogger("api.backend")

# Types PaySim et poids approximatifs du jeu de données.
_TX_TYPES = [("CASH_OUT", 0.35), ("PAYMENT", 0.34), ("CASH_IN", 0.21), ("TRANSFER", 0.09), ("DEBIT", 0.01)]


class BackendError(Exception):
    """Dépendance indisponible (ou commande invalide) -> réponse HTTP d'erreur."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


# --------------------------------------------------------------------------- helpers
def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * q
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * weight)


def _bucket_datetime(doc: dict) -> Optional[datetime]:
    """Temps d'un document stats_buckets (schéma actuel ou legacy)."""
    for key in ("bucket_start", "_id"):
        value = doc.get(key)
        parsed = parse_iso(value)
        if parsed is not None:
            return parsed
    return None


def _fill_points(points: Dict[int, dict], step: int) -> List[dict]:
    """Complète les trous entre le premier et le dernier point (courbe continue)."""
    if not points:
        return []
    keys = sorted(points)
    start, end = keys[0], keys[-1]
    out: List[dict] = []
    for key in range(start, end + step, step):
        bucket = points.get(key, {"tx": 0, "frauds": 0})
        out.append(
            {
                "t": iso_s(datetime.fromtimestamp(key, timezone.utc)),
                "tx": int(bucket.get("tx", 0)),
                "frauds": int(bucket.get("frauds", 0)),
            }
        )
    return out


def _normalize_sim_status(payload: dict) -> dict:
    """Normalise la réponse du producteur P2 (is_running/total_sent/...)."""
    is_running = bool(payload.get("is_running", payload.get("running", False)))
    total_sent = _safe_int(payload.get("total_sent", payload.get("sent", 0)))
    return {
        "is_running": is_running,
        "running": is_running,
        "rate_tx_per_sec": _safe_int(payload.get("rate_tx_per_sec"), 500),
        "fraud_ratio": _safe_float(payload.get("fraud_ratio"), 0.0),
        "total_sent": total_sent,
        "sent": total_sent,
        "total_delivered": _safe_int(payload.get("total_delivered"), total_sent),
        "errors_count": _safe_int(payload.get("errors_count"), 0),
        "dataset_rows": _safe_int(payload.get("dataset_rows"), 0),
        "last_error": payload.get("last_error"),
    }


# --------------------------------------------------------------------------- real
class RealBackend:
    mode = "real"

    def __init__(self):
        from pymongo import MongoClient

        self.mongo = MongoClient(
            config.MONGO_URI,
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
            socketTimeoutMS=15000,
            maxPoolSize=50,
        )
        self.db = self.mongo[config.MONGO_DB]
        self._producer = None
        self._producer_lock = threading.Lock()
        self._http = httpx.Client(timeout=config.SIMULATOR_TIMEOUT)
        self._breakdown_cache: Dict[int, tuple] = {}
        self._cache_lock = threading.Lock()

    # ---- Kafka (producteur créé à la demande : l'API démarre même si Kafka est KO)
    def _get_producer(self):
        if self._producer is None:
            with self._producer_lock:
                if self._producer is None:
                    from confluent_kafka import Producer

                    self._producer = Producer(
                        {
                            "bootstrap.servers": config.KAFKA_BOOTSTRAP,
                            "client.id": "fraud-api",
                            "socket.timeout.ms": 3000,
                            "message.timeout.ms": 5000,
                            "linger.ms": 5,
                            "acks": "all",
                        }
                    )
        return self._producer

    def publish(self, tx: dict) -> None:
        """Publie avec transaction_id comme Record Key (cahier des charges §5.2)."""
        errors: List[str] = []

        def on_delivery(err, _msg):
            if err:
                errors.append(str(err))

        try:
            producer = self._get_producer()
            producer.produce(
                config.KAFKA_TOPIC,
                key=tx["transaction_id"].encode(),
                value=json.dumps(tx, ensure_ascii=False, separators=(",", ":")).encode(),
                on_delivery=on_delivery,
            )
            remaining = producer.flush(5)
            if errors:
                raise BackendError(f"Kafka : {errors[0]}")
            if remaining:
                raise BackendError("Kafka : file d'attente non vidée (broker indisponible ?)")
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"Kafka indisponible : {exc}") from exc

    # ---- MongoDB
    def persist_prediction(self, doc: dict) -> None:
        try:
            self.db.transactions.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        except Exception as exc:
            raise BackendError(f"MongoDB indisponible : {exc}") from exc

    def stats(self) -> dict:
        """Compteurs cumulés pré-agrégés (stats_buckets), sans scan de transactions."""
        try:
            agg = list(
                self.db.stats_buckets.aggregate(
                    [
                        {
                            "$group": {
                                "_id": None,
                                "tx": {"$sum": {"$ifNull": ["$total_tx", 0]}},
                                "fr": {"$sum": {"$ifNull": ["$total_frauds", 0]}},
                                "amt": {"$sum": {"$ifNull": ["$fraud_amount", 0]}},
                            }
                        }
                    ]
                )
            )
            last_doc = self.db.stats_buckets.find_one(
                {"bucket_start": {"$exists": True, "$ne": None}},
                {"bucket_start": 1},
                sort=[("bucket_start", -1)],
            )
            if last_doc is None:
                last_doc = self.db.stats_buckets.find_one(
                    {"_id": {"$type": "string"}},
                    {"_id": 1},
                    sort=[("_id", -1)],
                )
        except Exception as exc:
            raise BackendError(f"MongoDB indisponible : {exc}") from exc

        row = agg[0] if agg else {"tx": 0, "fr": 0, "amt": 0.0}
        total_tx = _safe_int(row.get("tx"))
        total_frauds = _safe_int(row.get("fr"))
        last_update = None
        if last_doc:
            last_update = last_doc.get("bucket_start") or last_doc.get("_id")
        return {
            "total_tx": total_tx,
            "total_frauds": total_frauds,
            "fraud_rate": round(total_frauds / total_tx, 6) if total_tx else 0.0,
            "fraud_amount": round(_safe_float(row.get("amt")), 2),
            "last_update": timestamp_to_iso(last_update) if last_update else None,
        }

    def timeseries(self, window_s: int, bucket_s: int) -> List[dict]:
        start = datetime.now(timezone.utc) - timedelta(seconds=window_s)
        start_iso = iso_s(start)
        step = max(bucket_s, config.STATS_BASE_BUCKET_SECONDS)
        query = {
            "$or": [
                {"bucket_start": {"$gte": start_iso}},
                {"_id": {"$type": "string", "$gte": start_iso}},
            ]
        }
        try:
            docs = list(
                self.db.stats_buckets.find(
                    query, {"bucket_start": 1, "_id": 1, "total_tx": 1, "total_frauds": 1}
                )
            )
        except Exception as exc:
            raise BackendError(f"MongoDB indisponible : {exc}") from exc

        points: Dict[int, dict] = {}
        for doc in docs:
            when = _bucket_datetime(doc)
            if when is None or when < start:
                continue
            key = int(when.timestamp())
            key -= key % step
            point = points.setdefault(key, {"tx": 0, "frauds": 0})
            point["tx"] += _safe_int(doc.get("total_tx"))
            point["frauds"] += _safe_int(doc.get("total_frauds"))
        return _fill_points(points, step)

    def breakdown(self, window_s: int) -> List[dict]:
        with self._cache_lock:
            cached = self._breakdown_cache.get(window_s)
            if cached and (time.time() - cached[0]) < 10.0:
                return cached[1]

        start = datetime.now(timezone.utc) - timedelta(seconds=window_s)
        pipeline = [
            {"$match": {"scored_at": {"$gte": start}}},
            {
                "$group": {
                    "_id": "$type",
                    "total": {"$sum": 1},
                    "frauds": {"$sum": {"$cond": ["$is_fraud", 1, 0]}},
                    "amount": {"$sum": {"$ifNull": ["$amount", 0]}},
                    "fraud_amount": {
                        "$sum": {"$cond": ["$is_fraud", {"$ifNull": ["$amount", 0]}, 0]}
                    },
                }
            },
            {"$sort": {"total": -1}},
        ]
        try:
            rows = list(self.db.transactions.aggregate(pipeline))
        except Exception as exc:
            raise BackendError(f"MongoDB indisponible : {exc}") from exc
        out = []
        for row in rows:
            total = _safe_int(row.get("total"))
            frauds = _safe_int(row.get("frauds"))
            out.append(
                {
                    "type": str(row.get("_id") or "INCONNU"),
                    "total": total,
                    "frauds": frauds,
                    "fraud_rate": round(frauds / total, 6) if total else 0.0,
                    "amount": round(_safe_float(row.get("amount")), 2),
                    "fraud_amount": round(_safe_float(row.get("fraud_amount")), 2),
                }
            )
        with self._cache_lock:
            self._breakdown_cache[window_s] = (time.time(), out)
        return out

    def latency(self, window_s: int) -> dict:
        start = datetime.now(timezone.utc) - timedelta(seconds=window_s)
        try:
            cursor = (
                self.db.transactions.find(
                    {
                        "scored_at": {"$gte": start},
                        "pipeline_latency_ms": {"$type": "number"},
                    },
                    {"pipeline_latency_ms": 1},
                )
                .sort("scored_at", -1)
                .limit(5000)
            )
            values = [
                _safe_float(doc.get("pipeline_latency_ms"))
                for doc in cursor
                if doc.get("pipeline_latency_ms") is not None
            ]
        except Exception as exc:
            raise BackendError(f"MongoDB indisponible : {exc}") from exc
        return _latency_payload(values)

    def latest_alerts(self, limit: int) -> List[dict]:
        try:
            docs = (
                self.db.fraud_alerts.find()
                .sort("scored_at", -1)
                .limit(limit)
            )
            out = []
            for doc in docs:
                item = {
                    "transaction_id": str(doc.get("transaction_id") or doc.get("_id", "")),
                    "timestamp": timestamp_to_iso(doc.get("scored_at") or doc.get("timestamp")),
                    "type": str(doc.get("type", "")),
                    "amount": round(_safe_float(doc.get("amount")), 2),
                    "probability": round(_safe_float(doc.get("probability")), 6),
                    "decision": str(doc.get("decision", "BLOCKED")),
                    "model_version": str(doc.get("model_version", "")),
                }
                for f in ("oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"):
                    if f in doc and doc[f] is not None:
                        item[f] = round(_safe_float(doc[f]), 2)
                for f in ("nameOrig", "nameDest"):
                    if f in doc and doc[f]:
                        item[f] = str(doc[f])
                out.append(item)
            return out
        except Exception as exc:
            raise BackendError(f"MongoDB indisponible : {exc}") from exc

    # ---- simulateur (serveur HTTP interne, réseau Docker)
    def _simulator_request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        url = f"{config.SIMULATOR_URL.rstrip('/')}{path}"
        try:
            response = self._http.request(method, url, json=payload)
        except Exception as exc:
            raise BackendError(f"Simulateur indisponible : {exc}") from exc
        if response.status_code >= 400:
            message = f"Simulateur : HTTP {response.status_code}"
            try:
                body = response.json()
                message = str(body.get("error") or body.get("detail") or message)
            except ValueError:
                pass
            status = 422 if response.status_code in (400, 422) else 503
            raise BackendError(message, status_code=status)
        try:
            return response.json()
        except ValueError as exc:
            raise BackendError("Réponse invalide du simulateur") from exc

    def stream_control(self, payload: dict) -> dict:
        return _normalize_sim_status(self._simulator_request("POST", "/control", payload))

    def stream_status(self) -> dict:
        return _normalize_sim_status(self._simulator_request("GET", "/status"))

    def health(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        try:
            self.mongo.admin.command("ping")
            result["mongodb"] = "up"
            result["mongodb_connected"] = True
        except Exception:
            result["mongodb"] = "down"
            result["mongodb_connected"] = False
        try:
            metadata = self._get_producer().list_topics(timeout=2)
            up = bool(metadata.brokers)
            result["kafka"] = "up" if up else "down"
            result["kafka_connected"] = up
        except Exception:
            result["kafka"] = "down"
            result["kafka_connected"] = False

        # Vérification de l'avancement réel du pipeline Spark Streaming
        try:
            latest_batch = self.db.processed_batches.find_one(sort=[("processed_at", -1)])
            if latest_batch and "processed_at" in latest_batch:
                b_time = latest_batch["processed_at"]
                if b_time.tzinfo is None:
                    b_time = b_time.replace(tzinfo=timezone.utc)
                lag_s = max(0.0, (datetime.now(timezone.utc) - b_time).total_seconds())
                result["pipeline_lag_seconds"] = round(lag_s, 1)
                result["pipeline_synced"] = bool(lag_s < 30.0)
            else:
                result["pipeline_lag_seconds"] = None
                result["pipeline_synced"] = False
        except Exception:
            result["pipeline_lag_seconds"] = None
            result["pipeline_synced"] = False

        return result


# --------------------------------------------------------------------------- mock
class MockBackend:
    """Générateur en mémoire : un thread simule le flux tant que le simulateur est actif."""

    mode = "mock"

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets: Dict[str, dict] = {}
        self._alerts: List[dict] = []
        self._by_type: Dict[str, dict] = {}
        self._latencies: List[float] = []
        self._counter = 0
        self._sim = {
            "is_running": False,
            "running": False,
            "rate_tx_per_sec": 500,
            "fraud_ratio": 0.02,
            "total_sent": 0,
            "sent": 0,
            "total_delivered": 0,
            "errors_count": 0,
            "dataset_rows": 30000,
            "last_error": None,
        }
        threading.Thread(target=self._loop, daemon=True).start()

    def _pick_type(self) -> str:
        draw = random.random()
        cumulative = 0.0
        for name, weight in _TX_TYPES:
            cumulative += weight
            if draw <= cumulative:
                return name
        return _TX_TYPES[-1][0]

    def _record_bucket(self, when: datetime, tx: int, frauds: int, fraud_amount: float) -> None:
        key = iso_s(when.replace(second=when.second - when.second % config.STATS_BASE_BUCKET_SECONDS, microsecond=0))
        bucket = self._buckets.setdefault(key, {"tx": 0, "frauds": 0, "amt": 0.0})
        bucket["tx"] += tx
        bucket["frauds"] += frauds
        bucket["amt"] += fraud_amount

    def _loop(self):
        while True:
            time.sleep(1)
            with self._lock:
                if not self._sim["is_running"]:
                    continue
                rate = max(1, int(self._sim["rate_tx_per_sec"]))
                count = max(1, int(rate * random.uniform(0.94, 1.0)))
                ratio = max(0.0, min(1.0, float(self._sim["fraud_ratio"])))
                frauds = 0
                fraud_amount = 0.0
                now = datetime.now(timezone.utc)

                for _ in range(count):
                    tx_type = self._pick_type()
                    amount = round(random.uniform(10.0, 450000.0), 2)
                    is_fraud = tx_type in ("TRANSFER", "CASH_OUT") and random.random() < ratio
                    entry = self._by_type.setdefault(
                        tx_type, {"total": 0, "frauds": 0, "amount": 0.0, "fraud_amount": 0.0}
                    )
                    entry["total"] += 1
                    entry["amount"] += amount
                    if is_fraud:
                        frauds += 1
                        fraud_amount += amount
                        entry["frauds"] += 1
                        entry["fraud_amount"] += amount

                self._record_bucket(now, count, frauds, fraud_amount)
                self._sim["total_sent"] += count
                self._sim["sent"] = self._sim["total_sent"]
                self._sim["total_delivered"] = self._sim["total_sent"]
                self._latencies.extend(random.uniform(22.0, 95.0) for _ in range(min(count, 200)))
                del self._latencies[:-5000]

                for _ in range(min(frauds, 12)):
                    self._counter += 1
                    tx_type = random.choice(("TRANSFER", "CASH_OUT"))
                    self._alerts.insert(
                        0,
                        {
                            "transaction_id": f"tx_mock_{self._counter:08x}",
                            "timestamp": now_iso_ms(),
                            "type": tx_type,
                            "amount": round(random.uniform(80000.0, 600000.0), 2),
                            "probability": round(random.uniform(0.88, 0.999), 6),
                            "decision": "BLOCKED",
                            "model_version": "v1.0.0-xgb",
                        },
                    )
                del self._alerts[300:]

    def publish(self, tx: dict) -> None:
        with self._lock:
            self._sim["total_sent"] += 1
            self._sim["sent"] = self._sim["total_sent"]

    def persist_prediction(self, doc: dict) -> None:
        # Le vrai backend écrit uniquement dans `transactions` (source: "api").
        # Le mock conserve donc uniquement la latence pour l'observabilité :
        # ni les compteurs Spark (`stats_buckets`) ni les alertes du flux ne
        # doivent être modifiés par un test unitaire.
        with self._lock:
            self._latencies.append(_safe_float(doc.get("pipeline_latency_ms")))
            del self._latencies[:-5000]

    def stats(self) -> dict:
        with self._lock:
            tx = sum(b["tx"] for b in self._buckets.values())
            frauds = sum(b["frauds"] for b in self._buckets.values())
            amount = sum(b["amt"] for b in self._buckets.values())
            last = max(self._buckets) if self._buckets else None
        return {
            "total_tx": tx,
            "total_frauds": frauds,
            "fraud_rate": round(frauds / tx, 6) if tx else 0.0,
            "fraud_amount": round(amount, 2),
            "last_update": last,
        }

    def timeseries(self, window_s: int, bucket_s: int) -> List[dict]:
        limit = datetime.now(timezone.utc) - timedelta(seconds=window_s)
        step = max(bucket_s, config.STATS_BASE_BUCKET_SECONDS)
        points: Dict[int, dict] = {}
        with self._lock:
            for key, bucket in self._buckets.items():
                when = parse_iso(key)
                if when is None or when < limit:
                    continue
                ts = int(when.timestamp())
                ts -= ts % step
                point = points.setdefault(ts, {"tx": 0, "frauds": 0})
                point["tx"] += bucket["tx"]
                point["frauds"] += bucket["frauds"]
        return _fill_points(points, step)

    def breakdown(self, window_s: int) -> List[dict]:
        with self._lock:
            rows = [
                {
                    "type": name,
                    "total": int(value["total"]),
                    "frauds": int(value["frauds"]),
                    "fraud_rate": round(value["frauds"] / value["total"], 6) if value["total"] else 0.0,
                    "amount": round(value["amount"], 2),
                    "fraud_amount": round(value["fraud_amount"], 2),
                }
                for name, value in self._by_type.items()
            ]
        return sorted(rows, key=lambda item: item["total"], reverse=True)

    def latency(self, _window_s: int) -> dict:
        with self._lock:
            values = list(self._latencies[-5000:])
        return _latency_payload(values)

    def latest_alerts(self, limit: int) -> List[dict]:
        with self._lock:
            return [dict(alert) for alert in self._alerts[:limit]]

    def stream_control(self, payload: dict) -> dict:
        with self._lock:
            if payload.get("action") == "start":
                self._sim["is_running"] = True
                self._sim["running"] = True
                if payload.get("rate_tx_per_sec") is not None:
                    self._sim["rate_tx_per_sec"] = int(payload["rate_tx_per_sec"])
                if payload.get("fraud_ratio") is not None:
                    self._sim["fraud_ratio"] = float(payload["fraud_ratio"])
            else:
                self._sim["is_running"] = False
                self._sim["running"] = False
            return dict(self._sim)

    def stream_status(self) -> dict:
        with self._lock:
            return dict(self._sim)

    def health(self) -> Dict[str, Any]:
        return {
            "mongodb": "mock",
            "kafka": "mock",
            "mongodb_connected": True,
            "kafka_connected": True,
        }


def _latency_payload(values: List[float]) -> dict:
    values = [float(v) for v in values if v is not None and float(v) >= 0]
    return {
        "count": len(values),
        "avg_ms": round(sum(values) / len(values), 2) if values else 0.0,
        "p50_ms": round(_percentile(values, 0.50), 2),
        "p95_ms": round(_percentile(values, 0.95), 2),
        "p99_ms": round(_percentile(values, 0.99), 2),
        "max_ms": round(max(values), 2) if values else 0.0,
    }


def make_backend():
    return MockBackend() if config.MOCK_MODE else RealBackend()
