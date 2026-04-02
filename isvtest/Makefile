# Quick reference for common test commands

.PHONY: help test-all test-common test-k8s test-slurm test-local-k8s test-local-k8s-common test-local-k8s-gpu-stress test-minikube test-minikube-common test-k3s test-k3s-common

help:
	@echo "ISV Test Commands:"
	@echo "  make test-all                  - Run all validation tests"
	@echo "  make test-common               - Run common GPU/driver tests"
	@echo "  make test-k8s                  - Run Kubernetes tests"
	@echo "  make test-slurm                - Run Slurm tests"
	@echo "  make test-local-k8s            - Run k8s tests with microk8s"
	@echo "  make test-local-k8s-common     - Run common + k8s with microk8s"
	@echo "  make test-local-k8s-gpu-stress - Run GPU stress test on K8s (5+ min per node)"
	@echo "  make test-minikube             - Run k8s tests with minikube"
	@echo "  make test-minikube-common      - Run common + k8s with minikube"
	@echo "  make test-k3s                  - Run k8s tests with k3s"
	@echo "  make test-k3s-common           - Run common + k8s with k3s"

test-all:
	uv run isvtest all

test-common:
	uv run isvtest common

test-k8s:
	uv run isvtest k8s

test-slurm:
	uv run isvtest slurm

# Local Kubernetes tests using microk8s

test-local-k8s:
	K8S_PROVIDER=microk8s uv run isvtest k8s

test-local-k8s-common:
	K8S_PROVIDER=microk8s uv run pytest src/isvtest/tests -v

test-local-k8s-gpu-stress:
	K8S_PROVIDER=microk8s GPU_MEMORY_GB=4 GPU_STRESS_RUNTIME=30 uv run isvtest k8s -k test_gpu_stress_single_node -v

# Local Kubernetes tests using minikube

test-minikube:
	K8S_PROVIDER=minikube uv run isvtest k8s

test-minikube-common:
	K8S_PROVIDER=minikube uv run pytest src/isvtest/tests -v

# Local Kubernetes tests using k3s

test-k3s:
	K8S_PROVIDER=k3s uv run isvtest k8s

test-k3s-common:
	K8S_PROVIDER=k3s uv run pytest src/isvtest/tests -v
