variable "aws_region" {
  description = "AWS region to deploy EKS cluster and networking"
  type        = string
  default     = "eu-west-2"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "jason-birchall-rca-agent"
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EC2 instance type for EKS worker nodes"
  type        = string
  default     = "t3.small"
}

variable "desired_capacity" {
  description = "Desired number of worker nodes in the node group"
  type        = number
  default     = 3
}

variable "min_capacity" {
  description = "Minimum number of nodes in the node group (for auto-scaling)"
  type        = number
  default     = 3
}

variable "max_capacity" {
  description = "Maximum number of nodes in the node group (for auto-scaling)"
  type        = number
  default     = 3
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# Optionally specify which availability zones to use (for VPC subnets)
variable "azs" {
  description = "List of Availability Zones for subnets"
  type        = list(string)
  default     = []
}

# Variables for IRSA (IAM Role for Service Account)
variable "irsa_sa_name" {
  description = "Kubernetes ServiceAccount name for read-only agent"
  type        = string
  default     = "readonly-agent"
}

variable "irsa_sa_namespace" {
  description = "Kubernetes namespace for the read-only agent ServiceAccount"
  type        = string
  default     = "default"
}
