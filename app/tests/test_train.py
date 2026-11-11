import json

import joblib
import pytest

import train as train_module
from train import MIN_ACCURACY, train


def test_train_writes_model_and_metadata(model_dir):
    metadata = json.loads((model_dir / "metadata.json").read_text())

    assert metadata["model_version"] == "test"
    assert metadata["accuracy"] >= MIN_ACCURACY
    assert hasattr(joblib.load(model_dir / "model.joblib"), "predict_proba")


def test_training_is_reproducible(model_dir, tmp_path):
    first = json.loads((model_dir / "metadata.json").read_text())
    second = train(tmp_path, model_version="test")

    assert second["accuracy"] == first["accuracy"]


def test_quality_gate_stops_the_build(tmp_path, monkeypatch):
    monkeypatch.setattr(train_module, "MIN_ACCURACY", 1.01)

    with pytest.raises(SystemExit, match="Seuil de qualité non atteint"):
        train(tmp_path, model_version="test")

    assert not (tmp_path / "model.joblib").exists()
