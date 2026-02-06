# Getting Started

This guide covers installation and basic usage of NVIDIA ISV Lab Tools.

## Installation

### Local Development

Clone the repository and install dependencies:

```bash
git clone <repo-url>
cd nv-isv-tools
uv sync
```

Verify installation:

```bash
uv run isvctl --help
```

### Remote ISV Cluster (Pre-built Wheels)

For ISV clusters without source access, install pre-built wheels from NGC:

```bash
# Prerequisites
export NGC_API_KEY=your_api_key  # For downloading from NGC (installer only)
export NGC_ORG=your_org_id
export NGC_TEAM=your_team
export ISV_TOOLS_VERSION=latest
# uv is recommended, but python3 (with venv) works as a fallback
curl -LsSf https://astral.sh/uv/install.sh | sh  # Install uv (recommended)

# Download and run installer
curl -fsSL -H "Authorization: Bearer ${NGC_API_KEY}" \
  "https://api.ngc.nvidia.com/v2/org/${NGC_ORG}/team/${NGC_TEAM}/resources/ncp-isv-lab-scripts/versions/${ISV_TOOLS_VERSION}/files/install.sh" \
  | bash -s -- "${ISV_TOOLS_VERSION}"
```

After installation, configs are extracted to `./configs/`.

> **Note:** `NGC_API_KEY` is only required for downloading from NGC. For running tests, see the environment variables table below.

## Quick Start

### Running Validation Tests

**From source (development):**

```bash
# AWS control plane validation
uv run isvctl test run -f isvctl/configs/aws-control-plane.yaml

# AWS network validation
uv run isvctl test run -f isvctl/configs/aws-network.yaml

# Kubernetes cluster
uv run isvctl test run -f isvctl/configs/k8s.yaml

# Local MicroK8s
uv run isvctl test run -f isvctl/configs/microk8s.yaml

# Slurm cluster
uv run isvctl test run -f isvctl/configs/slurm.yaml
```

**From installed wheel:**

```bash
# Kubernetes
isvctl test run -f configs/k8s.yaml

# Slurm (may require sudo for docker access)
sudo -E env "PATH=$PATH" isvctl test run -f configs/slurm.yaml
```

> **Note:** Slurm tests using docker containers may require `sudo` if the Slurm user
> doesn't have docker group permissions. Use `sudo -E env "PATH=$PATH" isvctl ...`
> to preserve environment and PATH.

### Common Options

```bash
# Verbose output (shows script output on failure)
isvctl test run -f configs/k8s.yaml -v

# Pass extra pytest args
isvctl test run -f configs/k8s.yaml -- -v -s -k "NodeCount"

# Upload results to ISV Lab Service
isvctl test run -f configs/k8s.yaml --lab-id 35

# With ISV software version metadata
isvctl test run -f configs/k8s.yaml --lab-id 35 --isv-software-version "2.1.0-rc3"

# Dry run (validate config without executing)
isvctl test run -f configs/k8s.yaml --dry-run
```

### Remote Deployment

Deploy and run tests on a remote machine:

```bash
uv run isvctl deploy run <target-ip> -f isvctl/configs/k8s.yaml

# With jumphost for air-gapped environments
uv run isvctl deploy run <target-ip> -j <jumphost>:<port> -u ubuntu -f isvctl/configs/k8s.yaml
```

See [Remote Deployment Guide](guides/remote-deployment.md) for details.

## Environment Variables

| Variable | Description |
| -------- | ----------- |
| `AWS_ACCESS_KEY_ID` | AWS access key (for AWS tests) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (for AWS tests) |
| `AWS_REGION` | AWS region (default: us-west-2) |
| `NGC_API_KEY` | Required for downloading from NGC (installer only) |
| `NGC_ORG` | NGC organization ID (defaults to internal org) |
| `NGC_TEAM` | NGC team name (defaults to internal team) |
| `NGC_NIM_API_KEY` | Required for NIM model benchmarks |
| `ISV_CLIENT_ID` | Required for result upload to ISV Lab Service |
| `ISV_CLIENT_SECRET` | Required for result upload to ISV Lab Service |

## Next Steps

- [Configuration Guide](guides/configuration.md) - Learn about configuration options
- [Local Development](guides/local-development.md) - Running tests locally
- [isvctl Reference](packages/isvctl.md) - Full isvctl documentation
