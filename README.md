# Plateforme Big Data de Détection de Fraude en Flux

Plateforme temps réel distribuée de détection de transactions frauduleuses basée sur Apache Kafka, Apache Spark Structured Streaming, MongoDB et FastAPI.

## Rôles dans l'équipe

* **Personne 1 (ML / Data Science) :** Préparation PaySim, équilibrage des classes, entraînement des modèles (LogReg, Random Forest, XGBoost), export du pipeline composite `model.joblib` et test de consistance API/Spark.
* **Personne 2 (Big Data Engineer) :** Infrastructure Docker Compose, bus Kafka KRaft, simulateur de transactions, job Spark Streaming et persistance idempotente dans MongoDB.
* **Personne 3 (API REST & Front-End) :** API FastAPI (prédiction unitaire synchrone, injection Kafka, métriques), Swagger UI et tableau de bord de supervision temps réel.

## Contrats d'interface (Source de vérité)

Le dossier [`contracts/`](./contracts/) contient les spécifications formelles convenues dès le premier jour :
* [`kafka_message.schema.json`](./contracts/kafka_message.schema.json) : Contrat du message JSON publié sur le topic `transactions_stream`.
* [`mongodb_schemas.md`](./contracts/mongodb_schemas.md) : Modèles des documents, index et mécanisme d'idempotence (`processed_batches`).
* [`openapi.yaml`](./contracts/openapi.yaml) : Spécification OpenAPI 3.0 des endpoints de l'API FastAPI.
* [`common_versions.env`](./contracts/common_versions.env) : Versions figées de Python, scikit-learn, XGBoost et pandas pour éviter tout décalage de sérialisation `joblib`.

## Démarrage Docker (stack complète)

```bash
docker compose up -d --build
```

| Service | URL |
| :--- | :--- |
| Dashboard Streamlit | http://localhost:8501 |
| API FastAPI / Swagger | http://localhost:8000/docs |
| Spark Master UI | http://localhost:8080 |
| Simulateur Kafka (contrôle) | http://localhost:8001/status |

Le simulateur lit `streaming/data_sample/test_stream.csv`, publie dans Kafka
(`transactions_stream`) et Spark applique `ml/artifacts/model.joblib` via une
`pandas_udf`. Les variables `RATE`, `FRAUD_RATIO`, `MONGO_ENABLED` et
`MAX_OFFSETS_PER_TRIGGER` sont configurables dans `docker-compose.yml`.

## MongoDB : rôle, stockage et rétention

MongoDB est la couche de persistance et de serving, pas le moteur de streaming :

`Producer -> Kafka -> Spark -> MongoDB -> FastAPI -> Streamlit`

Spark écrit les résultats scorés dans MongoDB ; l'API lit MongoDB pour
`/alerts/latest`, `/stats` et `/stats/timeseries`.

### Collections et stratégie

| Collection | Rôle | Clé | Écriture |
| :--- | :--- | :--- | :--- |
| `transactions` | Historique complet des transactions scorées | `_id = transaction_id` | upsert |
| `fraud_alerts` | Uniquement les transactions `BLOCKED` | `_id = transaction_id` | upsert |
| `stats_buckets` | Métriques pré-agrégées par fenêtre de 10 s | `_id = début ISO` | `$inc` |
| `processed_batches` | Registre d'idempotence des micro-batches | `_id = batch_id` | insert |

* `transactions` : un document dénormalisé par transaction (features,
  probabilité, décision, modèle, timestamps, latence).
* `fraud_alerts` : duplication volontaire des fraudes pour accélérer
  `GET /api/v1/alerts/latest`.
* `stats_buckets` : pré-agrégation à l'écriture pour éviter de scanner
  `transactions` à chaque rafraîchissement du dashboard.
* `processed_batches` : inséré avant les écritures ; un doublon `E11000`
  signifie que le batch a déjà été traité.

Les écritures utilisent `bulk_write(ordered=False)` et des upserts par `_id`.
Le registre `processed_batches` évite le double comptage des `stats_buckets`
lors d'un rejeu Spark.

### Un seul nœud ou cluster ?

Un **nœud unique standalone** suffit pour ce projet : volume de démonstration,
pas de besoin de transactions multi-documents ni de sharding. Un replica set
**1 nœud** ne serait utile que pour activer les transactions multi-documents
ou les change streams. Un cluster multi-nœuds est inutile ici et coûteux en RAM.

### Rétention configurable

`MONGO_TTL_SECONDS` contrôle la purge automatique :

* `86400` (défaut) : 24 h ;
* `3600` : 1 h ;
* `0` : aucune purge (rétention infinie).

La TTL s'applique à `transactions.scored_at` et `fraud_alerts.scored_at`.
`stats_buckets` et `processed_batches` restent volontairement non purgés
(volume faible, et suppression risquée pour l'idempotence).

Configurer via `.env` (copier `.env.example`) ou une variable d'environnement :

```powershell
Copy-Item .env.example .env
# modifier MONGO_TTL_SECONDS dans .env
docker compose up -d mongo mongo-config
```

Le service `mongo-config` rejoue `streaming/mongo-init.js` à chaque
`docker compose up` : il crée les collections/index et met à jour la TTL sans
recréer le volume. Le service `mongo` monte aussi ce script dans
`/docker-entrypoint-initdb.d/` pour la première initialisation.

### Vérification (quand Docker sera lancé)

```bash
docker compose up -d mongo mongo-config
docker exec -it mongo mongosh fraud --eval "db.getCollectionNames()"
docker exec -it mongo mongosh fraud --eval "db.transactions.getIndexes()"
docker exec -it mongo mongosh fraud --eval "db.fraud_alerts.getIndexes()"
docker exec -it mongo mongosh fraud --eval "db.stats_buckets.find().sort({_id:-1}).limit(3)"
```

## Exécution locale avec PySpark

PySpark peut être lancé directement sur la machine hôte, sans le conteneur
`spark-job`. Kafka et MongoDB restent accessibles via Docker :

```bash
docker compose up -d kafka kafka-init mongo
```

Puis, depuis la racine du projet (PowerShell) :

```powershell
$env:KAFKA_BOOTSTRAP="localhost:29092"
$env:MONGO_URI="mongodb://localhost:27017"
$env:MODEL_PATH="ml/artifacts/model.joblib"
$env:CHECKPOINT_DIR="./checkpoint"
# Optionnel : tester Kafka + Spark sans MongoDB
# $env:MONGO_ENABLED="false"

spark-submit --master "local[*]" `
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.3.0 `
  streaming/spark_job/streaming_job.py
```

> Le connecteur Kafka doit correspondre à la version de Spark et à l'échelle
> Scala installées. Docker utilise Spark 3.5.1 / Scala 2.12
> (`spark-sql-kafka-0-10_2.12:3.5.1`) ; un PySpark 4.x utilise Scala 2.13
> (`spark-sql-kafka-0-10_2.13:4.x`).
>
> PySpark 4.x exige Java 17/21 et `pyarrow >= 18`. L'image Docker Spark 3.5.1
> utilise Java 17 et `pyarrow==17.0.0` (versions figées du contrat). Si le
> couple PySpark/Java local n'est pas stable, utiliser la stack Docker.

## Configuration du Master et des Workers Spark

* **Dans Docker** : `spark-master` lance
  `org.apache.spark.deploy.master.Master` et `spark-worker` lance
  `org.apache.spark.deploy.worker.Worker spark://spark-master:7077`.
  Le job se connecte avec `--master spark://spark-master:7077`.
  Les ressources se règlent via `SPARK_WORKER_CORES`, `SPARK_WORKER_MEMORY`
  et les options `spark.executor.memory` / `spark.driver.memory`.
* **En local (cluster standalone)** : lancer le master puis un worker :

```powershell
& "$env:SPARK_HOME\bin\spark-class.cmd" org.apache.spark.deploy.master.Master
& "$env:SPARK_HOME\bin\spark-class.cmd" org.apache.spark.deploy.worker.Worker spark://localhost:7077
```

  Puis utiliser `--master spark://localhost:7077` dans `spark-submit`.
  L'UI du master est sur http://localhost:8080 et celle du worker sur
  http://localhost:8081.
* **En local (mode simple)** : `--master "local[*]"` crée un master virtuel
  utilisant tous les cœurs de la machine, sans worker séparé.
