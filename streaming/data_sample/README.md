# Échantillon de Test pour Simulateur de Streaming (`test_stream.csv`)

Ce dossier contient les données de test réservées pour le producteur Kafka (`producer.py`) de **Personne 2** (Ingénieur Big Data).

---

## 1. Origine & Volumétrie des Données

* **Fichier :** `test_stream.csv`
* **Nombre de lignes :** 30 000 transactions (11 421 transactions sources uniques rejouées cycliquement).
* **Fraudes préservées :** 490 fraudes uniques (soit 100 % des fraudes du split de test), 1 124 occurrences au total.
* **Ratio de fraude :** 3.75 % (rejeu du split test à 4.29 %).
* **Découpage temporel :** $step > 700$ (conformément au Cahier des Charges §3.2 et §4.1).

### Pourquoi 30 000 lignes ?
Le split test pur ($step > 700$) contient exactement 11 421 transactions. Pour respecter le volume T1.3 (20 000 – 50 000 lignes) sans fuite temporelle, le fichier livré rejoue ce split 3 fois. Les 490 fraudes uniques sont préservées à chaque cycle. Le split pur de 11 421 lignes reste la référence d'évaluation (métriques de `metadata.json`) ; le rejeu ne sert qu'au simulateur.

---

## 2. Consignes d'Intégration pour Personne 2 (`producer.py`)

### A. Rejeu en boucle (Tâche T2.2)
Comme spécifié dans le Cahier des Charges (§5.2, exigence SF2 et tâche T2.2) :
* Pour atteindre les **300 000 messages requis sur 10 minutes** de streaming continu, le simulateur lit `test_stream.csv` **en boucle**.
* À chaque itération de la boucle, le producteur doit :
  1. Générer un nouvel identifiant unique `transaction_id` au format UUIDv4 préfixé (ex: `f"tx_{uuid.uuid4()}"`), utilisé comme clé de message Kafka (*Record Key*).
  2. Actualiser le champ `produced_at` à l'heure courante UTC au format ISO 8601 avec millisecondes et suffixe `Z` (ex: `datetime.now(timezone.utc).isoformat()`).

### B. Filtrage obligatoire des colonnes (Contrat Kafka JSON Schema)
Le fichier `test_stream.csv` conserve les colonnes `isFraud` et `isFlaggedFraud` afin de permettre au simulateur d'ajuster dynamiquement le `fraud_ratio` en mode démo (ex: forcer 2 % de fraudes).

> [!CAUTION]
> Le contrat de message JSON ([`contracts/kafka_message.schema.json`](../../contracts/kafka_message.schema.json)) impose `"additionalProperties": false`.
> Le simulateur **DOIT filtrer** et ne jamais inclure `isFraud` ni `isFlaggedFraud` dans le corps du message JSON envoyé à Kafka.

#### Colonnes autorisées dans le payload Kafka :
```json
{
  "transaction_id": "tx_c3b5d2e1-4f8a-4d9b-a1c2-3e4f5a6b7c8d",
  "step": 701,
  "type": "TRANSFER",
  "amount": 181.0,
  "nameOrig": "C123456789",
  "oldbalanceOrg": 181.0,
  "newbalanceOrig": 0.0,
  "nameDest": "C987654321",
  "oldbalanceDest": 0.0,
  "newbalanceDest": 0.0,
  "produced_at": "2026-11-07T14:30:00.123Z"
}
```
*(Les colonnes `nameOrig` et `nameDest` sont optionnelles mais acceptées par le schéma ; `isFraud` et `isFlaggedFraud` sont strictement interdites).*

---

## 3. Régénération du Fichier

```bash
python ml/src/extract_stream_data.py --target-rows 30000
```
Pour exporter le split pur de 11 421 lignes : `--target-rows 0`.
