import pytest
from fastapi.testclient import TestClient

from main import create_app


def test_healthz(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_model_metadata(client):
    metadata = client.get("/model").json()

    assert metadata["model_version"] == "test"
    assert metadata["accuracy"] >= metadata["min_accuracy"]


def test_predict_recognises_a_known_digit(client, digits):
    response = client.post("/predict", json={"pixels": digits.data[0].tolist()})

    assert response.status_code == 200
    body = response.json()
    assert body["digit"] == int(digits.target[0])
    assert 0.5 < body["confidence"] <= 1.0
    assert body["model_version"] == "test"


@pytest.mark.parametrize(
    "pixels",
    [
        [0.0] * 63,  # image incomplète
        [0.0] * 65,  # image trop grande
        [0.0] * 63 + [17.0],  # hors de l'échelle de gris 0-16
        [0.0] * 63 + [-1.0],
        "pas une image",
    ],
)
def test_predict_rejects_invalid_input(client, pixels):
    response = client.post("/predict", json={"pixels": pixels})

    assert response.status_code == 422


def test_metrics_expose_predictions_and_http_traffic(client, digits):
    client.post("/predict", json={"pixels": digits.data[0].tolist()})
    client.post("/predict", json={"pixels": []})

    metrics = client.get("/metrics").text

    digit = int(digits.target[0])
    assert f'model_predictions_total{{digit="{digit}"}}' in metrics
    assert "model_prediction_confidence_bucket" in metrics
    assert 'model_test_accuracy{model_version="test"}' in metrics
    assert 'http_requests_total{method="POST",path="/predict",status="200"}' in metrics
    assert 'http_requests_total{method="POST",path="/predict",status="422"}' in metrics
    assert 'http_request_duration_seconds_count{path="/predict"}' in metrics


def test_unknown_path_does_not_create_a_label_per_url(client):
    client.get("/chemin/inconnu/12345")

    metrics = client.get("/metrics").text

    assert 'path="unmatched",status="404"' in metrics
    assert "12345" not in metrics


def test_startup_fails_without_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))

    with pytest.raises(FileNotFoundError), TestClient(create_app()):
        pass
