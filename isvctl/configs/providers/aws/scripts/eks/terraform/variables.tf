# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

# AWS EKS GPU Cluster - Variables
# Customize these values in terraform.tfvars or via CLI

# -----------------------------------------------------------------------------
# General Configuration
# -----------------------------------------------------------------------------

variable "region" {
  description = "AWS region to deploy the cluster"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "cluster_name_prefix" {
  description = "Prefix for the EKS cluster name"
  type        = string
  default     = "isvtest-eks"
}

# -----------------------------------------------------------------------------
# VPC Configuration
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "single_nat_gateway" {
  description = "Use a single NAT gateway (cost savings for dev/test)"
  type        = bool
  default     = true
}

# -----------------------------------------------------------------------------
# EKS Configuration
# -----------------------------------------------------------------------------

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.32"
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "List of CIDR blocks to allow access to the EKS API server endpoint. MUST be set to your IP address(es). Example: [\"YOUR.IP.ADDRESS/32\"]"
  type        = list(string)
  default     = ["203.0.113.0/24"]  # RFC 5737 TEST-NET-3 - non-routable, must override with your IP
}

# -----------------------------------------------------------------------------
# System Node Group Configuration
# -----------------------------------------------------------------------------

variable "system_node_instance_types" {
  description = "Instance types for system (non-GPU) node group"
  type        = list(string)
  default     = ["m5.large"]
}

variable "system_node_min_size" {
  description = "Minimum number of system nodes"
  type        = number
  default     = 1
}

variable "system_node_max_size" {
  description = "Maximum number of system nodes"
  type        = number
  default     = 3
}

variable "system_node_desired_size" {
  description = "Desired number of system nodes"
  type        = number
  default     = 2
}

# -----------------------------------------------------------------------------
# GPU Node Group Configuration
# -----------------------------------------------------------------------------

variable "gpu_node_instance_types" {
  description = <<-EOT
    Instance types for GPU node group.
    Common options:
    - g4dn.xlarge   (1x T4, 16GB)     - Development, small models
    - g5.xlarge     (1x A10G, 24GB)   - Development, small models (16GB RAM, no NIM)
    - g5.2xlarge    (1x A10G, 24GB)   - Development, NIM inference (32GB RAM)
    - g5.12xlarge   (4x A10G, 24GB)   - Multi-GPU workloads
    - p4d.24xlarge  (8x A100, 40GB)   - Large models, training
    - p5.48xlarge   (8x H100, 80GB)   - LLM inference, training
  EOT
  type        = list(string)
  default     = ["g5.2xlarge"]
}

variable "gpu_node_min_size" {
  description = "Minimum number of GPU nodes"
  type        = number
  default     = 0
}

variable "gpu_node_max_size" {
  description = "Maximum number of GPU nodes"
  type        = number
  default     = 4
}

variable "gpu_node_desired_size" {
  description = "Desired number of GPU nodes"
  type        = number
  default     = 1
}

variable "gpu_node_volume_size" {
  description = "Root volume size for GPU nodes (GB)"
  type        = number
  default     = 200
}

variable "gpu_node_taints" {
  description = "Apply nvidia.com/gpu taint to GPU nodes (isolates GPU workloads)"
  type        = bool
  default     = false
}

# -----------------------------------------------------------------------------
# GPU Operator Configuration
# -----------------------------------------------------------------------------

variable "install_gpu_operator" {
  description = "Install NVIDIA GPU Operator via Helm"
  type        = bool
  default     = true
}

variable "gpu_operator_version" {
  description = "NVIDIA GPU Operator Helm chart version"
  type        = string
  default     = "v24.9.0"
}

variable "mig_strategy" {
  description = <<-EOT
    MIG (Multi-Instance GPU) strategy for the GPU Operator.
    Valid values:
    - "none"   - MIG disabled (default, recommended for A10G/g5 instances)
    - "single" - Single MIG strategy (for MIG-capable GPUs like A100/H100)
    - "mixed"  - Mixed MIG strategy
  EOT
  type        = string
  default     = "none"

  validation {
    condition     = contains(["none", "single", "mixed"], var.mig_strategy)
    error_message = "mig_strategy must be one of: none, single, mixed"
  }
}

# -----------------------------------------------------------------------------
# Storage Configuration
# -----------------------------------------------------------------------------

variable "enable_efs" {
  description = "Enable EFS for ReadWriteMany storage (required for NIM model cache)"
  type        = bool
  default     = true
}
