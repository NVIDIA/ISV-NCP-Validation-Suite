# /// script
# requires-python = ">=3.12"
# dependencies = [
#   'torch>=2.8.0',
# ]
#
# [tool.uv]
# extra-index-url = ["https://download.pytorch.org/whl/cu129"]
# ///
import os
import socket
import time

import torch

h = socket.gethostname()
r = int(os.getenv("GPU_STRESS_RUNTIME", "30"))
m = int(os.getenv("GPU_MEMORY_GB", "16"))
n = torch.cuda.device_count()
if n == 0:
    print(f"FAILURE: No GPUs on {h}")
    exit(1)
print(f"{h}: {n} GPUs, runtime={r}s, memory={m}GB")
sz = int((m * 1e9 / 4 / 4) ** 0.5)
a = [torch.randn(sz, sz, device=f"cuda:{i}", dtype=torch.float32) for i in range(n)]
t0 = time.time()
loops = 0
while time.time() - t0 < r:
    for x in a:
        torch.mm(x, x)
    loops += 1
print(f"SUCCESS: {h} completed {loops} loops with {n} GPU(s)")
