# External Validation Guide

This guide explains how to create custom validation tests using the ISV validation framework **without modifying the repository**. You can use `isvctl` as a standalone tool with your own scripts and configuration files.

For the full configuration reference, see the [Configuration Guide](configuration.md).

## Overview

The ISV validation framework uses a **step-based architecture**:

```text
Config (YAML) --> Script (any language) --> JSON output --> Validations (assertions)
```

- **Scripts do the work** - Launch VMs, create clusters, test APIs (Python, Bash, Go, etc.)
- **Scripts output JSON** - Structured results to stdout
- **Validations check JSON** - Built-in assertion classes verify the output

---

## Quick Start

### 1. Install isvctl

```bash
# From source
git clone git@github.com:NVIDIA/ISV-NCP-Validation-Suite.git
cd ISV-NCP-Validation-Suite
uv sync
```

### 2. Create Your Project

```text
my-validations/
├── config.yaml           # Your validation config
├── scripts/
│   ├── provision.py      # Setup script
│   └── teardown.py       # Cleanup script
└── README.md
```

### 3. Run

```bash
uv run isvctl test run -f config.yaml
```

---

## Writing Scripts

Scripts must:

1. **Output valid JSON to stdout** (this is captured and validated)
2. **Exit 0 for success**, non-zero for failure
3. **Write logs/errors to stderr** (only stdout is captured as JSON)
4. **Include `success` and `platform` fields** in the JSON output

### Python Script Template

```python
#!/usr/bin/env python3
"""Provision cloud resources."""

import argparse
import json
import sys
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision cluster")
    parser.add_argument("--name", required=True, help="Cluster name")
    parser.add_argument("--region", default="us-west-2")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "success": False,
        "platform": "kubernetes",  # or "vm", "network", etc.
    }

    try:
        # Your provisioning logic here
        result["success"] = True
        result["cluster_name"] = args.name
        result["node_count"] = 3
        result["endpoint"] = f"https://{args.name}.example.com"
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        result["error"] = str(e)

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

Bash, Go, Terraform wrappers, or any language works -- as long as valid JSON goes to stdout. See the [Configuration Guide](configuration.md#script-output-and-schema-validation) for more script examples.

---

## Configuration File

Here's a minimal working config:

```yaml
version: "1.0"

commands:
  myplatform:
    phases: ["setup", "test", "teardown"]
    steps:
      - name: launch_instance
        phase: setup
        command: "python3 ./scripts/provision.py"
        args: ["--name", "{{cluster_name}}", "--region", "{{region}}"]
        timeout: 600

      - name: teardown
        phase: teardown
        command: "python3 ./scripts/teardown.py"
        args: ["--instance-id", "{{steps.launch_instance.instance_id}}"]
        timeout: 300

tests:
  platform: myplatform
  cluster_name: "my-validation"

  settings:
    region: "us-west-2"
    cluster_name: "test-cluster"

  validations:
    launch_checks:
      step: launch_instance
      checks:
        - StepSuccessCheck: {}
        - FieldExistsCheck:
            fields: ["instance_id", "public_ip"]
        - InstanceStateCheck:
            expected_state: "running"

    ssh_checks:
      step: launch_instance
      checks:
        - SshConnectivityCheck: {}
        - SshGpuCheck:
            expected_gpus: 1

    teardown_checks:
      step: teardown
      checks:
        - StepSuccessCheck: {}
```

For full details on step options, template variables, schemas, and validation configuration, see the [Configuration Guide](configuration.md#config-structure).

---

## Validation Groups

Validations are grouped by meaningful category names. Set `step` at the group level or override per-check:

```yaml
validations:
  # Group-level step applies to all checks in the group
  setup_checks:
    step: provision_cluster
    checks:
      - StepSuccessCheck: {}
      - ClusterHealthCheck: {}

  # Per-check step overrides
  mixed:
    step: provision_cluster       # default
    checks:
      - ClusterHealthCheck: {}    # uses default step
      - StepSuccessCheck:
          step: teardown          # overrides
```

For validation timing and phase control, see the [Configuration Guide](configuration.md#validation-configuration).

---

## Running Validations

```bash
# Run all phases
isvctl test run -f config.yaml

# Verbose output
isvctl test run -f config.yaml -v

# Run specific phase
isvctl test run -f config.yaml --phase setup

# Merge configs (later overrides earlier)
isvctl test run -f base.yaml -f overrides.yaml

# Filter validations with pytest args
isvctl test run -f config.yaml -- -k "SshConnectivity"
isvctl test run -f config.yaml -- -m gpu
isvctl test run -f config.yaml -- -m "not slow"

# Debug: full output on failure
isvctl test run -f config.yaml -v -- -s --tb=long
```

---

## Best Practices

1. **Always output valid JSON** - Even on failure: `{"success": false, "error": "..."}`
2. **Log to stderr** - Keep stdout clean for JSON
3. **Use settings for reusable values** - `region`, `instance_type`, etc.
4. **Set appropriate timeouts** - Account for cloud API latency
5. **Test scripts manually first** - Run standalone to verify JSON output
6. **Keep teardown idempotent** - Safe to re-run
7. **Never hardcode credentials** - Use environment variables or IAM roles

---

## Troubleshooting

**Script output issues:**

```bash
# Test script manually, verify valid JSON
python ./scripts/provision.py --name test 2>/dev/null | jq .
```

**Schema validation failures** - check required fields per schema in the [Configuration Guide](configuration.md#schema-auto-detection).

**SSH validation failures** - ensure step output includes:

- Host: `public_ip`, `host`, or `ssh_host`
- Key: `key_file`, `key_path`, or `ssh_key_path` (must exist, permissions 0600)
- User: `user` or `ssh_user` (default: `"ubuntu"`)

---

## Templates

For common validation scenarios, **pre-built templates** are available in [`isvctl/configs/templates/`](../../isvctl/configs/templates/README.md). These provide a copy-and-customize starting point with skeleton scripts and documented JSON contracts.

| Template | What it tests | Stubs |
|----------|---------------|-------|
| [`iam.yaml`](../../isvctl/configs/templates/iam.yaml) | User create → verify credentials → delete | 3 scripts |
| [`network.yaml`](../../isvctl/configs/templates/network.yaml) | VPC CRUD, subnets, isolation, security, connectivity, traffic | 8 scripts |
| [`vm.yaml`](../../isvctl/configs/templates/vm.yaml) | Launch GPU VM → list → reboot → NIM deploy → teardown | 4 scripts + 2 shared |
| [`bm.yaml`](../../isvctl/configs/templates/bm.yaml) | Launch bare-metal → describe → reboot → NIM → teardown → verify | 5 scripts + 2 shared |
| [`eks.yaml`](../../isvctl/configs/templates/eks.yaml) | Provision K8s GPU cluster → validate nodes/GPU/workloads → teardown | 2 scripts |
| [`control-plane.yaml`](../../isvctl/configs/templates/control-plane.yaml) | API health, access key lifecycle, tenant lifecycle | 10 scripts |
| [`iso.yaml`](../../isvctl/configs/templates/iso.yaml) | Image upload/import → launch instance → teardown | 3 scripts |

```bash
# Copy the templates and implement for your platform
cp -r isvctl/configs/templates/ isvctl/configs/my-isv/
# Edit the stub scripts (each has a TODO block showing what to implement)
uv run isvctl test run -f isvctl/configs/my-isv/vm.yaml
```

Each template has a matching **AWS reference implementation** you can study as a working example. See the [AWS Reference Guide](../references/aws.md) for details.

---

## Related Documentation

- [Configuration Guide](configuration.md) - Full config reference (steps, schemas, validations, templates)
- [Validation Templates](../../isvctl/configs/templates/README.md) - Provider-agnostic templates with full guide
- [AWS Reference Implementation](../references/aws.md) - Working AWS examples for all templates
- [isvctl Package](../packages/isvctl.md) - CLI documentation
- [Local Development](local-development.md) - Development setup
