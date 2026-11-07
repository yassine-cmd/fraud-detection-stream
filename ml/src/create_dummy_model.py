"""Script de generation du Dummy Model (Tache T1.1 - Priorite J+1)

Ce script cree le premier artefact model.joblib conforme aux specifications
du Cahier des Charges.

L'objet serialise est directement un Pipeline scikit-learn standard,
sans dependance a des classes custom hors-sklearn, garantissant que
l'API FastAPI et le job Spark peuvent charger le fichier avec un simple :
    model = joblib.load("model.joblib")
    model.predict_proba(df)
"""

from pathlib import Path
import time
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def build_and_save_dummy_model(output_path: Path):
    """Construit et exporte l'artefact model.joblib."""
    # 1. Donnees synthetiques representatives PaySim pour ajuster le pipeline
    sample_data = pd.DataFrame(
        [
            # Transactions normales
            {"step": 1, "type": "PAYMENT", "amount": 100.0, "oldbalanceOrg": 500.0, "newbalanceOrig": 400.0, "oldbalanceDest": 0.0, "newbalanceDest": 0.0, "is_fraud": 0},
            {"step": 2, "type": "CASH_IN", "amount": 2000.0, "oldbalanceOrg": 1000.0, "newbalanceOrig": 3000.0, "oldbalanceDest": 5000.0, "newbalanceDest": 3000.0, "is_fraud": 0},
            {"step": 3, "type": "DEBIT", "amount": 50.0, "oldbalanceOrg": 800.0, "newbalanceOrig": 750.0, "oldbalanceDest": 100.0, "newbalanceDest": 150.0, "is_fraud": 0},
            {"step": 4, "type": "PAYMENT", "amount": 450.0, "oldbalanceOrg": 2000.0, "newbalanceOrig": 1550.0, "oldbalanceDest": 0.0, "newbalanceDest": 0.0, "is_fraud": 0},
            # Transactions frauduleuses (TRANSFER / CASH_OUT vidant le compte)
            {"step": 650, "type": "TRANSFER", "amount": 300000.0, "oldbalanceOrg": 300000.0, "newbalanceOrig": 0.0, "oldbalanceDest": 0.0, "newbalanceDest": 300000.0, "is_fraud": 1},
            {"step": 651, "type": "CASH_OUT", "amount": 180000.0, "oldbalanceOrg": 180000.0, "newbalanceOrig": 0.0, "oldbalanceDest": 1000.0, "newbalanceDest": 181000.0, "is_fraud": 1},
            {"step": 652, "type": "TRANSFER", "amount": 500000.0, "oldbalanceOrg": 500000.0, "newbalanceOrig": 0.0, "oldbalanceDest": 0.0, "newbalanceDest": 500000.0, "is_fraud": 1},
        ]
    )

    feature_cols = [
        "step",
        "type",
        "amount",
        "oldbalanceOrg",
        "newbalanceOrig",
        "oldbalanceDest",
        "newbalanceDest",
    ]
    numeric_cols = [
        "step",
        "amount",
        "oldbalanceOrg",
        "newbalanceOrig",
        "oldbalanceDest",
        "newbalanceDest",
    ]
    categorical_cols = ["type"]

    X_train = sample_data[feature_cols]
    y_train = sample_data["is_fraud"]

    # 2. Pipeline de pretraitement standard scikit-learn
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_cols),
            (
                "cat",
                OneHotEncoder(
                    categories=[["PAYMENT", "TRANSFER", "CASH_OUT", "DEBIT", "CASH_IN"]],
                    handle_unknown="ignore",
                ),
                categorical_cols,
            ),
        ]
    )

    # 3. Pipeline complet standard
    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", LogisticRegression(class_weight="balanced", random_state=42)),
        ]
    )

    # Entrainement
    pipeline.fit(X_train, y_train)

    # 4. Attributs de metadonnees et de seuil integres au pipeline
    optimal_threshold = 0.50
    model_version = "v0.1.0-dummy"

    pipeline.threshold = optimal_threshold
    pipeline.model_version = model_version
    pipeline.input_features = feature_cols
    pipeline.features = feature_cols
    pipeline.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # 5. Sauvegarde
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, output_path)

    print(f"[OK] Modele joblib sauvegarde avec succes : {output_path}")
    print(f"     Type de l'objet : {type(pipeline)}")
    print(f"     Version du modele : {model_version}")
    print(f"     Seuil de decision : {optimal_threshold}")
    print(f"     Colonnes attendues : {feature_cols}")
    return pipeline


def test_inference(model_path: Path):
    """Teste le chargement et l'inference pour valider la compatibilite."""
    print("\n--- Test d'Inference Unitaire (Simulation Scenario 2) ---")
    start_time = time.perf_counter()

    # Chargement direct du modele
    model = joblib.load(model_path)
    threshold = getattr(model, "threshold", 0.5)
    version = getattr(model, "model_version", "unknown")

    # Transaction de test (du Cahier des Charges)
    test_tx = pd.DataFrame(
        [
            {
                "step": 650,
                "type": "TRANSFER",
                "amount": 300000.0,
                "oldbalanceOrg": 300000.0,
                "newbalanceOrig": 0.0,
                "oldbalanceDest": 0.0,
                "newbalanceDest": 300000.0,
            }
        ]
    )

    # Prediction
    prob = float(model.predict_proba(test_tx)[0, 1])
    is_fraud = bool(prob >= threshold)
    decision = "BLOCKED" if is_fraud else "ALLOWED"
    latency_ms = (time.perf_counter() - start_time) * 1000

    print(f"Transaction ID : tx_test_sample_01")
    print(f"Probabilite de fraude : {prob:.4f}")
    print(f"Seuil applique : {threshold}")
    print(f"Decision : {decision}")
    print(f"Version du modele : {version}")
    print(f"Latence d'inference unitaire : {latency_ms:.2f} ms")
    assert 0.0 <= prob <= 1.0, "La probabilite doit etre comprise entre 0 et 1"
    print("[OK] Test d'inference valide !")


if __name__ == "__main__":
    artifact_file = Path(__file__).resolve().parent.parent / "artifacts" / "model.joblib"
    build_and_save_dummy_model(artifact_file)
    test_inference(artifact_file)
