"""
Test de consistance numerique, reproductibilite et validation en conditions reelles.
Tache T1.6 : Equivalence d'inference entre API FastAPI (unitaire) et Spark (batch).

Criteres du Cahier des Charges (Section 7.3 & T1.6) :
  1. Comparaison des probabilites sur un echantillon de 1 000 transactions en float64.
  2. Ecart absolu maximal tolere strictement inferieur a 10^-5 (max_diff < 1e-5).
  3. Zero divergence sur la decision binaire (BLOCKED vs ALLOWED).
  4. Mesure de la latence unitaire P95 (< 200 ms, exigence SNF2).
  5. Robustesse face aux cas limites de production (montants nuls, vidage de compte, types inconnus).
"""

import logging
import sys
import time
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("test_model_consistency")

# Resolution automatique des chemins
REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = REPO_ROOT / "ml" / "artifacts" / "model.joblib"
METADATA_PATH = REPO_ROOT / "ml" / "artifacts" / "metadata.json"
TEST_STREAM_PATH = REPO_ROOT / "streaming" / "data_sample" / "test_stream.csv"
DATA_PARQUET_PATH = REPO_ROOT / "data" / "paysim.parquet"

# Ajout du dossier src pour la resolution des modules
SRC_PATH = REPO_ROOT / "ml" / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))


class TestModelConsistency(unittest.TestCase):
    """Suite de tests de consistance et de robustesse en conditions reelles."""

    @classmethod
    def setUpClass(cls):
        """Chargement du modele et des donnees d'echantillon."""
        logger.info(f"Chargement de l'artefact modele depuis {MODEL_PATH}...")
        cls.assertTrue(MODEL_PATH.exists(), f"Artefact introuvable : {MODEL_PATH}")
        cls.pipeline = joblib.load(MODEL_PATH)

        # Verification des attributs de metadonnees
        cls.threshold = getattr(cls.pipeline, "threshold", 0.9447)
        cls.model_version = getattr(cls.pipeline, "model_version", "v1.0.0-xgb")
        logger.info(f"Modele charge avec succes : Version={cls.model_version}, Seuil={cls.threshold:.4f}")

        # Chargement de l'echantillon de test
        if TEST_STREAM_PATH.exists():
            logger.info(f"Lecture des donnees depuis {TEST_STREAM_PATH}...")
            df_full = pd.read_csv(TEST_STREAM_PATH)
        elif DATA_PARQUET_PATH.exists():
            logger.info(f"Lecture des donnees depuis {DATA_PARQUET_PATH} (split test step > 700)...")
            df_full = pd.read_parquet(DATA_PARQUET_PATH)
            df_full = df_full[df_full["step"] > 700]
        else:
            raise FileNotFoundError("Aucun fichier de donnees PaySim trouve pour le test.")

        # Echantillon de 1 000 transactions
        cls.n_sample = 1000
        cls.sample_df = df_full.sample(n=min(cls.n_sample, len(df_full)), random_state=42).copy()
        logger.info(f"Echantillon pret : {len(cls.sample_df)} transactions (dont {int(cls.sample_df.get('isFraud', pd.Series([0])).sum())} fraudes)")

    def test_01_metadata_and_threshold_integrity(self):
        """Verifie que le modele embarque un seuil valide et des metadonnees coherentes."""
        self.assertIsNotNone(self.threshold)
        self.assertGreater(self.threshold, 0.0)
        self.assertLess(self.threshold, 1.0)
        self.assertIsNotNone(self.model_version)

        # Verification de concordance avec metadata.json
        if METADATA_PATH.exists():
            import json
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta_thresh = meta.get("optimal_threshold")
            self.assertAlmostEqual(self.threshold, meta_thresh, places=4,
                                  msg="Le seuil dans metadata.json differe de celui de model.joblib !")
            logger.info("[TEST 1/5 SUCCES] Integrite des metadonnees et du seuil validee.")

    def test_02_numerical_parity_single_vs_batch(self):
        """
        Exigence SNF1 / Section 7.3 :
        Compare les probabilites entre le scoring unitaire (mode API) et vectorise (mode Spark).
        Ecart absolu maximal tolere : < 1e-5.
        """
        eval_cols = [
            "step", "type", "amount", "oldbalanceOrg", "newbalanceOrig",
            "oldbalanceDest", "newbalanceDest"
        ]
        X = self.sample_df[eval_cols].copy()

        # Mode 1 : Scoring vectorise en batch (simulation pandas_udf Spark)
        t_batch_start = time.perf_counter()
        batch_probs = self.pipeline.predict_proba(X)[:, 1].astype(np.float64)
        t_batch_ms = (time.perf_counter() - t_batch_start) * 1000

        # Mode 2 : Scoring unitaire transaction par transaction (simulation API FastAPI)
        single_probs = np.zeros(len(X), dtype=np.float64)
        single_latencies = []

        for i in range(len(X)):
            row_df = X.iloc[[i]]
            t_row_start = time.perf_counter()
            prob = self.pipeline.predict_proba(row_df)[:, 1][0]
            single_latencies.append((time.perf_counter() - t_row_start) * 1000)
            single_probs[i] = float(prob)

        # Mesure de l'ecart maximal absolu
        abs_diffs = np.abs(batch_probs - single_probs)
        max_diff = float(np.max(abs_diffs))
        mean_diff = float(np.mean(abs_diffs))

        logger.info(f"Ecart absolu de probabilites : Max = {max_diff:.2e} | Moyenne = {mean_diff:.2e}")
        logger.info(f"Performance Batch ({len(X)} tx) : {t_batch_ms:.2f} ms ({len(X) / (t_batch_ms / 1000):.0f} tx/s)")

        # Verification stricte du contrat (< 10^-5)
        self.assertLess(max_diff, 1e-5, f"Ecart numerique excessif ({max_diff:.2e} >= 1e-5) entre API et Spark !")

        # Verification de concordance a 100% sur la decision binaire
        batch_decisions = batch_probs >= self.threshold
        single_decisions = single_probs >= self.threshold
        divergences = np.sum(batch_decisions != single_decisions)
        self.assertEqual(divergences, 0, f"{divergences} divergences de decision detectees entre mode unitaire et batch !")
        logger.info(f"[TEST 2/5 SUCCES] Parite numerique certifiee (Max diff = {max_diff:.2e} < 1e-5, zero divergence de decision).")

    def test_03_inference_latency_snf2_compliance(self):
        """Verifie que la latence unitaire P95 respecte rigoureusement la contrainte SNF2 (< 200 ms)."""
        sample_row = self.sample_df.iloc[[0]][[
            "step", "type", "amount", "oldbalanceOrg", "newbalanceOrig",
            "oldbalanceDest", "newbalanceDest"
        ]]

        # Warmup
        self.pipeline.predict_proba(sample_row)

        latencies = []
        for _ in range(100):
            t0 = time.perf_counter()
            self.pipeline.predict_proba(sample_row)
            latencies.append((time.perf_counter() - t0) * 1000)

        p50 = float(np.percentile(latencies, 50))
        p95 = float(np.percentile(latencies, 95))
        p99 = float(np.percentile(latencies, 99))

        logger.info(f"Mesures de latence API : P50={p50:.2f} ms | P95={p95:.2f} ms | P99={p99:.2f} ms")
        self.assertLess(p95, 200.0, f"Violation SNF2 : Latence P95 ({p95:.2f} ms) >= 200 ms !")
        logger.info("[TEST 3/5 SUCCES] Conformite SNF2 de latence validee (P95 < 200 ms).")

    def test_04_real_life_fraud_scenarios(self):
        """Valide le comportement du modele sur des cas reels critiques."""
        # Scenario A : Vidage complet du compte par TRANSFER (Attaque classique PaySim)
        fraud_tx = pd.DataFrame([{
            "step": 720,
            "type": "TRANSFER",
            "amount": 500000.0,
            "oldbalanceOrg": 500000.0,
            "newbalanceOrig": 0.0,
            "oldbalanceDest": 0.0,
            "newbalanceDest": 0.0
        }])
        prob_fraud = self.pipeline.predict_proba(fraud_tx)[:, 1][0]
        decision_fraud = "BLOCKED" if prob_fraud >= self.threshold else "ALLOWED"
        logger.info(f"Scenario Fraude (Vidage complet) : Proba={prob_fraud:.4f} -> {decision_fraud}")
        self.assertGreaterEqual(prob_fraud, self.threshold, "Echec : la fraude evidente de vidage de compte n'a pas ete bloquee !")
        self.assertEqual(decision_fraud, "BLOCKED")

        # Scenario B : Achat normal courant de la vie quotidienne
        normal_tx = pd.DataFrame([{
            "step": 720,
            "type": "PAYMENT",
            "amount": 35.50,
            "oldbalanceOrg": 1200.0,
            "newbalanceOrig": 1164.50,
            "oldbalanceDest": 0.0,
            "newbalanceDest": 0.0
        }])
        prob_normal = self.pipeline.predict_proba(normal_tx)[:, 1][0]
        decision_normal = "BLOCKED" if prob_normal >= self.threshold else "ALLOWED"
        logger.info(f"Scenario Normal (Achat courant) : Proba={prob_normal:.4f} -> {decision_normal}")
        self.assertLess(prob_normal, 0.10, "Avertissement : faux positif eleve sur un achat quotidien classique !")
        self.assertEqual(decision_normal, "ALLOWED")

        # Scenario C : Virement bancaire legitime de montant significatif sans vidage de compte
        legit_transfer = pd.DataFrame([{
            "step": 720,
            "type": "TRANSFER",
            "amount": 10000.0,
            "oldbalanceOrg": 85000.0,
            "newbalanceOrig": 75000.0,
            "oldbalanceDest": 5000.0,
            "newbalanceDest": 15000.0
        }])
        prob_legit_tr = self.pipeline.predict_proba(legit_transfer)[:, 1][0]
        decision_legit_tr = "BLOCKED" if prob_legit_tr >= self.threshold else "ALLOWED"
        logger.info(f"Scenario Legitime (Virement equilibre) : Proba={prob_legit_tr:.4f} -> {decision_legit_tr}")
        self.assertEqual(decision_legit_tr, "ALLOWED")
        logger.info("[TEST 4/5 SUCCES] Scenarios metier en conditions reelles parfaitement discrimines.")

    def test_05_edge_cases_and_robustness(self):
        """Verifie la tolerance aux cas limites de production (zeros, montants extremes, type inconnu)."""
        edge_cases = [
            # 1. Montant nul
            {"step": 720, "type": "TRANSFER", "amount": 0.0, "oldbalanceOrg": 0.0, "newbalanceOrig": 0.0, "oldbalanceDest": 0.0, "newbalanceDest": 0.0},
            # 2. Montant tres eleve legitime
            {"step": 720, "type": "CASH_IN", "amount": 10000000.0, "oldbalanceOrg": 50000.0, "newbalanceOrig": 10050000.0, "oldbalanceDest": 20000000.0, "newbalanceDest": 10000000.0},
            # 3. Type d'operation inconnu (ex: CRYPTO)
            {"step": 720, "type": "CRYPTO", "amount": 500.0, "oldbalanceOrg": 500.0, "newbalanceOrig": 0.0, "oldbalanceDest": 0.0, "newbalanceDest": 500.0}
        ]

        df_edges = pd.DataFrame(edge_cases)
        probs = self.pipeline.predict_proba(df_edges)[:, 1]

        self.assertEqual(len(probs), 3)
        self.assertFalse(np.isnan(probs).any(), "Presence de valeurs NaN dans les probabilites sur cas limites !")
        self.assertTrue((probs >= 0.0).all() and (probs <= 1.0).all(), "Probabilites hors de l'intervalle [0, 1] !")
        logger.info(f"Cas limites evalues sans exception : Probas = {[round(p, 4) for p in probs]}")
        logger.info("[TEST 5/5 SUCCES] Robustesse aux cas limites certifiee.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
