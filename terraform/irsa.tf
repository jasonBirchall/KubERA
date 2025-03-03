# Enable OIDC provider for the EKS cluster (required for IRSA)
data "tls_certificate" "oidc_thumbprint" {
  url = aws_eks_cluster.eks_cluster.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks_oidc" {
  url             = replace(aws_eks_cluster.eks_cluster.identity[0].oidc[0].issuer, "https://", "")
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc_thumbprint.certificates[0].sha1_fingerprint]
}

# IAM Role for a Kubernetes Service Account (IRSA) with read-only access to cluster AWS resources
resource "aws_iam_role" "read_only_agent" {
  name = "${var.cluster_name}-readOnly-agent"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Federated = aws_iam_openid_connect_provider.eks_oidc.arn
      },
      Action = "sts:AssumeRoleWithWebIdentity",
      Condition = {
        StringEquals = {
          # Only allow the specific service account in the specified namespace to assume this role
          "${replace(aws_eks_cluster.eks_cluster.identity[0].oidc[0].issuer, "https://", "")}:sub" : "system:serviceaccount:${var.irsa_sa_namespace}:${var.irsa_sa_name}"
        }
      }
    }]
  })
  tags = {
    Name = "${var.cluster_name}-IRSA-ReadOnly"
  }
}

# IAM Policy for read-only access to EKS cluster resources (least privilege)
data "aws_eks_cluster" "cluster" {
  name = aws_eks_cluster.eks_cluster.name
}
# Construct ARNs for cluster and its nodegroups for use in policy
locals {
  cluster_arn    = data.aws_eks_cluster.cluster.arn
  nodegroup_arns = format("%s%s", data.aws_eks_cluster.cluster.arn, "/nodegroup/${var.cluster_name}*")
}

resource "aws_iam_policy" "read_only_policy" {
  name        = "${var.cluster_name}-ReadOnlyAccess"
  description = "Read-only access to describe EKS cluster and related resources"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "eks:DescribeCluster",
          "eks:ListNodegroups",
          "eks:DescribeNodegroup",
          "eks:ListFargateProfiles",
          "eks:DescribeFargateProfile"
        ],
        Resource = [
          local.cluster_arn,
          local.nodegroup_arns
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeTags",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups"
        ],
        Resource = "*"
      }
    ]
  })
}

# Attach the read-only policy to the IRSA role
resource "aws_iam_role_policy_attachment" "attach_read_only" {
  role       = aws_iam_role.read_only_agent.name
  policy_arn = aws_iam_policy.read_only_policy.arn
}

# Kubernetes Service Account associated with the above IAM role (IRSA)
resource "kubernetes_service_account" "readonly_agent" {
  metadata {
    name      = var.irsa_sa_name
    namespace = var.irsa_sa_namespace

    # Attach IAM role to this ServiceAccount via annotation
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.read_only_agent.arn
    }
  }
  automount_service_account_token = true

  depends_on = [aws_eks_node_group.nodes] # ensure cluster (and nodes) are ready before creating SA
}

# Kubernetes RBAC: Bind a read-only ClusterRole to the service account for Kubernetes resource access
resource "kubernetes_cluster_role_binding" "readonly_agent_view" {
  metadata {
    name = "${var.irsa_sa_name}-view-binding"
  }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = "view" # Predefined cluster role that grants read-only access to most Kubernetes resources
  }
  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.readonly_agent.metadata[0].name
    namespace = kubernetes_service_account.readonly_agent.metadata[0].namespace
  }

  depends_on = [kubernetes_service_account.readonly_agent]
}
