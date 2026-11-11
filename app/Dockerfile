# Étape 1 : installe les dépendances et entraîne le modèle.
# Si l'exactitude passe sous le seuil de train.py, la construction de l'image échoue.
FROM python:3.13-slim AS builder

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY train.py .
ARG MODEL_VERSION
RUN python train.py --output-dir /build/model --model-version "${MODEL_VERSION:?MODEL_VERSION est obligatoire}"

# Étape 2 : image d'exécution, sans le code d'entraînement et sans droits root.
FROM python:3.13-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_DIR=/app/model

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/model ./model
COPY main.py .

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
