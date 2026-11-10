# Documentation — Partie API & Front-End (branche `feature/fullstack`)

Responsable : [Nom 3] — Projet N°6, Détection de fraude en flux (cahier des charges §4.2, §4.3, §5, SF4–SF9).

## 1. Contenu

| Dossier | Rôle |
|---|---|
| `api/app/` | API FastAPI (`main.py` endpoints, `schemas.py` contrat, `model.py` inférence, `backends.py` Mongo/Kafka/simulateur + mode mock) |
| `api/model/model.joblib` | Modèle **fictif** v0.1.0-dummy (régression logistique), à remplacer par le modèle de [Nom 1] |
| `api/tests/` | Tests pytest (`test_api.py`) et test de charge Locust (`locustfile.py`, SNF2) |
| `frontend/` | **React 18 + Vite + Chart.js** (`src/App.jsx`, `components/Dashboard`, `TestForm`, `SimulatorPanel`, `AlertsTable`, `TrafficChart`, hook `usePolling`) ; build servi par nginx |
| `docker-compose.dev.yml` | Dev local API + front en mode mock |

## 2. Lancer

**Sans Docker (dev)**
```powershell
cd api
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:MOCK_MODE="1"; $env:CORS_ORIGINS="http://localhost:8080"
uvicorn app.main:app --reload --port 8000
# autre terminal
cd frontend ; npm install ; npm run dev   # http://localhost:8080
```
Front : http://localhost:8080 — Swagger : http://localhost:8000/docs

**Avec Docker** : `docker compose -f docker-compose.dev.yml up -d --build`

**Tests** : `cd api ; pytest -q tests`

## 3. Configuration (variables d'environnement de l'API)

| Variable | Défaut | Description |
|---|---|---|
| `MOCK_MODE` | `0` | `1` = données simulées en mémoire, `/health` → `mode:"mock"`. **Doit être `0` pour la recette (scénario 1)** |
| `MODEL_PATH` | `model/model.joblib` | Pipeline sklearn exporté |
| `MONGO_URI` / `MONGO_DB` | `mongodb://mongo:27017` / `fraud` | |
| `KAFKA_BOOTSTRAP` / `KAFKA_TOPIC` | `kafka:9092` / `transactions_stream` | |
| `SIMULATOR_URL` | `http://simulator:8001` | Serveur HTTP de contrôle du simulateur |
| `STATS_BASE_BUCKET_SECONDS` | `10` | Largeur des documents `stats_buckets` écrits par Spark |
| `CORS_ORIGINS` | `localhost:8080, 5500` | Origines du front autorisées |

Le front lit l'URL de l'API dans `frontend/public/config.js` (`API_BASE`, `POLL_MS`), fichier copié tel quel dans le build : modifiable sans rebuild.

## 4. Endpoints (préfixe `/api/v1`)

Conformes au §5.3. Particularités d'implémentation :

- `POST /predict?persist=false` — en mémoire, sans Kafka. `persist=true` écrit dans `transactions` (`source:"api"`, upsert sur `_id`). Mesuré en local (mode dummy, 300 requêtes via TestClient) : P95 ≈ 7 ms ; la vraie mesure Locust reste à faire (SNF2).
- `POST /transactions` — ajoute `produced_at` (ISO UTC ms, `Z`), génère `tx_<uuid4>` si absent, publie avec **`transaction_id` comme clé Kafka**. Réponse `202 {"status":"queued", ...}`.
- `GET /stats`, `GET /stats/timeseries` — lisent **uniquement** `stats_buckets`. La série ré-agrège les buckets de base (10 s) selon `bucket` (jamais plus fin que le bucket de base).
- `GET /alerts/latest?limit=20` — lit `fraud_alerts` trié par `scored_at` décroissant, exposé sous `timestamp`.
- `POST /stream/control`, `GET /stream/status` — relais vers le simulateur.
- `GET /health` — `status` = `healthy` seulement si modèle chargé **et** Kafka + MongoDB joignables ; sinon `degraded`.
- Erreurs : validation → 422 (détail par champ) ; dépendance indisponible → 503 avec message.

## 5. Points à valider avec l'équipe (hypothèses prises)

1. **Contrat HTTP du simulateur** (non défini dans le cahier des charges) : l'API appelle `POST {SIMULATOR_URL}/control` avec `{"action","rate_tx_per_sec","fraud_ratio"}` et `GET {SIMULATOR_URL}/status`, et attend `{"running":bool,"rate_tx_per_sec":int,"fraud_ratio":float,"sent":int?}`. → à confirmer avec [Nom 2].
2. **Règle de décision** : `probability >= threshold` → BLOCKED. Spark doit appliquer exactement la même règle.
3. **Largeur des buckets `stats_buckets`** : 10 s supposé (`STATS_BASE_BUCKET_SECONDS`), `_id` au format `YYYY-MM-DDTHH:MM:SSZ`.
4. **Seuil et version du modèle** : lus sur les attributs `threshold` et `model_version` de l'objet Pipeline (c'est ainsi que le `model.joblib` fourni les stocke). Le vrai modèle doit garder ce format, ou l'on adapte `app/model.py`.
5. **`scored_at` dans Mongo** : type `datetime` BSON attendu (nécessaire pour l'index TTL du §6.2) ; une chaîne est aussi tolérée en lecture.

## 6. Intégration dans le `docker-compose.yml` commun

```yaml
  api:
    build: ./api
    environment:
      MONGO_URI: mongodb://mongo:27017
      KAFKA_BOOTSTRAP: kafka:9092
      SIMULATOR_URL: http://simulator:8001
      CORS_ORIGINS: http://localhost:8080
    ports: ["8000:8000"]
    depends_on: [mongo, kafka]
    mem_limit: 512m
  frontend:
    build: ./frontend
    ports: ["8080:80"]
    mem_limit: 64m
```

## 7. Limites connues

- Le `model.joblib` actuel est un **modèle fictif** : il donne ~0,88 même pour un `PAYMENT` anodin, il ne discrimine pas. Les scénarios de recette 2 ne seront valides qu'avec le vrai modèle.
- `requirements.txt` fige scikit-learn 1.4.2 (version de sérialisation du modèle) ; à aligner avec l'image Spark et à compléter avec XGBoost.
- Tests faits en mode mock + vérification que le mode réel répond `degraded`/503 sans dépendances. **Non testé** avec de vrais Kafka/MongoDB/Spark.
- Le P95 de `/predict` sous Locust (≥ 1000 requêtes) et le test d'écart API/Spark (< 1e-5) restent à réaliser.
