#!/bin/bash
#
# install.sh
# Downloads and installs NVIDIA ISV Lab Tools from NGC.
#
# Usage (pipe from curl):
#   export NGC_API_KEY=your_api_key
#   export NGC_ORG=your_org_id
#   export NGC_TEAM=your_team
#   curl -fsSL -H "Authorization: Bearer ${NGC_API_KEY}" \
#     "https://api.ngc.nvidia.com/v2/org/${NGC_ORG}/team/${NGC_TEAM}/resources/ncp-isv-lab-scripts/versions/${VERSION}/files/install.sh" \
#     | bash -s -- "${VERSION}"
#
# Usage (local):
#   ./install.sh [version]
#
# After installation:
#   isvctl test run -f config.yaml
#

set -euo pipefail

VERSION="${1:-latest}"
NGC_ORG="${NGC_ORG:-fcypcg1knhby}"
NGC_TEAM="${NGC_TEAM:-isv-labs-dev}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_step() { echo -e "${GREEN}==>${NC} $1"; }
print_error() { echo -e "${RED}Error:${NC} $1" >&2; }

# Validate NGC organization and team
if [ -z "${NGC_ORG}" ]; then
    print_error "NGC_ORG environment variable is required."
    echo "export NGC_ORG=your_org_id"
    exit 1
fi

if [ -z "${NGC_TEAM}" ]; then
    print_error "NGC_TEAM environment variable is required."
    echo "export NGC_TEAM=your_team"
    exit 1
fi

NGC_API_BASE="https://api.ngc.nvidia.com/v2/org/${NGC_ORG}/team/${NGC_TEAM}"

# Check for required tools
HAS_UV=false
if command -v uv >/dev/null 2>&1; then
    HAS_UV=true
elif ! command -v python3 >/dev/null 2>&1; then
    print_error "Neither 'uv' nor 'python3' is installed."
    echo "Please install 'uv' (recommended) or 'python3'."
    echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    print_error "'curl' is not installed."
    exit 1
fi

# Check for NGC API key
if [ -z "${NGC_API_KEY:-}" ]; then
    print_error "NGC_API_KEY environment variable is required."
    echo "export NGC_API_KEY=your_api_key"
    exit 1
fi

# Create temporary directory
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

print_step "Downloading ISV Lab Tools (version: $VERSION)..."

# Download wheels tarball from NGC API (single file, predictable name)
WHEELS_URL="${NGC_API_BASE}/resources/ncp-isv-lab-wheels/versions/${VERSION}/files/wheels.tar.gz"
WHEELS_TAR="$TMP_DIR/wheels.tar.gz"

if ! curl -fsSL -o "$WHEELS_TAR" \
    -H "Authorization: Bearer ${NGC_API_KEY}" \
    "$WHEELS_URL" 2>/dev/null; then
    print_error "Failed to download wheels (version: $VERSION)"
    echo "Check that the version exists and your API key is valid."
    exit 1
fi

# Extract wheels
print_step "Extracting wheels..."
mkdir -p "$TMP_DIR/wheels"
tar -xzf "$WHEELS_TAR" -C "$TMP_DIR/wheels"

# Find and install wheels
WHEEL_COUNT=$(find "$TMP_DIR/wheels" -name "*.whl" | wc -l)
if [ "$WHEEL_COUNT" -eq 0 ]; then
    print_error "No wheel files found in download"
    exit 1
fi

print_step "Installing $WHEEL_COUNT wheel(s)..."

# Find the isvctl wheel (main entry point) and install as a tool
# uv tool install creates an isolated venv and adds to PATH
ISVCTL_WHEEL=$(find "$TMP_DIR/wheels" -name "isvctl-*.whl" | head -1)
ISVTEST_WHEEL=$(find "$TMP_DIR/wheels" -name "isvtest-*.whl" | head -1)
ISVREPORTER_WHEEL=$(find "$TMP_DIR/wheels" -name "isvreporter-*.whl" | head -1)

if [ -n "$ISVCTL_WHEEL" ]; then
    if [ "$HAS_UV" = true ]; then
        # Install isvctl with its dependencies (isvtest is a dependency)
        UV_ARGS=(tool install --force "$ISVCTL_WHEEL")
        [ -n "$ISVTEST_WHEEL" ] && UV_ARGS+=(--with "$ISVTEST_WHEEL")
        [ -n "$ISVREPORTER_WHEEL" ] && UV_ARGS+=(--with "$ISVREPORTER_WHEEL")
        uv "${UV_ARGS[@]}"
    else
        # Fallback: install in a local venv using python3
        INSTALL_DIR="$HOME/.local/share/nv-isv-tools"
        BIN_DIR="$HOME/.local/bin"

        print_step "uv not found, falling back to python3 venv installation..."
        print_step "Creating virtual environment in $INSTALL_DIR..."

        mkdir -p "$INSTALL_DIR" "$BIN_DIR"
        python3 -m venv "$INSTALL_DIR"

        print_step "Installing wheels with pip..."
        "$INSTALL_DIR/bin/pip" install --upgrade pip >/dev/null
        PIP_ARGS=("$ISVCTL_WHEEL")
        [ -n "$ISVTEST_WHEEL" ] && PIP_ARGS+=("$ISVTEST_WHEEL")
        [ -n "$ISVREPORTER_WHEEL" ] && PIP_ARGS+=("$ISVREPORTER_WHEEL")
        "$INSTALL_DIR/bin/pip" install "${PIP_ARGS[@]}"

        # Link binary
        print_step "Linking binary to $BIN_DIR/isvctl..."
        ln -sf "$INSTALL_DIR/bin/isvctl" "$BIN_DIR/isvctl"

        # Check PATH
        if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
            echo ""
            echo -e "${RED}Warning:${NC} $BIN_DIR is not in your PATH."
            echo "To use isvctl, add it to your PATH:"
            echo "  export PATH=\"\$PATH:$BIN_DIR\""
            echo ""
        fi
    fi
else
    print_error "isvctl wheel not found"
    exit 1
fi

# Extract config files (includes stubs/ subdirectory)
if [ -d "$TMP_DIR/wheels/configs" ]; then
    print_step "Extracting config files..."
    mkdir -p ./configs
    cp -a "$TMP_DIR/wheels/configs/." ./configs/
    chmod +x ./configs/stubs/*/*.sh 2>/dev/null || true
    echo "  Configs extracted to: $(pwd)/configs/"
fi

# Extract documentation
if [ -d "$TMP_DIR/wheels/docs" ]; then
    print_step "Extracting documentation..."
    mkdir -p ./docs
    cp -a "$TMP_DIR/wheels/docs/." ./docs/
    echo "  Docs extracted to: $(pwd)/docs/"
fi

print_step "Installation complete!"
echo ""
echo "Run validation tests:"
echo "  isvctl test run -f configs/k8s.yaml       # Kubernetes"
echo "  isvctl test run -f configs/microk8s.yaml  # MicroK8s"
echo "  isvctl test run -f configs/slurm.yaml     # Slurm"
echo ""
echo "Customize with override files:"
echo "  isvctl test run -f configs/k8s.yaml -f my-overrides.yaml"
if [ -d "./docs" ]; then
    echo ""
    echo "View documentation:"
    echo "  isvctl docs                               # Show docs location"
    echo "  cat docs/README.md                        # Browse docs"
fi
