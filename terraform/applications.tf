# Helm release: Prometheus (kube-prometheus-stack) for cluster monitoring
resource "helm_release" "kube_prometheus_stack" {
  name             = "kube-prom-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  namespace        = "monitoring"
  create_namespace = true
}

# Helm release: Loki for log aggregation
resource "helm_release" "loki" {
  name             = "loki"
  repository       = "https://grafana.github.io/helm-charts"
  chart            = "loki"
  namespace        = "logging"
  create_namespace = true
}

# Helm release: ArgoCD for GitOps continuous delivery
resource "helm_release" "argo_cd" {
  name             = "argo-cd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  namespace        = "argocd"
  create_namespace = true
  values = [
    jsonencode({
      server = {
        ingress = {
          enabled = false
        }
      }
    })
  ]
}

# Helm release: Fluent Bit for log forwarding with GDPR compliance (log redaction)
resource "helm_release" "fluent_bit" {
  name             = "fluent-bit"
  repository       = "https://fluent.github.io/helm-charts"
  chart            = "fluent-bit"
  namespace        = "logging"
  create_namespace = true
  values = [
    <<-EOF
    config:
      filters: | 
        [FILTER]
            Name                record_modifier
            Match               *
            Record_Remove_Key   passport_number
            Record_Remove_Key   ssn
            Record_Remove_Key   credit_card
        [FILTER]
            Name                grep
            Match               *
            Regex               log     (?i)((?!password).)*
    EOF
  ]
}
