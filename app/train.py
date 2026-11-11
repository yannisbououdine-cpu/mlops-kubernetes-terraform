"""Entraîne le classifieur de chiffres manuscrits et applique le seuil de qualité.

Le jeu de données (1 797 images 8x8, UCI) est embarqué dans scikit-learn :
l'entraînement est reproductible et ne dépend d'aucun téléchargement.
"""

import argparse
import json
from pathlib import Path

import joblib
import sklearn
from sklearn.datasets import load_digits
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MIN_ACCURACY = 0.95
RANDOM_STATE = 42


def train(output_dir: Path, model_version: str) -> dict:
    digits = load_digits()
    x_train, x_test, y_train, y_test = train_test_split(
        digits.data,
        digits.target,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=digits.target,
    )

    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit(x_train, y_train)

    accuracy = float(accuracy_score(y_test, model.predict(x_test)))
    if accuracy < MIN_ACCURACY:
        raise SystemExit(
            f"Seuil de qualité non atteint : exactitude {accuracy:.4f} < {MIN_ACCURACY}"
        )

    metadata = {
        "model_version": model_version,
        "accuracy": round(accuracy, 4),
        "min_accuracy": MIN_ACCURACY,
        "train_samples": len(x_train),
        "test_samples": len(x_test),
        "scikit_learn_version": sklearn.__version__,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_dir / "model.joblib")
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-version", required=True)
    args = parser.parse_args()
    print(json.dumps(train(args.output_dir, args.model_version), indent=2))
