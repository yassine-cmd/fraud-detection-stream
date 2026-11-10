# Spécification et Contrats des Collections MongoDB

Ce document définit formellement les collections, index, correspondances de champs et mécanismes d'idempotence pour MongoDB.

---

## 1. Table de Correspondance Globale des Champs

| Champ interne MongoDB | Type BSON | Description | Présent dans `/stats` | Présent dans `/alerts/latest` | Présent dans `/predict` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `_id` | String | `transaction_id` unique (ex: `tx_8f3a9b1c-...`) | - | `transaction_id` | `transaction_id` |
| `step` | Int32 | Pas de temps PaySim | - | Non | Non |
| `type` | String | Type d'opération bancaire | - | `type` | Non |
| `amount` | Double | Montant de la transaction | - | `amount` | Non |
| `oldbalanceOrg` | Double | Solde initial émetteur | - | Non | Non |
| `newbalanceOrig` | Double | Solde final émetteur | - | Non | Non |
| `oldbalanceDest` | Double | Solde initial destinataire | - | Non | Non |
| `newbalanceDest` | Double | Solde final destinataire | - | Non | Non |
| `nameOrig` / `nameDest` | String | Identifiants comptes (optionnels) | - | Non | Non |
| `probability` | Double | Probabilité prédite de fraude ($[0.0, 1.0]$) | - | `probability` | `probability` |
| `threshold` | Double | Seuil de coupure appliqué (ex: 0.35) | - | Non | `threshold` |
| `is_fraud` | Boolean | `true` si `probability >= threshold` | - | Non | `is_fraud` |
| `decision` | String | `"BLOCKED"` si `is_fraud`, sinon `"ALLOWED"` | - | `decision` | `decision` |
| `model_version` | String | Version du modèle (ex: `"v1.0.0"`) | - | `model_version` | `model_version` |
| `produced_at` | Date | Horodatage de publication Kafka | - | Non | Non |
| `scored_at` | Date | Horodatage d'inférence (Spark ou API) | - | Exposé en `timestamp` | Exposé en `timestamp` |
| `written_at` | Date | Horodatage d'écriture effective dans MongoDB (`$$NOW`, flux Spark uniquement) | - | Non | Non |
| `pipeline_latency_ms`| Double | Flux Spark : `written_at - produced_at` (écriture effective). API : `scored_at - produced_at` (inférence) | - | Non | Exposé en `latency_ms` |
| `source` | String | `"stream"` (Spark) ou `"api"` (si `persist=true`) | - | Non | Non |

---

## 2. Spécification des Collections

### Collection 1 : `transactions`
Contient l'historique complet des transactions scorées par Spark (`source: "stream"`) et par l'API (`source: "api"`, uniquement lorsque `POST /predict?persist=true`).

* **Clé primaire :** `_id` = `transaction_id` (upsert idempotent).
* **Index obligatoires :**
  1. `{ "scored_at": -1 }` : tri temporel et fenêtrage.
  2. `{ "is_fraud": 1, "scored_at": -1 }` : filtrage direct des fraudes récentes.
  3. *(Optionnel pour les démonstrations)* `{ "scored_at": 1 }` avec TTL `{ expireAfterSeconds: 86400 }` (purge après 24h).

### Collection 2 : `fraud_alerts`
Stocke exclusivement les transactions dont la décision est `BLOCKED`.

* **Clé primaire :** `_id` = `transaction_id`.
* **Index obligatoire :** `{ "scored_at": -1 }`.
* **Champ `decision` :** chaque alerte est écrite avec `decision: "BLOCKED"`.
* **Mapping API :** Le champ `scored_at` est renvoyé sous la clé `timestamp` (ISO 8601 UTC) dans l'endpoint `GET /api/v1/alerts/latest`.

### Collection 3 : `stats_buckets`
Stocke les métriques agrégées par micro-batch Spark (fenêtre de 10 secondes).

* **Clé primaire :** `_id` = `batch_id` (entier fourni par Spark).
* **Champs :**
  * `batch_id`: Identifiant du micro-batch Spark.
  * `bucket_start`: Début de l'intervalle de **processing time** (horloge du driver Spark), arrondi à 10 s (ex: `"2026-11-07T10:00:10Z"`). Ce n'est pas l'event time.
  * `total_tx`: Nombre total de transactions traitées dans le micro-batch.
  * `total_frauds`: Nombre de fraudes détectées.
  * `fraud_amount`: Montant total des transactions frauduleuses.
  * `model_version`: Version du modèle utilisée pour le micro-batch.
* **Index :** `{ "bucket_start": 1 }` pour la série temporelle de l'API.
* **Écriture idempotente :** `update_one({"_id": batch_id}, {"$set": {...}}, upsert=True)`.
  Un rejeu du même micro-batch écrase les mêmes compteurs au lieu de les incrémenter
  une seconde fois. Il y a exactement un bucket par batch car l'horodatage `now_utc`
  est fixé pour tout le micro-batch.
* **Lecture API :** `GET /stats` et `GET /stats/timeseries` agrègent les documents
  avec `$sum` sur `total_tx` / `total_frauds` / `fraud_amount`, groupés par
  `bucket_start` pour la série temporelle.
* **Migration :** ce schéma remplace l'ancien `_id = bucket_start` avec `$inc`.
  Vider `stats_buckets` avant le premier run pour éviter de mélanger les deux
  formats dans les agrégations.
* **Rétention :** le TTL MongoDB ne s'applique qu'à `transactions` et `fraud_alerts`.
  `stats_buckets` et `processed_batches` sont conservés pour l'audit ; les totaux
  `/stats` restent donc cumulés sur toute la durée de vie de la base. Après purge
  TTL, `/stats` peut dépasser `transactions.countDocuments()` : c'est intentionnel.
  `processed_batches` croît d'un document par micro-batch ; pour un run très long,
  prévoir un archivage ou une purge manuelle.

### Collection 4 : `processed_batches` (registre d'audit)
Collection dédiée à la traçabilité des micro-batches exécutés par
`foreachBatch(micro_batch_df, batch_id)` :

* **Clé primaire :** `_id` = `batch_id` (entier fourni par le moteur Spark).
* **Champs :**
  * `processed_at`: Date d'enregistrement ISO UTC.
  * `record_count`: Nombre de transactions dans le micro-batch.
* **Règle de traitement Spark :**
  1. Spark insère `{ _id: batch_id, processed_at: now, record_count: count }` dans `processed_batches`.
  2. Si l'insertion échoue par violation de clé unique (`E11000 duplicate key error`),
     le micro-batch est un **rejeu** : Spark journalise l'événement et **ré-exécute
     les écritures**. Celles-ci sont idempotentes (`upsert` par `_id` et `$set` par batch),
     donc le rejeu ne produit ni doublon ni sur-comptage.
  3. Le registre est une trace d'audit, pas un verrou : il ne doit jamais provoquer
     l'abandon des écritures.
* **Remise à zéro :** lorsqu'on supprime le checkpoint Spark, les `batch_id`
  repartent à 0. Il faut alors vider **les quatre collections** (`transactions`,
  `fraud_alerts`, `stats_buckets`, `processed_batches`) avant de relancer le job,
  sinon les premiers batches du nouveau run seraient considérés comme des rejeux
  (sans perte grâce aux upserts, mais avec des métriques mélangées à l'ancien run).

### Règle générale : `_id` immuable
Les `UpdateOne({"_id": ...}, {"$set": ...}, upsert=True)` ne doivent **jamais**
inclure `_id` dans le `$set`. Le filtre positionne `_id` à l'insertion ; le
répéter dans `$set` provoque `ImmutableField` sur un document existant.
