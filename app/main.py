"""API d'inférence : reconnaît un chiffre manuscrit à partir d'une image 8x8."""

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import joblib
from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

PIXEL_COUNT = 64  # image 8x8
PIXEL_MAX = 16  # niveaux de gris du jeu de données

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Requêtes HTTP traitées.",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "Durée de traitement des requêtes HTTP.",
    ["path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
PREDICTIONS = Counter(
    "model_predictions_total",
    "Prédictions rendues, par chiffre prédit.",
    ["digit"],
)
CONFIDENCE = Histogram(
    "model_prediction_confidence",
    "Probabilité attribuée par le modèle à la classe prédite.",
    buckets=(0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99),
)
MODEL_ACCURACY = Gauge(
    "model_test_accuracy",
    "Exactitude du modèle servi, mesurée sur le jeu de test à l'entraînement.",
    ["model_version"],
)


class Digit(BaseModel):
    pixels: Annotated[
        list[Annotated[float, Field(ge=0, le=PIXEL_MAX)]],
        Field(min_length=PIXEL_COUNT, max_length=PIXEL_COUNT),
    ]


class Prediction(BaseModel):
    digit: int
    confidence: float
    model_version: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Le serveur n'écoute qu'une fois le modèle chargé : sans modèle, le pod ne démarre pas.
    model_dir = Path(os.environ["MODEL_DIR"])
    app.state.model = joblib.load(model_dir / "model.joblib")
    app.state.metadata = json.loads((model_dir / "metadata.json").read_text())
    MODEL_ACCURACY.labels(app.state.metadata["model_version"]).set(app.state.metadata["accuracy"])
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="digit-classifier", lifespan=lifespan)

    @app.middleware("http")
    async def record_http_metrics(request: Request, call_next):
        start = time.perf_counter()
        status = 500  # valeur retenue si le traitement lève une exception
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = route.path if route else "unmatched"
            HTTP_REQUESTS.labels(request.method, path, status).inc()
            HTTP_DURATION.labels(path).observe(time.perf_counter() - start)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/model")
    def model_metadata(request: Request) -> dict:
        return request.app.state.metadata

    @app.post("/predict")
    def predict(digit: Digit, request: Request) -> Prediction:
        probabilities = request.app.state.model.predict_proba([digit.pixels])[0]
        predicted = int(probabilities.argmax())
        confidence = float(probabilities[predicted])

        PREDICTIONS.labels(str(predicted)).inc()
        CONFIDENCE.observe(confidence)
        return Prediction(
            digit=predicted,
            confidence=round(confidence, 4),
            model_version=request.app.state.metadata["model_version"],
        )

    return app
