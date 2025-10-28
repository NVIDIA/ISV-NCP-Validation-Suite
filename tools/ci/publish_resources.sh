#!/bin/bash

# Set NGC_CLI_ORG and NGC_CLI_TEAM environment variables if NGC_ORG and NGC_TEAM are set
if [ -n "$NGC_ORG" ] && [ -n "$NGC_TEAM" ]; then
    export NGC_CLI_ORG=$NGC_ORG
    export NGC_CLI_TEAM=$NGC_TEAM
fi

# Check NGC_CLI_ORG and NGC_CLI_TEAM environment variable is set
if [ -z "$NGC_CLI_ORG" ] || [ -z "$NGC_CLI_TEAM" ]; then
    echo "Error: NGC_CLI_ORG and/or NGC_CLI_TEAM environment variables are not set"
    exit 1
fi

# Check NGC_API_KEY environment variable is set
if [ -z "$NGC_API_KEY" ]; then
    echo "Error: NGC_API_KEY environment variable is not set"
    exit 1
fi

# Check NEXT_VERSION environment variable is set
if [ -z "$NEXT_VERSION" ]; then
    echo "Error: NEXT_VERSION environment variable is not set"
    exit 1
fi
RESOURCE_VERSION=$NEXT_VERSION

# Check if semantic release is skipped (on MRs we allow manual trigger)
if [ -z "${CI_MERGE_REQUEST_IID}" ]; then
    if [ "${SKIP_SEMANTIC_RELEASE}" == "true" ]; then
        echo "Non semantic-release detected, skipping resource push"
        exit 0
    fi

    if [ -z "${NEED_SEMANTIC_RELEASE}" ] || [ "${NEED_SEMANTIC_RELEASE}" == "false" ]; then
        echo "NEED_SEMANTIC_RELEASE is undefined or false, skipping resource push"
        exit 0
    fi
else
    echo "MR pipeline detected - skipping semantic release checks (manual trigger)"
    RESOURCE_VERSION="dev-$NEXT_VERSION"
fi

ngc config current
export NGC_CLI_TRACE_DISABLE=true

# Helper function to create or update an NGC resource
upload_resource() {
    local RESOURCE_NAME="$1"
    local SHORT_DESC="$2"
    local DISPLAY_NAME="$3"
    local SOURCE_PATH="$4"

    # Create the resource if it doesn't exist
    RESOURCE_LIST=$(ngc registry resource list $NGC_CLI_ORG/$NGC_CLI_TEAM/$RESOURCE_NAME --format_type json)
    RESOURCE_COUNT=$(echo "$RESOURCE_LIST" | jq 'length')
    if [ "$RESOURCE_COUNT" -eq 0 ]; then
        ngc registry resource create \
            --org "${NGC_CLI_ORG}" \
            --team "${NGC_CLI_TEAM}" \
            --application OTHER \
            --framework OTHER \
            --format json \
            --precision OTHER \
            --short-desc "${SHORT_DESC}" \
            --display-name "${DISPLAY_NAME}" \
            "$NGC_CLI_ORG/$NGC_CLI_TEAM/$RESOURCE_NAME"
        echo "${DISPLAY_NAME} resource created"
    fi

    # Get current NGC version
    CURRENT_NGC_VERSION=$(echo "$RESOURCE_LIST" | jq -r '.[0].latestVersionIdStr // empty')

    # Only update if version is different
    if [ "$CURRENT_NGC_VERSION" != "$RESOURCE_VERSION" ]; then
        echo "Uploading ${DISPLAY_NAME} version $RESOURCE_VERSION"
        ngc registry resource upload-version $NGC_CLI_ORG/$NGC_CLI_TEAM/$RESOURCE_NAME:$RESOURCE_VERSION --source "$SOURCE_PATH"

        # Only update "latest" alias for release builds (not MRs or dev versions)
        if [ -z "${CI_MERGE_REQUEST_IID:-}" ] && [[ ! "$RESOURCE_VERSION" =~ ^dev- ]]; then
            LATEST_VERSION_INFO=$(ngc registry resource info $NGC_CLI_ORG/$NGC_CLI_TEAM/$RESOURCE_NAME:latest --format_type json 2>/dev/null) || LATEST_VERSION_INFO=""
            if [ -z "$LATEST_VERSION_INFO" ] || [ "$LATEST_VERSION_INFO" == "[]" ] || [ "$LATEST_VERSION_INFO" == "{}" ]; then
                echo "Creating 'latest' version for ${DISPLAY_NAME}"
            else
                echo "Overwriting 'latest' version for ${DISPLAY_NAME}"
                if ngc registry resource remove $NGC_CLI_ORG/$NGC_CLI_TEAM/$RESOURCE_NAME:latest -y; then
                    sleep 10 # give NGC time to remove the version
                else
                    echo "Warning: Failed to remove existing 'latest' version, upload may fail"
                fi
            fi
            ngc registry resource upload-version $NGC_CLI_ORG/$NGC_CLI_TEAM/$RESOURCE_NAME:latest --source "$SOURCE_PATH"
        else
            echo "Skipping 'latest' alias update for non-release build"
        fi
    else
        echo "${DISPLAY_NAME} resource version is up to date: $RESOURCE_VERSION"
    fi
}

# ------------------------------------------------------------------------------------------------
# NCP ISV Lab Scripts (install.sh and configs)
if [ -f "install.sh" ]; then
    upload_resource \
        "ncp-isv-lab-scripts" \
        "NCP ISV Labs installation script and configs" \
        "NCP ISV Lab Scripts" \
        "install.sh"
else
    echo "Warning: install.sh not found, skipping scripts resource upload"
fi

# ------------------------------------------------------------------------------------------------
# NCP ISV Lab Python Wheels
# Build wheels if dist/ doesn't exist or is empty
if [ ! -d "dist" ] || [ -z "$(ls -A dist/*.whl 2>/dev/null)" ]; then
    echo "Building Python wheels..."
    mkdir -p dist
    uv build isvctl/ -o dist
    uv build isvtest/ -o dist
    uv build isvreporter/ -o dist
fi

# Package wheels and configs into a single tarball for easy download via NGC API
# (NGC API doesn't allow listing files, so we need a predictable single file)
if [ -d "dist" ] && [ -n "$(ls -A dist/*.whl 2>/dev/null)" ]; then
    echo "Packaging wheels, configs, and docs into wheels.tar.gz..."

    # Create temp directory with wheels, configs (stubs are inside configs/), and docs
    PACKAGE_DIR=$(mktemp -d)
    cp dist/*.whl "$PACKAGE_DIR/"
    cp -r isvctl/configs "$PACKAGE_DIR/configs"
    cp -r docs "$PACKAGE_DIR/docs"

    tar -czf wheels.tar.gz -C "$PACKAGE_DIR" .
    rm -rf "$PACKAGE_DIR"

    upload_resource \
        "ncp-isv-lab-wheels" \
        "NCP ISV Labs Python wheel packages (isvctl, isvtest, isvreporter) with configs and docs" \
        "NCP ISV Lab Wheels" \
        "wheels.tar.gz"

    rm -f wheels.tar.gz
else
    echo "Warning: No wheel files found in dist/, skipping wheels resource upload"
fi
