resource "random_password" "grafana_admin" {
  length  = 24
  special = false
}

resource "helm_release" "monitoring" {
  name             = "monitoring"
  namespace        = "monitoring"
  create_namespace = true

  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = var.kube_prometheus_stack_version
  timeout    = 900

  values = [file("${path.module}/values/monitoring.yaml")]

  set = [
    {
      name  = "grafana.service.nodePort"
      value = local.node_ports.grafana
    },
    {
      name  = "prometheus.service.nodePort"
      value = local.node_ports.prometheus
    },
  ]

  set_sensitive = [
    {
      name  = "grafana.adminPassword"
      value = random_password.grafana_admin.result
    },
  ]
}
