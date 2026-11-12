"""Configuration de l'API via variables d'environnement.

Les valeurs par défaut correspondent au déploiement Docker Compose de l'équipe.
En développement local, surcharger MONGO_URI / KAFKA_BOOTSTRAP / SIMULATOR_URL.
"""
import os


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Chemin du pipeline composite (préprocessing + classifieur + seuil + version).
MODEL_PATH = os.getenv("MODEL_PATH", "ml/artifacts/model.joblib")
# Métadonnées exportées par l'équipe ML (métriques, version, features).
MODEL_METADATA_PATH = os.getenv("MODEL_METADATA_PATH", "")

# MOCK_MODE=1 : stats/alertes/simulateur simulés en mémoire (dev front sans infra).
# Le champ "mode" de /health vaut alors "mock" (scénario de recette n°1 : doit être "real").
MOCK_MODE = _bool("MOCK_MODE")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "fraud")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "transactions_stream")
SIMULATOR_URL = os.getenv("SIMULATOR_URL", "http://producer:8001")
SIMULATOR_TIMEOUT = float(os.getenv("SIMULATOR_TIMEOUT", "3.0"))

# Largeur (secondes) d'un document de stats_buckets écrit par Spark.
# Le job Spark actuel écrit un bucket par micro-batch (trigger 1 s) avec
# bucket_start arrondi à 10 s : la valeur 10 reste donc la granularité de base.
STATS_BASE_BUCKET_SECONDS = max(1, _int("STATS_BASE_BUCKET_SECONDS", 10))

# Origines autorisées (CORS), séparées par des virgules. "*" accepte tout.
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173,http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    if o.strip()
]
