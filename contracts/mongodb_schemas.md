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
| `pipeline_latency_ms`| Double | `scored_at - produced_at` en ms | - | Non | Exposé en `latency_ms` |
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
* **Mapping API :** Le champ `scored_at` est renvoyé sous la clé `timestamp` (ISO 8601 UTC) dans l'endpoint `GET /api/v1/alerts/latest`.

### Collection 3 : `stats_buckets`
Stocke les métriques pré-agrégées par intervalle de temps (ex: fenêtre de 10 secondes).

* **Clé primaire :** `_id` = début de l'intervalle ISO (ex: `"2026-11-07T10:00:10Z"`).
* **Champs :**
  * `total_tx`: Nombre total de transactions traitées dans l'intervalle.
  * `total_frauds`: Nombre de fraudes détectées.
  * `fraud_amount`: Montant total des transactions frauduleuses.

### Collection 4 : `processed_batches` (Mécanisme d'Idempotence retenu)
Collection dédiée pour garantir l'idempotence stricte lors de l'exécution de `foreachBatch(micro_batch_df, batch_id)` par Spark Structured Streaming :

* **Clé primaire :** `_id` = `batch_id` (entier ou chaîne fourni par le moteur Spark).
* **Champs :**
  * `processed_at`: Date d'enregistrement ISO UTC.
  * `record_count`: Nombre de transactions dans le micro-batch.
* **Règle de traitement Spark :**
  Avant d'écrire dans `transactions`, `fraud_alerts` et de mettre à jour `stats_buckets` :
  1. Spark tente d'insérer `{ _id: batch_id, processed_at: now, record_count: count }` dans `processed_batches`.
  2. Si l'insertion échoue par violation de clé unique (doublon `E11000 duplicate key error`), cela signifie que le micro-batch a déjà été validé : **Spark ignore l'écriture et termine le micro-batch sans ré-incrémenter les stats**.
  3. Cette approche résout définitivement le risque de sur-comptage sans nécessiter de verrouillage complexe.
