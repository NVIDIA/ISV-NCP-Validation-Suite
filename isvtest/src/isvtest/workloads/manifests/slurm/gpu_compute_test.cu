// Minimal CUDA test: allocate GPU memory, memset, verify on host
#include <cuda_runtime.h>
#include <stdio.h>

int main() {
    float *d_data;
    size_t size = 1024 * sizeof(float);

    if (cudaMalloc((void**)&d_data, size) != cudaSuccess) {
        return 1;
    }
    if (cudaMemset(d_data, 42, size) != cudaSuccess) {
        cudaFree(d_data);
        return 1;
    }

    float h_data[1024];
    if (cudaMemcpy(h_data, d_data, size, cudaMemcpyDeviceToHost) != cudaSuccess) {
        cudaFree(d_data);
        return 1;
    }

    cudaFree(d_data);
    printf("GPU_COMPUTE_OK\n");
    return 0;
}
