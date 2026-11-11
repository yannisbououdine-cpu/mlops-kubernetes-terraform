variable "image" {
  description = "Image de l'API à déployer (nom:tag). Elle doit exister dans le Docker local : Terraform la charge dans le cluster."
  type        = string

  validation {
    condition     = can(regex("^[^:]+:[^:]+$", var.image)) && !endswith(var.image, ":latest")
    error_message = "L'image doit être de la forme nom:tag, avec un tag précis (pas latest)."
  }
}

variable "cluster_name" {
  description = "Nom du cluster kind."
  type        = string
  default     = "mlops"
}

variable "node_image" {
  description = "Image des nœuds kind : fixe la version de Kubernetes. Le condensat est celui publié avec kind v0.33.0."
  type        = string
  default     = "kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
}

variable "kube_prometheus_stack_version" {
  description = "Version du chart kube-prometheus-stack (Prometheus, Alertmanager, Grafana)."
  type        = string
  default     = "93.2.2"
}

variable "host_ports" {
  description = "Ports de la machine hôte (127.0.0.1) sur lesquels les services sont joignables."
  type = object({
    api        = number
    grafana    = number
    prometheus = number
  })
  default = {
    api        = 8080
    grafana    = 3000
    prometheus = 9090
  }
}
