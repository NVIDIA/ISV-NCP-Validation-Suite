#!/bin/bash
# Example CPU job script for SlurmSbatchWorkload
#
# Variables (substitute via config):
#   PARTITION - Slurm partition to use (default: cpu)
#   NODES - Number of nodes to request (default: 1)
#   CPUS_PER_TASK - CPUs per task (default: 4)
#   TIME_LIMIT - Job time limit in HH:MM:SS format (default: 00:10:00)
#   JOB_NAME - Name for the job (default: isvtest-cpu-job)

#SBATCH --job-name={{JOB_NAME}}
#SBATCH --partition={{PARTITION}}
#SBATCH --nodes={{NODES}}
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task={{CPUS_PER_TASK}}
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
echo "CPUs per Task: $SLURM_CPUS_PER_TASK"
echo "=========================================="

# Run on all nodes
echo ""
echo "Node Information:"
srun bash -c 'echo "$(hostname): $(nproc) CPUs, $(free -h | grep Mem | awk '\''{print $2}'\'') RAM"'

# Simple compute test
echo ""
echo "Running simple compute verification..."
srun python3 -c "
import multiprocessing
import time

def cpu_work(n):
    \"\"\"Simple CPU-bound work.\"\"\"
    total = 0
    for i in range(n):
        total += i * i
    return total

if __name__ == '__main__':
    cpu_count = multiprocessing.cpu_count()
    print(f'Available CPUs: {cpu_count}')

    start = time.time()
    result = cpu_work(1000000)
    elapsed = time.time() - start

    print(f'Compute test completed in {elapsed:.2f}s')
    print('SUCCESS: CPU compute verified')
"

echo ""
echo "Job completed successfully"
