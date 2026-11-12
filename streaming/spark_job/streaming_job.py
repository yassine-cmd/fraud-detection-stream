"""streaming_job.py - Apache Spark Structured Streaming avec scoring ML et idempotence MongoDB.

Fonctionne aussi bien :
- En conteneur Docker (via docker compose et le cluster spark-master / spark-worker)
- En local sur la machine hote (via PySpark en local avec Kafka et MongoDB exposes)

Le scoring est applique par une pandas_udf distribuee sur les executers Spark.
Le modele composite (preprocessing + classifieur + seuil + version) est charge
depuis model.joblib et diffuse via une variable broadcast.
"""

import os
from datetime import datetime, timezone

import joblib
import pandas as pd
from pymongo import MongoClient, UpdateOne
from pymongo.errors import DuplicateKeyError

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, LongType, StringType, StructField, StructType

# ---------- Configuration (priorite aux variables d'environnement) ----------
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "transactions_stream")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "fraud")
MONGO_ENABLED = os.getenv("MONGO_ENABLED", "true").lower() == "true"
MODEL_PATH = os.getenv("MODEL_PATH", "ml/artifacts/model.joblib")
CHECKPOINT = os.path.join(os.getenv("CHECKPOINT_DIR", "./checkpoint"), "stream_v2")
TRIGGER_SECONDS = os.getenv("TRIGGER_SECONDS", "1")
MAX_OFFSETS = os.getenv("MAX_OFFSETS_PER_TRIGGER", "2000")

FEATURE_COLS = [
    "step",
    "type",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
]

# Schema conforme au contrat kafka_message.schema.json
SCHEMA = StructType(
    [
        StructField("transaction_id", StringType()),
        StructField("step", LongType()),
        StructField("type", StringType()),
        StructField("amount", DoubleType()),
        StructField("nameOrig", StringType()),
        StructField("oldbalanceOrg", DoubleType()),
        StructField("newbalanceOrig", DoubleType()),
        StructField("nameDest", StringType()),
        StructField("oldbalanceDest", DoubleType()),
        StructField("newbalanceDest", DoubleType()),
        StructField("produced_at", StringType()),
    ]
)

GLOBAL_MODEL = None
GLOBAL_MONGO = None


def get_mongo_db():
    global GLOBAL_MONGO
    if GLOBAL_MONGO is None:
        GLOBAL_MONGO = MongoClient(
            MONGO_URI, connectTimeoutMS=5000, serverSelectionTimeoutMS=5000
        )
    return GLOBAL_MONGO[MONGO_DB]


def load_model():
    global GLOBAL_MODEL
    if GLOBAL_MODEL is not None:
        return GLOBAL_MODEL

    candidates = [
        MODEL_PATH,
        "/models/model.joblib",
        "ml/artifacts/model.joblib",
        "../ml/artifacts/model.joblib",
        "../../ml/artifacts/model.joblib",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                GLOBAL_MODEL = joblib.load(path)
                print(f"[Spark ML] Modele charge avec succes depuis {path}", flush=True)
                return GLOBAL_MODEL
            except Exception as e:
                print(f"[Spark ML] Erreur chargement modele depuis {path}: {e}", flush=True)

    print(
        "[Spark ML WARN] Aucun modele joblib trouve. Ingestion avec fallback heuristique.",
        flush=True,
    )
    return None


def parse_iso(ts_str):
    if ts_str is None:
        return datetime.now(timezone.utc)
    try:
        if pd.isna(ts_str):
            return datetime.now(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        clean_ts = str(ts_str).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(clean_ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.now(timezone.utc)


def safe_float(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=1):
    try:
        if value is None or pd.isna(value):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_str(value, default=""):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value)
    return default if text.lower() == "nan" else text


def make_score_udf(model_bc):
    """Construit la pandas_udf de scoring a partir du modele diffuse."""

    @F.pandas_udf(DoubleType())
    def _score(
        step: pd.Series,
        op_type: pd.Series,
        amount: pd.Series,
        oldbalanceOrg: pd.Series,
        newbalanceOrig: pd.Series,
        oldbalanceDest: pd.Series,
        newbalanceDest: pd.Series,
    ) -> pd.Series:
        index = step.index
        model = model_bc.value if model_bc is not None else None

        if model is None:
            probabilities = []
            for i in range(len(step)):
                tx_type = safe_str(op_type.iloc[i], "TRANSFER")
                tx_amount = safe_float(amount.iloc[i], 0.0)
                tx_new_orig = safe_float(newbalanceOrig.iloc[i], 0.0)
                suspicious = (
                    tx_type in ("TRANSFER", "CASH_OUT")
                    and tx_amount > 100000.0
                    and tx_new_orig == 0.0
                )
                probabilities.append(0.95 if suspicious else 0.01)
            return pd.Series(probabilities, index=index, dtype="float64")

        features = pd.DataFrame(
            {
                "step": step.fillna(1).astype("int64"),
                "type": op_type.fillna("TRANSFER").astype(str),
                "amount": amount.fillna(0.0).astype("float64"),
                "oldbalanceOrg": oldbalanceOrg.fillna(0.0).astype("float64"),
                "newbalanceOrig": newbalanceOrig.fillna(0.0).astype("float64"),
                "oldbalanceDest": oldbalanceDest.fillna(0.0).astype("float64"),
                "newbalanceDest": newbalanceDest.fillna(0.0).astype("float64"),
            },
            index=index,
        )
        probabilities = model.predict_proba(features[FEATURE_COLS])[:, 1]
        return pd.Series(probabilities, index=index, dtype="float64")

    return _score


def _tx_update(transaction_id, tx_doc):
    """Upsert d'une transaction avec latence calculee cote MongoDB.

    Le pipeline d'update en deux etapes mesure l'ecriture effective ($$NOW)
    sans second round-trip vers MongoDB. `pipeline_latency_ms` devient donc
    un vrai `produced_at -> written_at` pour les documents de streaming.
    """
    return UpdateOne(
        {"_id": transaction_id},
        [
            {"$set": tx_doc},
            {
                "$set": {
                    "written_at": "$$NOW",
                    "pipeline_latency_ms": {
                        "$toDouble": {
                            "$max": [0, {"$subtract": ["$$NOW", "$produced_at"]}]
                        }
                    },
                }
            },
        ],
        upsert=True,
    )


def process_batch(batch_df, batch_id):
    """Execute pour chaque micro-batch Spark Structured Streaming."""
    batch_df = batch_df.persist()
    total_count = batch_df.count()

    if total_count == 0:
        batch_df.unpersist()
        return

    pdf = batch_df.toPandas()
    if len(pdf) == 0:
        batch_df.unpersist()
        return

    valid_mask = pdf["transaction_id"].notna() & pdf["transaction_id"].astype(str).str.startswith("tx_")
    pdf_valid = pdf[valid_mask].copy()

    invalid_count = len(pdf) - len(pdf_valid)
    if invalid_count:
        sample_ids = (
            pdf.loc[~valid_mask, "transaction_id"].astype(str).head(5).tolist()
        )
        print(
            f"[batch {batch_id}] {invalid_count} message(s) invalide(s) ignore(s). "
            f"Exemples: {sample_ids}",
            flush=True,
        )

    if len(pdf_valid) == 0:
        batch_df.unpersist()
        return

    now_utc = datetime.now(timezone.utc)
    scored_at_iso = now_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    model = load_model()
    threshold = float(getattr(model, "threshold", 0.5)) if model is not None else 0.5
    model_version = (
        str(getattr(model, "model_version", "v1.0.0-fallback"))
        if model is not None
        else "v1.0.0-fallback"
    )

    # 1. Registre d'idempotence : trace d'audit, pas un verrou.
    #    Un rejeu Spark (meme batch_id) doit re-executer les ecritures ci-dessous,
    #    car celles-ci sont idempotentes (upserts + $set par batch).
    db = None
    if MONGO_ENABLED:
        db = get_mongo_db()
        try:
            db.processed_batches.insert_one(
                {
                    "_id": batch_id,
                    "processed_at": now_utc,
                    "record_count": total_count,
                }
            )
        except DuplicateKeyError:
            print(
                f"[batch {batch_id}] deja vu -> rejeu idempotent.",
                flush=True,
            )
        except Exception as e:
            print(f"[Spark Mongo Error] processed_batches verification: {e}", flush=True)
            batch_df.unpersist()
            raise

    # 2. Preparation des documents MongoDB
    tx_ops = []
    alert_ops = []
    bucket_counts = {}

    fraud_count = 0
    fraud_amount_total = 0.0
    latencies = []

    for row in pdf_valid.to_dict("records"):
        probability = safe_float(row.get("probability"), 0.0)
        is_fraud = bool(probability >= threshold)
        decision = "BLOCKED" if is_fraud else "ALLOWED"

        produced_at = parse_iso(row.get("produced_at"))
        latency_ms = max(0.0, (now_utc - produced_at).total_seconds() * 1000.0)
        latencies.append(latency_ms)

        transaction_id = safe_str(row.get("transaction_id"))
        tx_doc = {
            "step": safe_int(row.get("step"), 1),
            "type": safe_str(row.get("type"), "TRANSFER"),
            "amount": safe_float(row.get("amount"), 0.0),
            "oldbalanceOrg": safe_float(row.get("oldbalanceOrg"), 0.0),
            "newbalanceOrig": safe_float(row.get("newbalanceOrig"), 0.0),
            "oldbalanceDest": safe_float(row.get("oldbalanceDest"), 0.0),
            "newbalanceDest": safe_float(row.get("newbalanceDest"), 0.0),
            "nameOrig": safe_str(row.get("nameOrig"), ""),
            "nameDest": safe_str(row.get("nameDest"), ""),
            "probability": probability,
            "threshold": threshold,
            "is_fraud": is_fraud,
            "decision": decision,
            "model_version": model_version,
            "produced_at": produced_at,
            "scored_at": now_utc,
            "source": "stream",
        }
        # pipeline_latency_ms est calcule par MongoDB au moment de l'ecriture
        # effective (voir _tx_update), pas avant le bulk_write.
        tx_ops.append(_tx_update(transaction_id, tx_doc))

        if is_fraud:
            fraud_count += 1
            fraud_amount_total += tx_doc["amount"]
            alert_ops.append(
                UpdateOne(
                    {"_id": transaction_id},
                    {
                        "$set": {
                            "transaction_id": transaction_id,
                            "timestamp": scored_at_iso,
                            "scored_at": now_utc,
                            "type": tx_doc["type"],
                            "amount": tx_doc["amount"],
                            "oldbalanceOrg": tx_doc["oldbalanceOrg"],
                            "newbalanceOrig": tx_doc["newbalanceOrig"],
                            "oldbalanceDest": tx_doc["oldbalanceDest"],
                            "newbalanceDest": tx_doc["newbalanceDest"],
                            "nameOrig": tx_doc["nameOrig"],
                            "nameDest": tx_doc["nameDest"],
                            "probability": probability,
                            "model_version": model_version,
                            "decision": decision,
                        }
                    },
                    upsert=True,
                )
            )

        # Agregation fenetre 10s
        bucket_sec = (now_utc.second // 10) * 10
        bucket_key = now_utc.replace(second=bucket_sec, microsecond=0).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        bucket = bucket_counts.setdefault(
            bucket_key, {"total_tx": 0, "total_frauds": 0, "fraud_amount": 0.0}
        )
        bucket["total_tx"] += 1
        if is_fraud:
            bucket["total_frauds"] += 1
            bucket["fraud_amount"] += tx_doc["amount"]

    # 3. Ecritures idempotentes
    if MONGO_ENABLED and db is not None:
        try:
            if tx_ops:
                db.transactions.bulk_write(tx_ops, ordered=False)
            if alert_ops:
                db.fraud_alerts.bulk_write(alert_ops, ordered=False)

            # Un seul bucket par batch : now_utc est fixe pour tout le micro-batch.
            # _id = batch_id + $set => un rejeu ecrase les memes compteurs
            # au lieu de les incrementer une seconde fois.
            for bucket_key, bucket_value in bucket_counts.items():
                db.stats_buckets.update_one(
                    {"_id": batch_id},
                    {
                        "$set": {
                            "batch_id": batch_id,
                            "bucket_start": bucket_key,
                            "total_tx": bucket_value["total_tx"],
                            "total_frauds": bucket_value["total_frauds"],
                            "fraud_amount": bucket_value["fraud_amount"],
                            "model_version": model_version,
                        }
                    },
                    upsert=True,
                )
        except Exception as e:
            print(f"[Spark Mongo Write Error] {e}", flush=True)
            batch_df.unpersist()
            raise

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    mongo_state = "ON" if MONGO_ENABLED and db is not None else "OFF"
    print(
        f"[batch {batch_id}] Traite : {len(pdf_valid)} tx | Fraudes : {fraud_count} "
        f"| Montant bloque : {fraud_amount_total:,.2f} $ | Latence scoring moy : {avg_latency:.1f} ms "
        f"| Mongo : {mongo_state}",
        flush=True,
    )

    batch_df.unpersist()


def main():
    print("Demarrage Spark Streaming Job...", flush=True)
    print(f"  Kafka: {KAFKA_BOOTSTRAP} (topic={KAFKA_TOPIC})", flush=True)
    print(f"  Mongo: {MONGO_URI} (db={MONGO_DB}, enabled={MONGO_ENABLED})", flush=True)
    print(f"  Model: {MODEL_PATH}", flush=True)

    builder = (
        SparkSession.builder.appName("fraud-streaming")
        .config("spark.sql.session.timeZone", "UTC")
        # Spark 3.5.1 : spark.streaming.stopGracefullyOnShutdown ne s'applique
        # qu'aux DStreams. Pour Structured Streaming, stopTimeout laisse au
        # micro-batch en cours le temps de se terminer proprement.
        .config("spark.sql.streaming.stopTimeout", "30000")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.sql.execution.arrow.maxRecordsPerBatch", "10000")
    )

    # Si le job n'est pas lance via spark-submit avec --master explicite
    if "SPARK_MASTER" in os.environ:
        builder = builder.master(os.environ["SPARK_MASTER"])

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    model = load_model()
    threshold = float(getattr(model, "threshold", 0.5)) if model is not None else 0.5
    model_version = (
        str(getattr(model, "model_version", "v1.0.0-fallback"))
        if model is not None
        else "v1.0.0-fallback"
    )
    model_bc = spark.sparkContext.broadcast(model) if model is not None else None
    print(f"  Seuil de decision: {threshold} | Version modele: {model_version}", flush=True)

    score_udf = make_score_udf(model_bc)

    # Lecture Kafka
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "earliest")
        .option("maxOffsetsPerTrigger", MAX_OFFSETS)
        .load()
    )

    # Parsing JSON + scoring distribue via pandas_udf
    parsed = (
        raw.select(
            F.col("key").cast("string").alias("kafka_key"),
            F.col("value").cast("string").alias("raw_json"),
            F.col("partition"),
            F.col("offset"),
        )
        .withColumn("data", F.from_json("raw_json", SCHEMA))
        .select("kafka_key", "data.*")
        .withColumn(
            "probability",
            score_udf(
                F.col("step"),
                F.col("type"),
                F.col("amount"),
                F.col("oldbalanceOrg"),
                F.col("newbalanceOrig"),
                F.col("oldbalanceDest"),
                F.col("newbalanceDest"),
            ),
        )
    )

    # Lancement Structured Streaming foreachBatch
    query = (
        parsed.writeStream.foreachBatch(process_batch)
        .option("checkpointLocation", CHECKPOINT)
        .trigger(processingTime=f"{TRIGGER_SECONDS} seconds")
        .start()
    )

    query.awaitTermination()


if __name__ == "__main__":
    main()
