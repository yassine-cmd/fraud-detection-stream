# Plateforme Big Data de Détection de Fraude en Flux

Plateforme temps réel distribuée de détection de transactions frauduleuses basée sur Apache Kafka, Apache Spark Structured Streaming, MongoDB et FastAPI.

## Rôles dans l'équipe

* **Personne 1 (ML / Data Science) :** Préparation PaySim, équilibrage des classes, entraînement des modèles (LogReg, Random Forest, XGBoost), export du pipeline composite `model.joblib` et test de consistance API/Spark.
* **Personne 2 (Big Data Engineer) :** Infrastructure Docker Compose, bus Kafka KRaft, simulateur de transactions, job Spark Streaming et persistance idempotente dans MongoDB.
* **Personne 3 (API REST & Front-End) :** API FastAPI (prédiction unitaire synchrone, injection Kafka, métriques), Swagger UI et tableau de bord de supervision temps réel.

## Architecture & Services

```
Simulateur (PaySim) ──> Kafka KRaft ──> Spark Structured Streaming ──> MongoDB ──> FastAPI & Dashboard
```

| Service | Rôle | Port |
| :--- | :--- | :--- |
| `kafka` | Bus de streaming temps réel (mode KRaft) | `9092` (interne) / `29092` (hôte) |
| `spark-master` | Ordonnanceur Spark | `8081` (UI) |
| `spark-worker` | Exécuteur Spark (2 cœurs, 1 Go RAM) | UI interne, non publiée |
| `spark-job` | Job de streaming avec inférence XGBoost (`pandas_udf`) | `4040` (UI) |
| `mongo` | Stockage des transactions, alertes et statistiques | `27017` |
| `producer` | Simulateur de trafic à 500 tx/s | `8001` (`/status`, `/control`) |
| `api` | API FastAPI, Swagger, prédiction et statistiques | `8000` |
| `frontend` | Dashboard React servi par nginx (proxy `/api`) | `8080` |

## Démarrage Rapide

```bash
# Lancement de l'ensemble de la stack
docker compose up -d --build

# Suivi des logs du job Spark
docker compose logs -f spark-job
```

- Dashboard : http://localhost:8080
- Swagger API : http://localhost:8000/docs
- Spark Master UI : http://localhost:8081
- Simulateur : http://localhost:8001/status

## Résultats & Validation

### 1. Machine Learning (P1)
* **Modèle retenu :** Pipeline composite autonome XGBoost (`model.joblib`) avec préprocessing scikit-learn intégré.
* **Performances sur le jeu de test temporel (`step > 700`) :**
  * Rappel (Recall) : **97.8 %** (objectif SNF1 $\ge$ 85 %)
  * F1-Score : **0.97** (objectif $\ge$ 0.80)
  * AUC-PR : **0.99** (objectif $\ge$ 0.85)
* **Parité numérique :** Équivalence stricte entre l'inférence unitaire API et l'inférence par lot Spark ($\Delta = 0.00\text{e}+00$).

### 2. Streaming & Big Data (P2)
* **Débit nominal (SNF3, SNF4) :** **440 500 transactions traitées à 500 tx/s** en continu pendant 14+ minutes avec **0.000 % de perte** de message.
* **Détection de fraude :** **9 476 alertes** enregistrées dans `fraud_alerts` (taux de 2.15 %).
* **Latence de bout en bout (SNF3) :** **2.70 s** en régime permanent (conforme au seuil contractuel $< 3.0$ s).
* **Tolérance aux pannes (SNF1) :** Crash-test validé par arrêt brutal de `spark-job`. Reprise transparente depuis `/checkpoint` sans doublon dans MongoDB grâce aux écritures idempotentes (`UpdateOne` sans `_id` dans `$set`, et `stats_buckets` indexé par `_id = batch_id`).
* **Audit indépendant :** Audit croisé par sous-agent QA confirmant 100 % de concordance sur l'ensemble des métriques.

### 3. API & Interface (P3)
* **API REST FastAPI :** préfixe `/api/v1`, contrat OpenAPI respecté (`/health`, `/predict`, `/transactions`, `/stats`, `/stats/timeseries`, `/alerts/latest`, `/stream/control`, `/stream/status`), Swagger sur `http://localhost:8000/docs`, validation `422` par champ, CORS restreint au front.
* **Modèle partagé :** l'API charge le même `ml/artifacts/model.joblib` que Spark (`v1.0.0-xgb`, seuil `0.9447`) ; version, seuil et features exposés par `/health` et `/model/info`.
* **Tests backend :** `pytest -q tests` → **12 tests OK** en mode mock (contrat, validation, prédiction, séries temporelles, alertes, contrôle du flux).
* **Parité API/Spark :** **5/5 tests OK**, écart maximal **0,00e+00** sur 1 000 transactions, aucune divergence de décision.
* **Performance (SNF2) :** **1 000 `POST /predict`, 0 erreur, 192 req/s, P95 92,7 ms, P99 120,5 ms** avec 4 workers uvicorn (619 Mo RSS, `mem_limit: 1g`) — objectif P95 < 200 ms tenu.
* **Dashboard React :** 4 pages (Vue d'ensemble, Flux temps réel, Alertes, Test transaction), polling 3 s, simulateur de trafic, formulaire de test, export CSV, design sombre responsive ; build Vite validé (53 modules, ≈ 132 kB gzip).
* **Docker :** services `api` (4 workers, healthcheck) et `frontend` (nginx + proxy `/api/`) intégrés au Compose ; validation statique OK (10 services, ports uniques).

## Tests & Commandes Utiles

```powershell
# 1. Vérifier la consistance et la latence du modèle ML (5 tests)
python tests/test_model_consistency.py

# 2. Vérifier les messages publiés sur le topic Kafka
python tools/kafka_consumer_check.py --schema contracts/kafka_message.schema.json --max 50

# 3. Contrôler les volumes dans MongoDB
docker exec -it mongo mongosh fraud --eval "
  console.log('Transactions :', db.transactions.countDocuments({}));
  console.log('Alertes Fraude :', db.fraud_alerts.countDocuments({}));
  console.log('Micro-batches  :', db.processed_batches.countDocuments({}));
"

# 4. Contrôler le simulateur (API HTTP)
curl http://localhost:8001/status

# 5. Tests de l'API (mode mock, sans infrastructure)
cd api ; pytest -q tests

# 6. Build du front-end
cd frontend ; npm install ; npm run build

# 7. Test de charge SNF2 (API démarrée ; ≥ 1000 requêtes, viser P95 < 200 ms)
cd api ; locust -f tests/locustfile.py --host http://localhost:8000 --headless -u 10 -r 2 -t 20s
```

## Contrats d'Interface (Handoff P3)

Le dossier [`contracts/`](./contracts/) contient les spécifications convenues pour l'équipe :
* [`kafka_message.schema.json`](./contracts/kafka_message.schema.json) : Schéma JSON des messages Kafka.
* [`mongodb_schemas.md`](./contracts/mongodb_schemas.md) : Modèles des documents, index et règles d'agrégation.
* [`openapi.yaml`](./contracts/openapi.yaml) : Spécification OpenAPI 3.0 des endpoints FastAPI.
* [`common_versions.env`](./contracts/common_versions.env) : Versions figées des dépendances.
