# Raccourcis pour la démonstration locale. La CI exécute les mêmes étapes.
SHA   := $(shell git rev-parse --short HEAD)
IMAGE ?= digit-classifier:$(SHA)

.PHONY: test build up smoke traffic drift down

test: ## Lint et tests de l'API
	ruff check . && ruff format --check . && cd app && python -m pytest

build: ## Entraîne le modèle et construit l'image
	docker build --build-arg MODEL_VERSION=$(SHA) -t $(IMAGE) app

up: build ## Crée le cluster et déploie supervision et API
	terraform -chdir=terraform init
	terraform -chdir=terraform apply -var image=$(IMAGE)

smoke: ## Vérifie le déploiement de bout en bout
	scripts/smoke-test.sh

traffic: ## Envoie un trafic normal
	python scripts/generate_traffic.py

drift: ## Envoie des images bruitées pour déclencher l'alerte de dérive
	python scripts/generate_traffic.py --noise 4

down: ## Détruit tout
	terraform -chdir=terraform destroy -var image=$(IMAGE)
