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

import torch
import torch.nn as nn

h = socket.gethostname()
n = torch.cuda.device_count()
steps = int(os.getenv("TRAIN_STEPS", "50"))
batch = int(os.getenv("TRAIN_BATCH_SIZE", "64"))
hidden = int(os.getenv("TRAIN_HIDDEN_SIZE", "2048"))
lr = float(os.getenv("TRAIN_LR", "0.01"))

if n == 0:
    print(f"FAILURE: No GPUs on {h}")
    exit(1)

print(f"{h}: {n} GPUs, steps={steps}, batch={batch}, hidden={hidden}")

results = []
for gpu in range(n):
    dev = f"cuda:{gpu}"
    model = nn.Sequential(
        nn.Linear(hidden, hidden),
        nn.ReLU(),
        nn.Linear(hidden, hidden),
        nn.ReLU(),
        nn.Linear(hidden, 10),
    ).to(dev)
    optimizer = torch.optim.SGD(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()

    first_loss = 0.0
    last_loss = 0.0
    for step in range(steps):
        x = torch.randn(batch, hidden, device=dev)
        target = torch.randint(0, 10, (batch,), device=dev)
        optimizer.zero_grad()
        loss = loss_fn(model(x), target)
        loss.backward()
        optimizer.step()
        lv = loss.item()
        if step == 0:
            first_loss = lv
        last_loss = lv

    # Verify gradients were computed
    has_grads = all(p.grad is not None and p.grad.abs().sum().item() > 0 for p in model.parameters() if p.requires_grad)
    decreased = last_loss < first_loss
    results.append(
        {
            "gpu": gpu,
            "first_loss": first_loss,
            "last_loss": last_loss,
            "decreased": decreased,
            "has_grads": has_grads,
        }
    )
    status = "ok" if (decreased and has_grads) else "WARN"
    print(
        f"  GPU {gpu}: loss {first_loss:.4f} -> {last_loss:.4f} (decreased={decreased}, grads={has_grads}) [{status}]"
    )

failed = [r for r in results if not r["has_grads"]]
if failed:
    gpus = ", ".join(str(r["gpu"]) for r in failed)
    print(f"FAILURE: No gradients on GPU(s) {gpus}")
    exit(1)

print(f"SUCCESS: {h} trained {steps} steps on {n} GPU(s)")
