terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # AWS provider version
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23" # Kubernetes provider for managing K8s resources
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.8" # Helm provider for deploying charts
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0" # TLS provider for obtaining OIDC thumbprint
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Retrieve cluster authentication token (for Kubernetes and Helm providers)
data "aws_eks_cluster_auth" "cluster" {
  name = aws_eks_cluster.eks_cluster.name
}

# AWS Account ID (used for constructing ARNs in IAM policies)
data "aws_caller_identity" "current" {}

# Kubernetes provider (to manage ServiceAccounts, RBAC, etc., using the EKS cluster)
provider "kubernetes" {
  host                   = aws_eks_cluster.eks_cluster.endpoint
  cluster_ca_certificate = base64decode(aws_eks_cluster.eks_cluster.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.cluster.token

  # Wait until cluster is fully created before using this provider
  load_config_file = false
}

# Helm provider (to install Helm charts into the EKS cluster)
provider "helm" {
  kubernetes {
    host                   = aws_eks_cluster.eks_cluster.endpoint
    cluster_ca_certificate = base64decode(aws_eks_cluster.eks_cluster.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.cluster.token
    load_config_file       = false
  }
}

