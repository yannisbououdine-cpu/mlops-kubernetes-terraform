#!/usr/bin/env bash
# Vérifie de bout en bout un déploiement : API, collecte Prometheus, alertes et tableau de bord.
# Usage : scripts/smoke-test.sh (à lancer après terraform apply).
set -euo pipefail

cd "$(dirname "$0")/.."
api=$(terraform -chdir=terraform output -raw api_url)
prometheus=$(terraform -chdir=terraform output -raw prometheus_url)
grafana=$(terraform -chdir=terraform output -raw grafana_url)
grafana_password=$(terraform -chdir=terraform output -raw grafana_admin_password)

# Réessaie une commande toutes les 10 s pendant 5 min au plus.
retry() {
  local description=$1
  shift
  for _ in $(seq 30); do
    if "$@" >/dev/null 2>&1; then
      echo "OK   $description"
      return 0
    fi
    sleep 10
  done
  echo "ÉCHEC $description" >&2
  "$@" || true
  return 1
}

prediction_is_correct() {
  curl -fsS -X POST "$api/predict" -H 'Content-Type: application/json' -d @examples/digit-5.json |
    jq -e '.digit == 5'
}

invalid_input_is_rejected() {
  test "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$api/predict" \
    -H 'Content-Type: application/json' -d '{"pixels": [1, 2, 3]}')" = 422
}

prometheus_scrapes_every_pod() {
  curl -fsS "$prometheus/api/v1/query" --data-urlencode 'query=sum(up{job="digit-classifier"})' |
    jq -e '.data.result[0].value[1] == "2"'
}

prometheus_counts_predictions() {
  curl -fsS "$prometheus/api/v1/query" --data-urlencode 'query=sum(model_predictions_total{job="digit-classifier"})' |
    jq -e '(.data.result[0].value[1] | tonumber) > 0'
}

alert_rules_are_loaded() {
  curl -fsS "$prometheus/api/v1/rules" |
    jq -e '[.data.groups[] | select(.name == "digit-classifier") | .rules[]] | length == 4'
}

dashboard_is_provisioned() {
  curl -fsS -u "admin:$grafana_password" "$grafana/api/dashboards/uid/digit-classifier" |
    jq -e '.dashboard.title == "Digit classifier"'
}

retry "l'API reconnaît le chiffre 5 de examples/digit-5.json" prediction_is_correct
retry "l'API rejette une image invalide (422)" invalid_input_is_rejected
retry "Prometheus collecte les 2 pods de l'API" prometheus_scrapes_every_pod
retry "Prometheus a enregistré les prédictions" prometheus_counts_predictions
retry "les 4 règles d'alerte sont chargées" alert_rules_are_loaded
retry "Grafana a chargé le tableau de bord" dashboard_is_provisioned
