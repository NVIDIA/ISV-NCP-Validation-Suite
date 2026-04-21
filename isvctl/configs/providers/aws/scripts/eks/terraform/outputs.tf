# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# AWS EKS GPU Cluster - Outputs

# -----------------------------------------------------------------------------
# Cluster Information
# -----------------------------------------------------------------------------

output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_version" {
  description = "Kubernetes version"
  value       = module.eks.cluster_version
}

output "cluster_arn" {
  description = "EKS cluster ARN"
  value       = module.eks.cluster_arn
}

output "cluster_endpoint_public_access_cidrs" {
  description = "CIDR blocks allowed to access EKS API endpoint"
  value       = var.cluster_endpoint_public_access_cidrs
}

# -----------------------------------------------------------------------------
# Network Information
# -----------------------------------------------------------------------------

output "region" {
  description = "AWS region"
  value       = var.region
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnets" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnets
}

output "public_subnets" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnets
}

# -----------------------------------------------------------------------------
# Node Group Information
# -----------------------------------------------------------------------------

output "node_groups" {
  description = "EKS managed node groups"
  value       = module.eks.eks_managed_node_groups
}

output "gpu_node_instance_types" {
  description = "GPU node instance types"
  value       = var.gpu_node_instance_types
}

# -----------------------------------------------------------------------------
# Storage Information
# -----------------------------------------------------------------------------

output "efs_file_system_id" {
  description = "EFS file system ID for NIM model cache"
  value       = var.enable_efs ? aws_efs_file_system.nim_cache[0].id : null
}

output "efs_storage_class" {
  description = "EFS StorageClass name"
  value       = var.enable_efs ? "efs-sc" : null
}

# -----------------------------------------------------------------------------
# Configuration Commands
# -----------------------------------------------------------------------------

output "configure_kubectl" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.region}"
}

output "run_tests" {
  description = "Command to run ISV Lab tests"
  value       = <<-EOT
    # Configure kubectl
    aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.region}

    # Set environment variables
    export AWS_REGION=${var.region}
    export EKS_CLUSTER_NAME=${module.eks.cluster_name}
    export NGC_API_KEY=nvapi-XXXXX  # Replace with your NGC API key

    # Run tests
    uv run isvctl test run -f isvctl/configs/providers/aws/config/eks.yaml
  EOT
}

# -----------------------------------------------------------------------------
# Environment Export (for setup.sh)
# -----------------------------------------------------------------------------

output "environment_exports" {
  description = "Environment variables to export for ISV Lab tools"
  value       = <<-EOT
    export AWS_REGION="${var.region}"
    export EKS_CLUSTER_NAME="${module.eks.cluster_name}"
  EOT
}
