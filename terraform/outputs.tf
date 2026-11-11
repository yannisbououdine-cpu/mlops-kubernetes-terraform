output "api_url" {
  description = "URL de l'API d'inférence."
  value       = "http://127.0.0.1:${var.host_ports.api}"
}

output "grafana_url" {
  description = "URL de Grafana (utilisateur : admin)."
  value       = "http://127.0.0.1:${var.host_ports.grafana}"
}

output "prometheus_url" {
  description = "URL de Prometheus."
  value       = "http://127.0.0.1:${var.host_ports.prometheus}"
}

output "grafana_admin_password" {
  description = "Mot de passe du compte admin de Grafana, généré par Terraform."
  value       = random_password.grafana_admin.result
  sensitive   = true
}

output "kubeconfig_path" {
  description = "Fichier kubeconfig du cluster, à passer à kubectl."
  value       = kind_cluster.this.kubeconfig_path
}
