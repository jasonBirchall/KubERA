output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = aws_eks_cluster.eks_cluster.name
}

output "cluster_endpoint" {
  description = "Endpoint URL of the EKS control plane (API server)"
  value       = aws_eks_cluster.eks_cluster.endpoint
}

output "cluster_certificate_authority" {
  description = "Base64 encoded certificate authority data for the cluster"
  value       = aws_eks_cluster.eks_cluster.certificate_authority[0].data
}

output "eks_node_role_arn" {
  description = "IAM Role ARN for EKS worker nodes"
  value       = aws_iam_role.eks_node_role.arn
}

output "irsa_role_arn" {
  description = "IAM Role ARN for the read-only service account (IRSA)"
  value       = aws_iam_role.read_only_agent.arn
}
