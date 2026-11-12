# Documentation — Partie API & Front-End (branche `feature/fullstack`)

Responsable : [Nom 3] — Projet N°6, Détection de fraude en flux (cahier des charges §4.2, §4.3, §5, SF4–SF9, SNF1–SNF6).

## 1. Contenu

| Dossier | Rôle |
|---|---|
| `api/app/` | API FastAPI : `main.py` (routes), `schemas.py` (contrat Pydantic), `model.py` (chargement et inférence du pipeline), `backends.py` (MongoDB/Kafka/simulateur + mode mock) |
| `api/model/model.joblib` | Artefact de test léger (utilisé par pytest) ; l'API réelle charge `ml/artifacts/model.joblib` |
| `api/tests/` | Tests pytest (`test_api.py`) et test de charge Locust (`locustfile.py`, SNF2) |
| `frontend/` | SPA **React 18 + Vite + Chart.js**, 4 pages (Vue d'ensemble, Flux temps réel, Alertes, Test transaction), servie par nginx |
| `docker-compose.yml` | Stack complète ; services `api` et `frontend` ajoutés par la partie P3 |

## 2. Lancer

**Sans Docker (dev)**

```powershell
cd api
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:MOCK_MODE="1"
$env:CORS_ORIGINS="http://localhost:8080"
uvicorn app.main:app --reload --port 8000
# autre terminal
cd frontend ; npm install ; npm run dev   # http://localhost:8080
```

Front : http://localhost:8080 — Swagger : http://localhost:8000/docs

Avec Docker (stack complète) :

```bash
docker compose up -d --build
docker compose logs -f spark-job
```

- Frontend : http://localhost:8080 (nginx relaie `/api/` vers `api:8000`)
- API directe : http://localhost:8000/api/v1/health — Swagger : http://localhost:8000/docs
- Spark Master UI : http://localhost:8081 (8080 est réservé au frontend)
- Simulateur : http://localhost:8001/status

**Tests** : `cd api ; pytest -q tests`

## 3. Configuration (variables d'environnement de l'API)

| Variable | Défaut | Description |
|---|---|---|
| `MOCK_MODE` | `0` | `1` = données simulées en mémoire, `/health` → `mode:"mock"`. **Doit être `0` pour la recette (scénario 1)** |
| `MODEL_PATH` | `ml/artifacts/model.joblib` | Pipeline composite exporté (préprocessing + XGBoost) |
| `MODEL_METADATA_PATH` | `""` | Métadonnées JSON optionnelles (`metadata.json`) |
| `MONGO_URI` / `MONGO_DB` | `mongodb://mongo:27017` / `fraud` | Connexion MongoDB |
| `KAFKA_BOOTSTRAP` / `KAFKA_TOPIC` | `kafka:9092` / `transactions_stream` | Bus Kafka |
| `SIMULATOR_URL` | `http://producer:8001` | Serveur HTTP de contrôle du simulateur |
| `SIMULATOR_TIMEOUT` | `3.0` | Timeout HTTP du simulateur (secondes) |
| `STATS_BASE_BUCKET_SECONDS` | `10` | Largeur des documents `stats_buckets` écrits par Spark |
| `CORS_ORIGINS` | `localhost:8080, 127.0.0.1:8080, …` | Origines du front autorisées |

Le front lit l'URL de l'API dans `frontend/public/config.js` (`API_BASE`, `POLL_MS`), fichier copié tel quel dans le build : modifiable sans rebuild.

## 4. Endpoints (préfixe `/api/v1`)

Conformes au §5.3. Particularités d'implémentation :

- `GET /health` — `status` = `healthy` seulement si le modèle est chargé **et** Kafka + MongoDB joignables ; sinon `degraded`. Expose `mode`, `model_loaded`, `model_version`, `threshold`, `uptime_s`.
- `GET /model/info` — informations du modèle (version, type, seuil, features, métriques de test/validation). Endpoint de supervision, non contractuel.
- `POST /predict?persist=false` — inférence synchrone en mémoire, sans Kafka. `persist=true` écrit dans `transactions` (`source:"api"`, upsert sur `_id`) et calcule `pipeline_latency_ms`. La réponse contient `decision` (`BLOCKED`/`ALLOWED`), `probability`, `threshold`, `model_version` et `latency_ms`.
- `POST /transactions` — ajoute `produced_at` (ISO UTC ms, `Z`), génère `tx_<uuid4>` si absent, publie avec **`transaction_id` comme clé Kafka**. Réponse `202 {"status":"queued","transaction_id":...}`. Le job Spark ignore les identifiants qui ne commencent pas par `tx_`.
- `GET /stats` — compteurs cumulés lus dans `stats_buckets` (somme de `total_tx`, `total_frauds`, `fraud_amount`).
- `GET /stats/timeseries?window=15m&bucket=10s` — ré-agrège les buckets de base (10 s) selon `bucket` ; jamais plus fin que le bucket de base. Lecture de `bucket_start` (schéma réel Spark), pas de `_id`.
- `GET /stats/breakdown?window=15m` — répartition par type de transaction à partir de `transactions` (`scored_at`, `is_fraud`).
- `GET /stats/latency?window=15m` — percentiles P50/P95/P99 de `pipeline_latency_ms` (SNF3).
- `GET /alerts/latest?limit=20` — lit `fraud_alerts` trié par `scored_at` décroissant, exposé sous `timestamp`.
- `POST /stream/control`, `GET /stream/status` — relais vers le simulateur. Réponse normalisée : `is_running`, `rate_tx_per_sec`, `fraud_ratio`, `total_sent`, `total_delivered`, `errors_count`, `dataset_rows`, `last_error` (alias `running`/`sent` conservés pour compatibilité).
- Erreurs : validation → 422 (détail par champ) ; dépendance indisponible → 503 avec message.

## 5. Contrats réels utilisés

1. **Simulateur** : `POST {SIMULATOR_URL}/control` avec `{"action":"start|stop","rate_tx_per_sec":int,"fraud_ratio":float}` et `GET {SIMULATOR_URL}/status`. Le producteur renvoie `is_running`, `total_sent`, `total_delivered`, `errors_count`, `dataset_rows`, `last_error` ; l'API normalise ces champs et tolère les anciens noms `running`/`sent`.
2. **Décision** : `probability >= threshold` → `BLOCKED`. Spark applique exactement la même règle avec le même `model.joblib`.
3. **`stats_buckets`** : `_id = batch_id` (entier), temps porté par `bucket_start` (ISO `YYYY-MM-DDTHH:MM:SSZ`), compteurs `total_tx`, `total_frauds`, `fraud_amount`. L'API ne suppose plus que `_id` contient une date.
4. **`transactions` / `fraud_alerts`** : `scored_at` est un `datetime` BSON (index TTL du §6.2) ; `pipeline_latency_ms` est calculé côté MongoDB au moment de l'écriture.
5. **Modèle** : `model.joblib` = pipeline composite `v1.0.0-xgb` (XGBoost), seuil `0.9447`, features `step,type,amount,oldbalanceOrg,newbalanceOrig,oldbalanceDest,newbalanceDest`. Le seuil et la version sont lus sur le pipeline, avec repli sur `metadata.json`.

## 6. Frontend

- **Vue d'ensemble** : hero de pilotage, 4 KPI (transactions, fraudes, taux, montant protégé), courbe débit/fraudes (5 min / 15 min / 1 h), simulateur, santé système, dernières alertes, performance du modèle, répartition par type.
- **Flux temps réel** : débit estimé, messages envoyés/acquittés, erreurs Kafka, courbe, latence P50/P95/P99, chaîne Kafka → Spark → MongoDB → FastAPI.
- **Alertes fraude** : registre filtrable (recherche, type), export CSV, probabilité et seuil.
- **Test transaction** : formulaire complet (type, step, montants, soldes), presets fraude/normal/cash-out, évaluation synchrone (`/predict`), injection Kafka (`/transactions`), jauge de probabilité et seuil, réponse JSON.
- Polling rapide toutes les **3 s** (`/stats`, `/stats/timeseries`, `/alerts/latest`, `/stream/status`) et lent toutes les **15 s** (`/stats/breakdown`, `/stats/latency`). Aucune logique ML dans le front (SNF4).
- Design sombre « Sentinel Fraud Intelligence », responsive (sidebar desktop, bottom-nav mobile).

## 7. Intégration Docker Compose

```yaml
  api:
    build: ./api
    environment:
      MONGO_URI: mongodb://mongo:27017
      KAFKA_BOOTSTRAP: kafka:9092
      SIMULATOR_URL: http://producer:8001
      MODEL_PATH: /models/model.joblib
      MODEL_METADATA_PATH: /models/metadata.json
      CORS_ORIGINS: http://localhost:8080,http://127.0.0.1:8080
    volumes:
      - ./ml/artifacts:/models:ro
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
    ports: ["8000:8000"]
    depends_on: [mongo, kafka-init, producer]
    mem_limit: 1g
  frontend:
    build: ./frontend
    ports: ["8080:80"]
    depends_on:
      api:
        condition: service_healthy
    mem_limit: 64m
```

Le montage `./ml/artifacts:/models:ro` garantit que l'API et Spark utilisent **le même** `model.joblib` (parité des scores, §3.3). Le healthcheck de l'API interroge `/api/v1/health` ; nginx sert la SPA avec fallback `index.html`.

Le nombre de workers uvicorn du service `api` est piloté par `API_WORKERS` (défaut `4`, voir `.env.example`) : 1 worker par cœur physique améliore le P95 sous charge (SNF2). En mode mock (`docker-compose.dev.yml`), rester à **1 worker** pour conserver un état simulé cohérent entre les requêtes.

## 8. Résultats mesurés (validation locale)

- `pytest -q tests` : **12 tests OK** en mode mock (contrat, validation 422, prédiction, séries, stream, alertes).
- Smoke test du vrai modèle `ml/artifacts/model.joblib` (`v1.0.0-xgb`, seuil `0,9447`) : chargement OK ; fraude TRANSFER avec vidage du compte → `BLOCKED` (p = 0,9995) ; paiement normal → `ALLOWED` (p = 3,6e-5) ; CASH_OUT suspect → `BLOCKED` (p = 0,9971).
- `tests/test_model_consistency.py` : **5/5 tests OK** — écart maximal unitaire/batch **0,00e+00** sur 1 000 transactions (55 fraudes), **aucune divergence** de décision ; latence API **P50 7,7 ms / P95 8,8 ms / P99 9,8 ms** (< 200 ms, SNF2) ; débit batch 101 734 tx/s ; cas limites (montants nuls, type inconnu) évalués sans exception.
- Test de charge HTTP réel (`POST /api/v1/predict`, vrai `ml/artifacts/model.joblib`, uvicorn **4 workers**, 10 requêtes en vol, client asynchrone `httpx`) : **1 000 requêtes, 0 erreur, 192 req/s, P50 39,4 ms / P95 92,7 ms / P99 120,5 ms** — conforme à SNF2 (P95 < 200 ms sur ≥ 1 000 requêtes). Répartition identique des décisions (500 `BLOCKED`, 500 `ALLOWED`), empreinte mesurée **619 Mo RSS** pour les 4 workers (`mem_limit: 1g`).
- Sensibilité à la concurrence (même machine, 4 cœurs physiques / 8 logiques, i5-10210U) : 1 worker à 20 clients → 58 req/s et P95 387 ms ; 2 workers → 88 req/s et P95 236 ms ; 4 workers à 20 clients → 175 req/s et P95 226 ms (saturation CPU). Le P95 < 200 ms est tenu avec 4 workers à 10 clients simultanés ; au-delà, le goulot est le CPU du poste de validation, pas l'API.
- Build frontend : `npm run build` OK (53 modules, JS 374 kB, CSS 47 kB, gzip ≈ 132 kB).
- Contrôles HTTP réels : `/health` → `healthy`, `/docs` → 200, prédiction fraude → `BLOCKED`, `bucket=5s` → 422, `POST /transactions` → 202, en-tête CORS `http://localhost:8080` présent.
- Validation statique des fichiers Compose (10 services, ports hôtes uniques, dépendances et healthchecks cohérents) : OK. `docker compose config` n'a pas pu être exécuté, la CLI Docker étant absente de l'environnement de validation.

Ces mesures ont été réalisées avec l'interpréteur local Python 3.10 (scikit-learn 1.5, XGBoost 3.1). Les versions épinglées de l'image Docker (`scikit-learn 1.4.2`, `xgboost 2.0.3`) restent la référence de production et de démonstration.

## 9. Limites connues / reste à faire

- Le test de parité **cross-engine** sur le cluster Spark réel (`pandas_udf`) reste à exécuter ; le banc `tests/test_model_consistency.py` valide la parité unitaire/batch du même pipeline (écart nul mesuré).
- Le test de charge a été réalisé avec un client `httpx` asynchrone (Locust n'est pas installé dans l'environnement de validation) : 1 000 requêtes, 4 workers, P95 92,7 ms. La montée en charge au-delà de 10 clients simultanés sature le CPU du poste (P95 226 ms à 20 clients) ; sur une machine de démonstration plus puissante ou avec `API_WORKERS` ajusté, refaire la mesure pour le rapport final.
- Le mode réel (`MOCK_MODE=0`) a été validé en lecture sur les schémas Spark/Mongo ; un test de bout en bout avec Kafka + Spark + MongoDB démarrés reste à faire avant la soutenance.
- Les buckets `stats_buckets` sont indexés par `batch_id` : un redémarrage de Spark réutilise les mêmes `_id` et écrase les buckets précédents. Les compteurs `/stats` reflètent donc la dernière session de streaming (choix du job Spark, à discuter avec [Nom 2]).
- L'artefact `api/model/model.joblib` est un modèle de test (seuil 0,5) ; seul `ml/artifacts/model.joblib` doit être utilisé en démonstration.
