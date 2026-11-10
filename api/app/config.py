"""Configuration de l'API via variables d'environnement."""
import os


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


MODEL_PATH = os.getenv("MODEL_PATH", "ml/artifacts/model.joblib")
# MOCK_MODE=1 : stats/alertes/simulateur simulés en mémoire (dev front sans infra).
# Le champ "mode" de /health vaut alors "mock" (scénario de recette n°1 : doit être "real").
MOCK_MODE = _bool("MOCK_MODE")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "fraud")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "transactions_stream")
SIMULATOR_URL = os.getenv("SIMULATOR_URL", "http://simulator:8001")

# Largeur (secondes) d'un document de stats_buckets écrit par Spark.
STATS_BASE_BUCKET_SECONDS = int(os.getenv("STATS_BASE_BUCKET_SECONDS", "10"))

# Origines autorisées (CORS), séparées par des virgules.
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5500,http://127.0.0.1:5500"
).split(",") if o.strip()]
