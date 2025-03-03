# IAM role for EKS Cluster Control Plane
resource "aws_iam_role" "eks_cluster_role" {
  name = "${var.cluster_name}-eks-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "eks.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
  tags = {
    Name = "${var.cluster_name}-ClusterRole"
  }
}

# Attach EKS cluster IAM managed policy (allows EKS to manage AWS resources like EC2 on your behalf)
resource "aws_iam_role_policy_attachment" "eks_cluster_attach" {
  role       = aws_iam_role.eks_cluster_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# IAM role for EKS Worker Nodes (Node Group)
resource "aws_iam_role" "eks_node_role" {
  name = "${var.cluster_name}-eks-node-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "ec2.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
  tags = {
    Name = "${var.cluster_name}-NodeRole"
  }
}

# Attach necessary IAM policies to worker node role (least privilege for EKS nodes)
resource "aws_iam_role_policy_attachment" "eks_worker_node_attach_1" {
  role       = aws_iam_role.eks_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}
resource "aws_iam_role_policy_attachment" "eks_worker_node_attach_2" {
  role       = aws_iam_role.eks_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}
resource "aws_iam_role_policy_attachment" "eks_worker_node_attach_3" {
  role       = aws_iam_role.eks_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# EKS Cluster Creation
resource "aws_eks_cluster" "eks_cluster" {
  name     = var.cluster_name
  version  = var.cluster_version
  role_arn = aws_iam_role.eks_cluster_role.arn

  # Specify subnets for EKS control plane (private subnets for private API access)
  vpc_config {
    subnet_ids              = aws_subnet.private[*].id # control plane ENIs in private subnets
    endpoint_private_access = true                     # private API endpoint enabled
    endpoint_public_access  = false                    # disable public API endpoint for security
  }

  # Enable Kubernetes RBAC (on by default for EKS; here just noting for clarity)
  enabled_cluster_log_types = ["api", "audit"] # send API server and audit logs to CloudWatch (optional for security visibility)

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_attach]
}

# EKS Managed Node Group (deploys worker nodes)
resource "aws_eks_node_group" "nodes" {
  cluster_name    = aws_eks_cluster.eks_cluster.name
  node_group_name = "${var.cluster_name}-node-group"
  node_role_arn   = aws_iam_role.eks_node_role.arn
  subnet_ids      = aws_subnet.private[*].id # place nodes in private subnets
  instance_types  = [var.node_instance_type]
  disk_size       = 20          # 20 GB EBS volume for nodes
  capacity_type   = "ON_DEMAND" # use on-demand instances (could be changed to SPOT for cost savings with careful planning)

  scaling_config {
    desired_size = var.desired_capacity
    min_size     = var.min_capacity
    max_size     = var.max_capacity
  }

  # Ensure dependency on cluster creation
  depends_on = [
    aws_eks_cluster.eks_cluster,
    aws_iam_role_policy_attachment.eks_worker_node_attach_1,
    aws_iam_role_policy_attachment.eks_worker_node_attach_2,
    aws_iam_role_policy_attachment.eks_worker_node_attach_3
  ]

  tags = {
    Name = "${var.cluster_name}-workers"
  }
}
