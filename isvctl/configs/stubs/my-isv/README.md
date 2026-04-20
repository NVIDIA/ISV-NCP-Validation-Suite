# my-isv scaffold

Copy-and-fill-in stubs for adding your own platform to the validation suite.

Each stub ships with a TODO block and two behaviors:

- **Default run** -- exits with `"Not implemented - ..."`, making it obvious where to fill in your platform's API calls.
- **Demo mode** (`ISVCTL_DEMO_MODE=1`) -- returns dummy-success JSON so the whole pipeline runs end-to-end without any cloud. Used by `make demo-test`.

## The three pieces that make this work

```text
tests/*.yaml               ← contract   (what to validate; platform-agnostic)
                  │
                  ▼ imported by
providers/my-isv/*.yaml    ← wiring     (which stubs implement each step)
                  │
                  ▼ invokes
stubs/my-isv/<domain>/*.py ← scaffold   (copy these; fill in TODO blocks)
```

The `tests/` layer is the NVIDIA-owned validation contract. You never change
it. You copy the `stubs/my-isv/` and `providers/my-isv/` trees, rename them to
your platform, and implement the TODOs.

## Domains

| Domain | Stubs | Contract | Provider YAML | AWS reference |
|--------|-------|----------|---------------|---------------|
| `iam/` | 3 | [`tests/iam.yaml`](../../tests/iam.yaml) | [`providers/my-isv/iam.yaml`](../../providers/my-isv/iam.yaml) | [`stubs/aws/iam/`](../aws/iam/) |
| `control-plane/` | 10 | [`tests/control-plane.yaml`](../../tests/control-plane.yaml) | [`providers/my-isv/control-plane.yaml`](../../providers/my-isv/control-plane.yaml) | [`stubs/aws/control-plane/`](../aws/control-plane/) |
| `vm/` | 9 | [`tests/vm.yaml`](../../tests/vm.yaml) | [`providers/my-isv/vm.yaml`](../../providers/my-isv/vm.yaml) | [`stubs/aws/vm/`](../aws/vm/) |
| `bare_metal/` | 12 | [`tests/bare_metal.yaml`](../../tests/bare_metal.yaml) | [`providers/my-isv/bare_metal.yaml`](../../providers/my-isv/bare_metal.yaml) | [`stubs/aws/bare_metal/`](../aws/bare_metal/) |
| `network/` | 16 | [`tests/network.yaml`](../../tests/network.yaml) | [`providers/my-isv/network.yaml`](../../providers/my-isv/network.yaml) | [`stubs/aws/network/`](../aws/network/) |
| `image-registry/` | 7 | [`tests/image-registry.yaml`](../../tests/image-registry.yaml) | [`providers/my-isv/image-registry.yaml`](../../providers/my-isv/image-registry.yaml) | [`stubs/aws/image-registry/`](../aws/image-registry/) |
| `k8s/` | 9 shell | [`tests/k8s.yaml`](../../tests/k8s.yaml) | -- | [`stubs/aws/eks/`](../aws/eks/) |
| `slurm/` | 2 shell | [`tests/slurm.yaml`](../../tests/slurm.yaml) | -- | -- |

See [`tests/README.md`](../../tests/README.md) for the per-step / per-field breakdown.

## Usage

**1. Preview the pipeline with no cloud (~10s):**

```bash
make demo-test
```

**2. Copy the scaffold and the wiring to a new name:**

```bash
cp -r isvctl/configs/stubs/my-isv/     isvctl/configs/stubs/acme/
cp -r isvctl/configs/providers/my-isv/ isvctl/configs/providers/acme/
```

**3. Update `providers/acme/*.yaml` to point at `stubs/acme/`** (search & replace `my-isv` -> `acme`).

**4. Implement each stub** -- each has a `TODO:` block with pseudocode and a link to the AWS reference implementation.

**5. Run for real (no demo flag):**

```bash
uv run isvctl test run -f isvctl/configs/providers/acme/vm.yaml
```

## Anatomy of a stub

Every Python stub in this tree follows the same shape -- this is what you're
copying:

```python
DEMO_MODE = os.environ.get("ISVCTL_DEMO_MODE") == "1"

def main() -> int:
    args = parser.parse_args()
    result = {"success": False, "platform": "<domain>", ...}

    # ╔═══════════════════════════════════════════════════════╗
    # ║  TODO: Replace with your platform's API calls         ║
    # ║  Example (pseudocode):                                ║
    # ║    client = MyCloudClient(region=args.region)         ║
    # ║    ...                                                ║
    # ╚═══════════════════════════════════════════════════════╝

    if DEMO_MODE:
        # dummy-success values so make demo-test passes
        result["success"] = True
        result[...] = ...
    else:
        result["error"] = "Not implemented - replace with your platform's ... logic"

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1
```

Keep the output field names in the documented contract -- the validations
read specific keys (`instance_id`, `state`, `public_ip`, etc.). The AWS
reference implementation is the source of truth for what "correct" output
looks like.

## See also

- [`providers/my-isv/`](../../providers/my-isv/) -- the YAML wiring that invokes these stubs
- [`tests/README.md`](../../tests/README.md) -- per-step breakdown and JSON field reference
- [AWS reference](../../../../docs/references/aws.md) -- working implementation of every stub in this tree
- [External Validation Guide](../../../../docs/guides/external-validation-guide.md) -- writing scripts, JSON output format
