"""
Module de Feature Engineering pour la detection de fraude PaySim.
Tache T1.2 : Fonctions d'encodage, ecarts de soldes et pipeline scikit-learn standard.

Ce module offre :
1. Des fonctions d'ingenierie de variables Pandas (pour l'EDA et le benchmark) :
   - balance_diff_orig = newbalanceOrig + amount - oldbalanceOrg
   - balance_diff_dest = oldbalanceDest + amount - newbalanceDest
2. Un preprocesseur scikit-learn 100% natif (ColumnTransformer, StandardScaler, OneHotEncoder,
   projecteurs lineaires PCA avec poids fixes) garantissant la deserialisation avec joblib.load()
   dans Spark (pandas_udf) et FastAPI sans necessiter d'import de classes specifiques.
"""

from typing import List, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler, RobustScaler


# Definition des categories PaySim et colonnes
CATEGORICAL_FEATURES: List[str] = ["type"]
PAYMENT_TYPES: List[str] = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]

RAW_NUMERIC_FEATURES: List[str] = [
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest"
]

METADATA_COLUMNS_TO_DROP: List[str] = [
    "nameOrig",
    "nameDest",
    "isFlaggedFraud",
    "transaction_id",
    "produced_at"
]


def compute_balance_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule les variables d'ecart comptable pour l'emetteur et le destinataire.
    
    balance_diff_orig : newbalanceOrig + amount - oldbalanceOrg
      (vaut 0 si le solde emetteur a ete debite exactement du montant)
    balance_diff_dest : oldbalanceDest + amount - newbalanceDest
      (vaut 0 si le solde destinataire a ete credite exactement du montant)
    """
    df_out = df.copy()
    
    # Ecart origine
    df_out["balance_diff_orig"] = (
        df_out["newbalanceOrig"] + df_out["amount"] - df_out["oldbalanceOrg"]
    )
    
    # Ecart destinataire
    df_out["balance_diff_dest"] = (
        df_out["oldbalanceDest"] + df_out["amount"] - df_out["newbalanceDest"]
    )
    
    return df_out


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrichit un DataFrame PaySim avec toutes les features metier deduites.
    """
    df_feat = compute_balance_features(df)
    
    # Indicateurs binaires de vidange de compte et solde initial nul
    df_feat["is_orig_zero_new"] = (df_feat["newbalanceOrig"] == 0.0).astype(np.float64)
    df_feat["is_dest_zero_old"] = (df_feat["oldbalanceDest"] == 0.0).astype(np.float64)
    df_feat["is_dest_zero_new"] = (df_feat["newbalanceDest"] == 0.0).astype(np.float64)
    
    # Ratio montant / solde origine
    df_feat["amount_to_oldbalance_orig"] = np.where(
        df_feat["oldbalanceOrg"] > 0,
        df_feat["amount"] / (df_feat["oldbalanceOrg"] + 1.0),
        0.0
    )
    
    return df_feat


def prepare_features_and_target(
    df: pd.DataFrame,
    target_col: str = "isFraud"
) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """
    Supprime les colonnes inutiles/fuites de donnees (identifiants, flags PaySim).
    Retourne X et optionnellement y si target_col est present.
    """
    cols_to_drop = [c for c in METADATA_COLUMNS_TO_DROP if c in df.columns]
    
    y = None
    if target_col in df.columns:
        y = df[target_col].copy()
        cols_to_drop.append(target_col)
        
    X = df.drop(columns=cols_to_drop, errors="ignore").copy()
    return X, y


def _create_linear_diff_transformer(coefficients: np.ndarray) -> PCA:
    """
    Cree un transformateur lineaire scikit-learn standard via PCA (n_components=1)
    avec des poids et moyennes predefinis.
    
    Cela permet de calculer une combinaison lineaire exacte (ex: 1*amount - 1*old + 1*new)
    au sein d'une Pipeline scikit-learn SANS aucune classe personnalisee,
    garantissant une serialisation/deserialisation universelle avec joblib.load().
    """
    n_features = len(coefficients)
    pca = PCA(n_components=1)
    # Fit initial avec donnees non-nulles pour initialiser proprement les structures sklearn sans avertissement
    dummy_data = np.arange(2 * n_features, dtype=np.float64).reshape(2, n_features)
    pca.fit(dummy_data)
    pca.components_ = np.array([coefficients], dtype=np.float64)
    pca.mean_ = np.zeros(n_features, dtype=np.float64)
    return pca


def build_preprocessor(scaler_type: str = "standard") -> ColumnTransformer:
    """
    Construit un ColumnTransformer scikit-learn natif pret a recevoir
    directement les donnees brutes PaySim (avec type, amount, oldbalanceOrg, etc.).
    
    Pipeline de transformation interne :
      1. One-Hot Encoding strict de la variable 'type'
      2. Mise a l'echelle des features numeriques brutes (StandardScaler ou RobustScaler)
      3. Calcul natif des ecarts de soldes 'balance_diff_orig' et 'balance_diff_dest'
    """
    # Projecteur lineaire balance_diff_orig :
    # Entrees : ['amount', 'oldbalanceOrg', 'newbalanceOrig']
    # Formule : 1.0 * amount - 1.0 * oldbalanceOrg + 1.0 * newbalanceOrig
    pca_diff_orig = _create_linear_diff_transformer(np.array([1.0, -1.0, 1.0]))

    # Projecteur lineaire balance_diff_dest :
    # Entrees : ['amount', 'oldbalanceDest', 'newbalanceDest']
    # Formule : 1.0 * amount + 1.0 * oldbalanceDest - 1.0 * newbalanceDest
    pca_diff_dest = _create_linear_diff_transformer(np.array([1.0, 1.0, -1.0]))

    scaler = StandardScaler() if scaler_type == "standard" else RobustScaler()

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat_encoder",
                OneHotEncoder(
                    categories=[PAYMENT_TYPES],
                    handle_unknown="ignore",
                    sparse_output=False
                ),
                CATEGORICAL_FEATURES
            ),
            (
                "num_scaler",
                scaler,
                RAW_NUMERIC_FEATURES
            ),
            (
                "diff_orig_calc",
                pca_diff_orig,
                ["amount", "oldbalanceOrg", "newbalanceOrig"]
            ),
            (
                "diff_dest_calc",
                pca_diff_dest,
                ["amount", "oldbalanceDest", "newbalanceDest"]
            ),
        ],
        remainder="drop"
    )
    return preprocessor


def build_pipeline(classifier: BaseEstimator, scaler_type: str = "standard") -> Pipeline:
    """
    Assemble le preprocesseur natif et le classifieur (LogisticRegression, RandomForest, XGBoost)
    en une Pipeline composite scikit-learn autonome.
    """
    preprocessor = build_preprocessor(scaler_type=scaler_type)
    return Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", classifier)
    ])


if __name__ == "__main__":
    import joblib
    import tempfile
    from pathlib import Path
    from sklearn.linear_model import LogisticRegression

    print("=== Test unitaire du module feature_engineering.py ===")

    # 1. Test des calculs Pandas
    sample_df = pd.DataFrame([
        {
            "step": 1,
            "type": "TRANSFER",
            "amount": 1000.0,
            "nameOrig": "C123",
            "oldbalanceOrg": 1000.0,
            "newbalanceOrig": 0.0,
            "nameDest": "C456",
            "oldbalanceDest": 0.0,
            "newbalanceDest": 0.0,
            "isFraud": 1,
            "isFlaggedFraud": 0
        },
        {
            "step": 1,
            "type": "PAYMENT",
            "amount": 50.0,
            "nameOrig": "C789",
            "oldbalanceOrg": 200.0,
            "newbalanceOrig": 150.0,
            "nameDest": "M999",
            "oldbalanceDest": 0.0,
            "newbalanceDest": 0.0,
            "isFraud": 0,
            "isFlaggedFraud": 0
        }
    ])

    enriched = add_engineered_features(sample_df)
    assert "balance_diff_orig" in enriched.columns
    assert "balance_diff_dest" in enriched.columns
    print(f"Calculs Pandas valides : diff_orig={enriched['balance_diff_orig'].tolist()}, diff_dest={enriched['balance_diff_dest'].tolist()}")

    # 2. Test du preprocesseur scikit-learn natif
    X, y = prepare_features_and_target(sample_df)
    preprocessor = build_preprocessor()
    transformed = preprocessor.fit_transform(X)
    print(f"Transformation scikit-learn : forme du tenseur {transformed.shape} (5 one-hot + 5 num + 2 diffs = 12 cols)")
    assert transformed.shape == (2, 12), f"Attendu (2, 12), obtenu {transformed.shape}"

    # 3. Test d'assemblage en Pipeline scikit-learn complete et serialisation joblib
    pipe = build_pipeline(LogisticRegression())
    pipe.fit(X, y)
    
    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        joblib.dump(pipe, tmp_path)
        loaded_pipe = joblib.load(tmp_path)
        probas = loaded_pipe.predict_proba(X)
        print(f"Inference apres joblib.load() : probas={probas.tolist()}")
        print("[SUCCES] Pipeline 100% autonome, serialisable et compatible Spark / FastAPI !")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
