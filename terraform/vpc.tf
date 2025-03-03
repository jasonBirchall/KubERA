resource "aws_vpc" "eks_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.cluster_name}-vpc"
  }
}

# Get availability zones (if not provided via var.azs)
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  # Use either provided AZs or first two AZs from the region for high availability
  cluster_azs = length(var.azs) > 0 ? var.azs : slice(data.aws_availability_zones.available.names, 0, 2)
}

# Create two public subnets (one in each AZ) for NAT gateways and potential LoadBalancers
resource "aws_subnet" "public" {
  count                   = length(local.cluster_azs)
  vpc_id                  = aws_vpc.eks_vpc.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index) # e.g., splits /16 into /20 subnets
  availability_zone       = local.cluster_azs[count.index]
  map_public_ip_on_launch = true # auto-assign public IPs in public subnets

  tags = {
    Name       = "${var.cluster_name}-public-${local.cluster_azs[count.index]}"
    Kubernetes = "public"
  }
}

# Create corresponding private subnets (one in each AZ) for EKS nodes and control plane endpoints
resource "aws_subnet" "private" {
  count                   = length(local.cluster_azs)
  vpc_id                  = aws_vpc.eks_vpc.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index + length(local.cluster_azs))
  availability_zone       = local.cluster_azs[count.index]
  map_public_ip_on_launch = false # no public IPs in private subnets

  tags = {
    Name       = "${var.cluster_name}-private-${local.cluster_azs[count.index]}"
    Kubernetes = "private"
  }
}

# Internet Gateway for the VPC (to allow outbound to internet from public subnets)
resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.eks_vpc.id
  tags = {
    Name = "${var.cluster_name}-igw"
  }
}

# NAT Gateways (one per AZ for high availability)
resource "aws_eip" "nat" {
  count = length(local.cluster_azs)
  vpc   = true
  tags = {
    Name = "${var.cluster_name}-nat-eip-${local.cluster_azs[count.index]}"
  }
}

resource "aws_nat_gateway" "nat" {
  count         = length(local.cluster_azs)
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags = {
    Name = "${var.cluster_name}-nat-${local.cluster_azs[count.index]}"
  }
}

# Route table for public subnets (routes internet traffic to IGW)
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.eks_vpc.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }
  tags = {
    Name = "${var.cluster_name}-public-rt"
  }
}

# Associate public subnets with the public route table
resource "aws_route_table_association" "public_assoc" {
  count          = length(local.cluster_azs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Route tables for private subnets (each with a route to its AZ's NAT Gateway for outbound internet)
resource "aws_route_table" "private" {
  count  = length(local.cluster_azs)
  vpc_id = aws_vpc.eks_vpc.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat[count.index].id
  }
  tags = {
    Name = "${var.cluster_name}-private-rt-${local.cluster_azs[count.index]}"
  }
}

# Associate private subnets with their respective private route tables
resource "aws_route_table_association" "private_assoc" {
  count          = length(local.cluster_azs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

