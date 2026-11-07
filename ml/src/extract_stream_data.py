"""
Script d'extraction du jeu de test temporel pour le simulateur de streaming.
Tâche T1.3 : Découpage temporel et extraction pour Personne 2.

Découpage temporel défini dans le Cahier des Charges :
  - Train      : step <= 600
  - Validation : 601 <= step <= 700
  - Test       : step > 700

Ce script extrait l'intégralité du split de test (step > 700), préservant 100%
des fraudes (490 fraudes sur 11 421 transactions, soit 4.29% de fraudes),
et l'enregistre dans streaming/data_sample/test_stream.csv pour alimenter
le producteur Kafka (producer.py) de Personne 2.
"""

import argparse
import logging
import os
from pathlib import Path
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("extract_stream_data")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extraction du split de test temporel PaySim pour le streaming"
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default="data/paysim.parquet",
        help="Chemin vers le dataset PaySim (parquet ou csv)"
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="streaming/data_sample/test_stream.csv",
        help="Chemin du fichier CSV de sortie pour le simulateur"
    )
    parser.add_argument(
        "--train-step-max",
        type=int,
        default=600,
        help="Borne superieure du split d'entrainement (inclus)"
    )
    parser.add_argument(
        "--val-step-max",
        type=int,
        default=700,
        help="Borne superieure du split de validation (inclus)"
    )
    return parser.parse_args()


def load_dataset(input_path: Path) -> pd.DataFrame:
    logger.info(f"Chargement du dataset depuis {input_path}...")
    if not input_path.exists():
        # Fallback csv si parquet absent
        csv_fallback = input_path.with_suffix(".csv")
        if csv_fallback.exists():
            logger.info(f"Fichier parquet non trouve, lecture du CSV : {csv_fallback}")
            return pd.read_csv(csv_fallback)
        raise FileNotFoundError(f"Impossible de trouver {input_path} ou {csv_fallback}")

    if input_path.suffix == ".parquet":
        return pd.read_parquet(input_path)
    elif input_path.suffix == ".csv":
        return pd.read_csv(input_path)
    else:
        raise ValueError(f"Format non supporte : {input_path.suffix}")


def main():
    args = parse_args()
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)

    df = load_dataset(input_path)
    total_rows = len(df)
    total_frauds = int(df["isFraud"].sum())
    logger.info(f"Dataset charge : {total_rows:,} lignes, {total_frauds:,} fraudes ({total_frauds / total_rows * 100:.4f}%)")

    # 1. Verification du decoupage temporel
    train_mask = df["step"] <= args.train_step_max
    val_mask = (df["step"] > args.train_step_max) & (df["step"] <= args.val_step_max)
    test_mask = df["step"] > args.val_step_max

    train_df = df[train_mask]
    val_df = df[val_mask]
    test_df = df[test_mask].copy()

    logger.info("=== Bilan du decoupage temporel ===")
    logger.info(
        f"Train (step <= {args.train_step_max})       : "
        f"{len(train_df):>9,} lignes | {int(train_df['isFraud'].sum()):>5,} fraudes "
        f"({train_df['isFraud'].mean() * 100:6.3f}%)"
    )
    logger.info(
        f"Validation (step {args.train_step_max + 1}-{args.val_step_max}) : "
        f"{len(val_df):>9,} lignes | {int(val_df['isFraud'].sum()):>5,} fraudes "
        f"({val_df['isFraud'].mean() * 100:6.3f}%)"
    )
    logger.info(
        f"Test (step > {args.val_step_max})           : "
        f"{len(test_df):>9,} lignes | {int(test_df['isFraud'].sum()):>5,} fraudes "
        f"({test_df['isFraud'].mean() * 100:6.3f}%)"
    )

    # 2. Tri chronologique sur le split de test pour respecter l'ordre temporel du stream
    test_df = test_df.sort_values(by=["step"]).reset_index(drop=True)

    # 3. Export du fichier test_stream.csv pour Personne 2
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Exportation de {len(test_df):,} transactions vers {output_path}...")
    test_df.to_csv(output_path, index=False)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"[SUCCES] Fichier exporte avec succes : {output_path} ({file_size_mb:.2f} Mo)")
    logger.info(
        f"Contenu : {len(test_df):,} transactions dont {int(test_df['isFraud'].sum()):,} fraudes "
        f"(100% des fraudes de test conservees, ratio: {test_df['isFraud'].mean() * 100:.2f}%)"
    )


if __name__ == "__main__":
    main()
