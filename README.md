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
