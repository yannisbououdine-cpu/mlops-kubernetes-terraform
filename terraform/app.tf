resource "helm_release" "app" {
  name             = "digit-classifier"
  namespace        = "ml"
  create_namespace = true

  chart = "${path.module}/../chart"

  set = [
    {
      name  = "image"
      value = var.image
    },
    {
      name  = "service.nodePort"
      value = local.node_ports.api
    },
  ]

  depends_on = [
    kind_load.app,           # l'image doit être dans le nœud avant le démarrage des pods
    helm_release.monitoring, # fournit les types ServiceMonitor et PrometheusRule
  ]
}
