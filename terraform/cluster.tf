locals {
  # Port du nœud (NodePort) de chaque service exposé hors du cluster.
  node_ports = {
    api        = 30080
    grafana    = 30300
    prometheus = 30090
  }
}

resource "kind_cluster" "this" {
  name            = var.cluster_name
  node_image      = var.node_image
  kubeconfig_path = abspath("${path.module}/kubeconfig")
  wait_for_ready  = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"

      # Relie chaque NodePort à un port de la machine hôte, en écoute locale uniquement.
      dynamic "extra_port_mappings" {
        for_each = local.node_ports
        content {
          container_port = extra_port_mappings.value
          host_port      = var.host_ports[extra_port_mappings.key]
          listen_address = "127.0.0.1"
        }
      }
    }
  }
}

# Copie l'image construite localement dans le nœud : le cluster n'a pas de registre à interroger.
resource "kind_load" "app" {
  image        = var.image
  cluster_name = kind_cluster.this.name
}
