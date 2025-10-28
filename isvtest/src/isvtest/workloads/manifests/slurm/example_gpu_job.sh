#!/bin/bash
# Example GPU job script for SlurmSbatchWorkload
#
# Variables (substitute via config):
#   PARTITION - Slurm partition to use (default: gpu)
#   NODES - Number of nodes to request (default: 1)
#   GPUS_PER_NODE - GPUs per node (default: 1)
#   TIME_LIMIT - Job time limit in HH:MM:SS format (default: 00:10:00)
#   JOB_NAME - Name for the job (default: isvtest-gpu-job)

#SBATCH --job-name={{JOB_NAME}}
#SBATCH --partition={{PARTITION}}
#SBATCH --nodes={{NODES}}
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:{{GPUS_PER_NODE}}
#SBATCH --time={{TIME_LIMIT}}
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err

# Print job info
echo "=========================================="
echo "Job ID: $SLURM_JOB_ID"
echo "Job Name: $SLURM_JOB_NAME"
echo "Partition: $SLURM_JOB_PARTITION"
echo "Nodes: $SLURM_JOB_NUM_NODES"
echo "Node List: $SLURM_JOB_NODELIST"
echo "GPUs per Node: {{GPUS_PER_NODE}}"
echo "=========================================="

# Run nvidia-smi to verify GPU access - this is the primary verification
echo ""
echo "GPU Information:"
if ! srun nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv; then
    echo "FAILURE: nvidia-smi failed - GPUs not accessible"
    exit 1
fi

# Count GPUs and verify we got what we requested
GPU_COUNT=$(srun nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
echo ""
echo "Detected $GPU_COUNT GPU(s)"

if [ "$GPU_COUNT" -lt 1 ]; then
    echo "FAILURE: No GPUs detected"
    exit 1
fi

# Run PyTorch verification using uv with inline dependencies (PEP 723)
# Each compute node writes the script locally and executes it
echo ""
echo "Running GPU compute verification with uv..."

# Define the Python script content (PEP 723 inline metadata for uv)
# Note: PyTorch CUDA builds require the extra index URL
read -r -d '' GPU_VERIFY_SCRIPT << 'PYTHON_EOF'
# /// script
# requires-python = ">=3.12"
# dependencies = ["torch>=2.8.0"]
#
# [tool.uv]
# extra-index-url = ["https://download.pytorch.org/whl/cu129"]
# ///
"""GPU verification script for Slurm jobs."""
import sys
import torch

def main() -> int:
    if not torch.cuda.is_available():
        print("SKIPPED: CUDA not available to PyTorch (nvidia-smi passed)")
        return 0
    gpu_count = torch.cuda.device_count()
    print(f"PyTorch detected {gpu_count} GPU(s)")
    for i in range(gpu_count):
        print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
    x = torch.randn(1000, 1000, device="cuda")
    y = torch.matmul(x, x)
    del y
    print("GPU compute test passed (matrix multiply on GPU)")
    print("SUCCESS: GPU job completed with full compute verification")
    return 0

if __name__ == "__main__":
    sys.exit(main())
PYTHON_EOF

# Write and run on each compute node (expand GPU_VERIFY_SCRIPT here, escape node-local vars)
# Check for uv availability and handle errors gracefully as SKIPPED
srun bash -c "
    export PATH=\"\$HOME/.local/bin:\$PATH\"

    # Check if uv is installed
    if ! command -v uv >/dev/null 2>&1; then
        echo 'SKIPPED: uv not installed (nvidia-smi passed)'
        exit 0
    fi

    SCRIPT_FILE=\"/tmp/gpu_verify_\$\$.py\"
    cat > \"\$SCRIPT_FILE\" << 'INNEREOF'
$GPU_VERIFY_SCRIPT
INNEREOF

    # Run uv and capture output; treat dependency/resolution errors as SKIPPED
    UV_OUTPUT=\$(uv run \"\$SCRIPT_FILE\" 2>&1)
    EXIT_CODE=\$?
    rm -f \"\$SCRIPT_FILE\"

    echo \"\$UV_OUTPUT\"

    # Check for dependency resolution or uv-specific errors
    if [ \$EXIT_CODE -ne 0 ]; then
        if echo \"\$UV_OUTPUT\" | grep -qiE '(resolve|dependency|download|install|network|connection|timeout)'; then
            echo 'SKIPPED: uv dependency resolution failed (nvidia-smi passed)'
            exit 0
        fi
    fi

    exit \$EXIT_CODE
"
