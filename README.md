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
| `frontend` | Dashboard React / Vite (Supervision temps réel) | `8080` |
| `api` | API REST FastAPI (Inférence synchrone & stats) | `8000` (`/docs`) |
| `kafka` | Bus de streaming temps réel (mode KRaft) | `9092` (interne) / `29092` (hôte) |
| `spark-master` | Ordonnanceur Spark | `8082` (UI) |
| `spark-worker` | Exécuteur Spark (2 cœurs, 1 Go RAM) | `8081` (UI interne) |
| `spark-job` | Job de streaming avec inférence XGBoost (`pandas_udf`) | `4040` (UI) |
| `mongo` | Stockage des transactions, alertes et statistiques | `27017` |
| `producer` | Simulateur de trafic à 500 tx/s | `8001` (`/status`) |

## Démarrage Rapide

```bash
# Lancement de l'ensemble de la stack
docker compose up -d --build

# Suivi des logs du job Spark
docker compose logs -f spark-job
```

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
```

## Contrats d'Interface (Handoff P3)

Le dossier [`contracts/`](./contracts/) contient les spécifications convenues pour l'équipe :
* [`kafka_message.schema.json`](./contracts/kafka_message.schema.json) : Schéma JSON des messages Kafka.
* [`mongodb_schemas.md`](./contracts/mongodb_schemas.md) : Modèles des documents, index et règles d'agrégation.
* [`openapi.yaml`](./contracts/openapi.yaml) : Spécification OpenAPI 3.0 des endpoints FastAPI.
* [`common_versions.env`](./contracts/common_versions.env) : Versions figées des dépendances.
