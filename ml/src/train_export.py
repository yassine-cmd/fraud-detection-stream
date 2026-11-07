"""
Script d'entrainement reproductible, benchmark et export du modele de detection de fraude.
Taches T1.4 & T1.5 : Benchmark des algorithmes, calibrage du seuil optimal et export composite.

Criteres SNF1 du Cahier des Charges :
  - Rappel (Recall) >= 85%
  - F1-Score        >= 0.80
  - AUC-PR          >= 0.85

Decoupage temporel strict :
  - Train      : step <= 600
  - Validation : 601 <= step <= 700 (calibrage du seuil)
  - Test       : step > 700 (evaluation finale impartiale)
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import platform
import subprocess
from typing import Dict, Any, Tuple

import joblib
import numpy as np
import pandas as pd
import pyarrow
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score
)
import xgboost as xgb

from feature_engineering import (
    build_pipeline,
    prepare_features_and_target,
    PAYMENT_TYPES,
    RAW_NUMERIC_FEATURES
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("train_export")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Entrainement, benchmark et export du pipeline de scoring PaySim"
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="data/paysim.parquet",
        help="Chemin vers le dataset PaySim (parquet ou csv)"
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default="ml/artifacts",
        help="Repertoire d'export des modeles et metadonnees"
    )
    parser.add_argument(
        "--train-neg-samples",
        type=int,
        default=500000,
        help="Nombre de transactions negatives a echantillonner dans Train (500000 par defaut, 0 pour 100%% des donnees)"
    )
    parser.add_argument(
        "--run-benchmark",
        action="store_true",
        default=True,
        help="Executer le benchmark comparatif (LogReg vs RandomForest vs XGBoost) sur un sous-ensemble"
    )
    parser.add_argument(
        "--skip-benchmark",
        dest="run_benchmark",
        action="store_false",
        help="Sauter l'etape de benchmark pour un entrainement direct"
    )
    return parser.parse_args()


def load_and_split_data(
    data_path: Path,
    neg_samples: int = 500000,
    random_state: int = 42
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """
    Charge PaySim et applique le decoupage temporel sans fuite d'information :
      Train : step <= 600 (avec 100% des fraudes et echantillonnage controle des negatives)
      Val   : 601 <= step <= 700 (donnees reelles sans reechantillonnage)
      Test  : step > 700 (donnees reelles sans reechantillonnage)
    """
    logger.info(f"Chargement de PaySim depuis {data_path}...")
    t0 = time.time()
    if data_path.suffix == ".parquet":
        df = pd.read_parquet(data_path)
    else:
        df = pd.read_csv(data_path)
    logger.info(f"Dataset charge en {time.time() - t0:.2f}s ({len(df):,} transactions, {int(df['isFraud'].sum()):,} fraudes)")

    # Masques temporels
    train_mask = df["step"] <= 600
    val_mask = (df["step"] > 600) & (df["step"] <= 700)
    test_mask = df["step"] > 700

    if neg_samples and neg_samples < (train_mask & (df["isFraud"] == 0)).sum():
        train_frauds = df[train_mask & (df["isFraud"] == 1)]
        train_negatives = df[train_mask & (df["isFraud"] == 0)].sample(n=neg_samples, random_state=random_state)
        logger.info(f"Reechantillonnage Train : {len(train_frauds):,} fraudes (100%) + {neg_samples:,} non-fraudes")
        train_df = pd.concat([train_frauds, train_negatives]).sample(frac=1.0, random_state=random_state)
    else:
        logger.info(f"Train complet (100% des donnees) : {train_mask.sum():,} transactions d'entrainement")
        train_df = df[train_mask].copy()

    val_df = df[val_mask].copy()
    test_df = df[test_mask].copy()
    del df

    logger.info(f"Dimensions - Train: {len(train_df):,} | Val: {len(val_df):,} | Test: {len(test_df):,}")

    X_train, y_train = prepare_features_and_target(train_df)
    X_val, y_val = prepare_features_and_target(val_df)
    X_test, y_test = prepare_features_and_target(test_df)

    return X_train, y_train, X_val, y_val, X_test, y_test


def run_benchmark_models(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series
) -> Dict[str, Dict[str, Any]]:
    """
    Compare les 3 modeles requis par le Cahier des Charges :
      1. LogisticRegression (Baseline de reference)
      2. RandomForest (avec class_weight='balanced')
      3. XGBoost (avec scale_pos_weight)
    """
    scale_pos = (len(y_train) - y_train.sum()) / y_train.sum()
    logger.info("=== Lancement du Benchmark Comparatif ===")

    models = {
        # Solveur et tolerance figes pour un benchmark reproductible :
        # lbfgs avec tol=1e-4 peut s'arreter sur des solutions differentes
        # selon l'ordonnancement BLAS (AUC-PR observee entre 0.33 et 0.66).
        "LogisticRegression (Baseline)": LogisticRegression(
            class_weight="balanced",
            solver="lbfgs",
            max_iter=1000,
            tol=1e-8,
            random_state=42
        ),
        "RandomForest (Balanced)": RandomForestClassifier(
            n_estimators=50,
            max_depth=10,
            class_weight="balanced",
            n_jobs=-1,
            random_state=42
        ),
        "XGBoost (Optimise)": xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            scale_pos_weight=scale_pos,
            tree_method="hist",
            n_jobs=-1,
            random_state=42
        )
    }

    benchmark_results = {}
    for name, clf in models.items():
        logger.info(f"Entrainement de {name}...")
        t0 = time.time()
        pipeline = build_pipeline(clf)
        pipeline.fit(X_train, y_train)
        fit_time = time.time() - t0

        val_probs = pipeline.predict_proba(X_val)[:, 1]
        auc_pr = average_precision_score(y_val, val_probs)
        roc_auc = roc_auc_score(y_val, val_probs)

        # Seuil par defaut 0.5
        val_preds_default = (val_probs >= 0.5).astype(int)
        rec_default = recall_score(y_val, val_preds_default)
        f1_default = f1_score(y_val, val_preds_default)

        benchmark_results[name] = {
            "fit_time_s": round(fit_time, 2),
            "val_auc_pr": round(float(auc_pr), 4),
            "val_roc_auc": round(float(roc_auc), 4),
            "val_recall_0.5": round(float(rec_default), 4),
            "val_f1_0.5": round(float(f1_default), 4)
        }
        logger.info(
            f"--> {name:30} | Fit: {fit_time:5.2f}s | AUC-PR: {auc_pr:.4f} | "
            f"ROC-AUC: {roc_auc:.4f} | Recall@0.5: {rec_default:.4f} | F1@0.5: {f1_default:.4f}"
        )

    return benchmark_results


def calibrate_threshold(
    pipeline,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    min_recall: float = 0.85
) -> Tuple[float, Dict[str, float]]:
    """
    Calibre le seuil optimal sur l'ensemble de validation.
    Strategie : Maximiser le F1-Score sous contrainte Rappel >= min_recall (SNF1: >= 85%).
    """
    logger.info("Calibrage du seuil optimal sur le split de validation...")
    val_probs = pipeline.predict_proba(X_val)[:, 1]
    precisions, recalls, thresholds = precision_recall_curve(y_val, val_probs)
    
    # Calcul des F1 pour chaque seuil
    f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-10)

    # Filtrer les seuils garantissant le Rappel minimal SNF1
    valid_indices = [i for i, r in enumerate(recalls[:-1]) if r >= min_recall]
    
    if valid_indices:
        # Parmi ceux qui respectent le Rappel, trouver celui qui maximise le F1
        best_idx = max(valid_indices, key=lambda i: f1_scores[i])
        best_threshold = float(thresholds[best_idx])
    else:
        # Fallback : seuil qui maximise le F1 global
        best_idx = int(np.argmax(f1_scores[:-1]))
        best_threshold = float(thresholds[best_idx])

    # Mesures finales au seuil choisi
    val_preds = (val_probs >= best_threshold).astype(int)
    calibrated_metrics = {
        "threshold": round(best_threshold, 4),
        "recall": round(float(recall_score(y_val, val_preds)), 4),
        "precision": round(float(precision_score(y_val, val_preds)), 4),
        "f1_score": round(float(f1_score(y_val, val_preds)), 4),
        "auc_pr": round(float(average_precision_score(y_val, val_probs)), 4),
        "roc_auc": round(float(roc_auc_score(y_val, val_probs)), 4)
    }

    logger.info(
        f"[VALIDATION CALIBREE] Seuil: {calibrated_metrics['threshold']} | "
        f"Rappel: {calibrated_metrics['recall']:.2%} | "
        f"Precision: {calibrated_metrics['precision']:.2%} | "
        f"F1-Score: {calibrated_metrics['f1_score']:.4f} | "
        f"AUC-PR: {calibrated_metrics['auc_pr']:.4f}"
    )
    return best_threshold, calibrated_metrics


def evaluate_test_set(
    pipeline,
    threshold: float,
    X_test: pd.DataFrame,
    y_test: pd.Series
) -> Dict[str, Any]:
    """
    Evaluation finale impartiale sur le jeu de test reserve (step > 700).
    """
    logger.info(f"Evaluation finale sur le jeu de test au seuil {threshold:.4f}...")
    test_probs = pipeline.predict_proba(X_test)[:, 1]
    test_preds = (test_probs >= threshold).astype(int)

    cm = confusion_matrix(y_test, test_preds)
    tn, fp, fn, tp = cm.ravel()

    metrics = {
        "recall": round(float(recall_score(y_test, test_preds)), 4),
        "precision": round(float(precision_score(y_test, test_preds)), 4),
        "f1_score": round(float(f1_score(y_test, test_preds)), 4),
        "auc_pr": round(float(average_precision_score(y_test, test_probs)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, test_probs)), 4),
        "confusion_matrix": {
            "true_negatives": int(tn),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "true_positives": int(tp)
        }
    }

    logger.info(
        f"[TEST FINAL] Rappel: {metrics['recall']:.2%} | "
        f"Precision: {metrics['precision']:.2%} | "
        f"F1-Score: {metrics['f1_score']:.4f} | "
        f"AUC-PR: {metrics['auc_pr']:.4f}"
    )
    logger.info(f"[TEST MATRICE] TP: {tp}, FP: {fp}, FN: {fn}, TN: {tn}")
    return metrics


def main():
    args = parse_args()
    data_path = Path(args.data_path)
    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Chargement et decoupage temporel
    X_train, y_train, X_val, y_val, X_test, y_test = load_and_split_data(
        data_path=data_path,
        neg_samples=args.train_neg_samples
    )

    # 2. Benchmark comparatif
    benchmark_summary = {}
    if args.run_benchmark:
        benchmark_summary = run_benchmark_models(X_train, y_train, X_val, y_val)

    # 3. Entrainement final du modele champion (XGBoost)
    logger.info("=== Entrainement du Modele Champion (XGBoost Production) ===")
    scale_pos = (len(y_train) - y_train.sum()) / y_train.sum()
    champion_clf = xgb.XGBClassifier(
        n_estimators=150,
        max_depth=6,
        learning_rate=0.08,
        scale_pos_weight=scale_pos,
        subsample=0.8,
        colsample_bytree=0.8,
        tree_method="hist",
        random_state=42,
        n_jobs=-1
    )

    production_pipeline = build_pipeline(champion_clf)
    t_train = time.time()
    production_pipeline.fit(X_train, y_train)
    fit_duration = round(time.time() - t_train, 2)
    logger.info(f"Modele XGBoost champion entraine en {fit_duration}s")

    # 4. Calibrage du seuil optimal sur Validation (SNF1)
    optimal_thresh, val_metrics = calibrate_threshold(
        pipeline=production_pipeline,
        X_val=X_val,
        y_val=y_val,
        min_recall=0.85
    )

    # 5. Evaluation finale sur Test
    test_metrics = evaluate_test_set(
        pipeline=production_pipeline,
        threshold=optimal_thresh,
        X_test=X_test,
        y_test=y_test
    )

    # 6. Verification des exigences SNF1
    snf1_check = {
        "recall_ge_85": bool(test_metrics["recall"] >= 0.85),
        "f1_ge_80": bool(test_metrics["f1_score"] >= 0.80),
        "auc_pr_ge_85": bool(test_metrics["auc_pr"] >= 0.85),
        "all_criteria_met": bool(
            test_metrics["recall"] >= 0.85 and
            test_metrics["f1_score"] >= 0.80 and
            test_metrics["auc_pr"] >= 0.85
        )
    }

    # 7. Attributs integres a la pipeline pour portabilite Spark/FastAPI
    raw_input_cols = ["step", "type", "amount", "oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]
    transformed_cols = PAYMENT_TYPES + RAW_NUMERIC_FEATURES + ["balance_diff_orig", "balance_diff_dest"]

    production_pipeline.threshold = optimal_thresh
    production_pipeline.model_version = "v1.0.0-xgb"
    production_pipeline.input_features = raw_input_cols
    production_pipeline.features = raw_input_cols  # Contrat d'entree explicite pour P2 et P3
    production_pipeline.transformed_features = transformed_cols

    # 8. Exportation de model.joblib et metadata.json
    model_export_path = artifacts_dir / "model.joblib"
    metadata_export_path = artifacts_dir / "metadata.json"

    logger.info(f"Sauvegarde du pipeline composite dans {model_export_path}...")
    joblib.dump(production_pipeline, model_export_path)

    # Provenance et tracabilite MLOps
    def get_git_commit_sha() -> str:
        try:
            return subprocess.check_output(
                ["git", "describe", "--always", "--dirty", "--tags"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            try:
                return subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    stderr=subprocess.DEVNULL
                ).decode().strip()
            except Exception:
                return "unknown"

    def compute_file_sha256(file_path: Path) -> str:
        if not file_path.exists():
            return "not_found"
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    git_sha = get_git_commit_sha()
    data_sha256 = compute_file_sha256(data_path)

    metadata_payload = {
        "model_version": "v1.0.0-xgb",
        "model_type": "XGBClassifier",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "git_commit": git_sha,
            "environment_versions": {
                "python": platform.python_version(),
                "scikit_learn": sklearn.__version__,
                "xgboost": xgb.__version__,
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "pyarrow": pyarrow.__version__,
                "joblib": joblib.__version__
            },
            "dataset": {
                "path": str(data_path),
                "size_bytes": data_path.stat().st_size if data_path.exists() else 0,
                "sha256": data_sha256
            }
        },
        "train_samples": len(X_train),
        "train_fit_time_seconds": fit_duration,
        "optimal_threshold": optimal_thresh,
        "input_features": raw_input_cols,
        "features": {
            "categorical": ["type"],
            "numeric": RAW_NUMERIC_FEATURES,
            "engineered": ["balance_diff_orig", "balance_diff_dest"]
        },
        "hyperparameters": {
            "n_estimators": 150,
            "max_depth": 6,
            "learning_rate": 0.08,
            "scale_pos_weight": round(float(scale_pos), 2),
            "tree_method": "hist"
        },
        "snf1_compliance": snf1_check,
        "validation_metrics": val_metrics,
        "test_metrics": test_metrics,
        "benchmark_summary": benchmark_summary
    }

    logger.info(f"Sauvegarde des metadonnees dans {metadata_export_path}...")
    with open(metadata_export_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, indent=2)

    logger.info("=== Bilan Final SNF1 ===")
    logger.info(f"Rappel Test >= 85%  : {'VALIDE' if snf1_check['recall_ge_85'] else 'ECHEC'} ({test_metrics['recall']:.2%})")
    logger.info(f"F1-Score Test >= 0.80: {'VALIDE' if snf1_check['f1_ge_80'] else 'ECHEC'} ({test_metrics['f1_score']:.4f})")
    logger.info(f"AUC-PR Test >= 0.85 : {'VALIDE' if snf1_check['auc_pr_ge_85'] else 'ECHEC'} ({test_metrics['auc_pr']:.4f})")
    if snf1_check["all_criteria_met"]:
        logger.info("[SUCCES TOTAL] Taches T1.4 et T1.5 terminees et conformes au Cahier des Charges !")
    else:
        logger.warning("[ECHEC] Un ou plusieurs criteres SNF1 ne sont pas satisfaits.")


if __name__ == "__main__":
    main()
