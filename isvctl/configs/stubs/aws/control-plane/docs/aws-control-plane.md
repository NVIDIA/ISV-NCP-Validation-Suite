# AWS Control Plane Validation Guide

This guide covers validating AWS control plane connectivity, IAM operations, and tenant management.

## Overview

The control plane validation tests verify:

1. **API Health** - Authentication and service connectivity
2. **Access Key Lifecycle** - Create, authenticate, disable, verify rejection, delete (ISVP-173, 174)
3. **Tenant Lifecycle** - Create, list, get info, delete resource groups (ISVP-175-179)

**Architecture:**

- **Scripts**: Platform-specific (boto3) - perform CRUD operations, output JSON
- **Validations**: Platform-agnostic - check JSON output against schemas
- **Phases**: Setup -> Test -> Teardown

## Architecture

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                    AWS Control Plane Validation                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  SETUP PHASE                                                             │
│  ┌────────────────┐  ┌─────────────────────┐  ┌───────────────────┐      │
│  │ check_api.py   │  │ create_access_key.py│  │ create_tenant.py  │      │
│  │ -> api_health  │  │ -> access_key schema│  │ -> tenant schema  │      │
│  └────────────────┘  └─────────────────────┘  └───────────────────┘      │
│                                                                          │
│  TEST PHASE                                                              │
│  ┌─────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐ │
│  │ test_access_key.py  │  │ disable_access_key.py│  │ verify_key_      │ │
│  │ -> auth_result      │  │ -> access_key_status │  │ rejected.py      │ │
│  └─────────────────────┘  └──────────────────────┘  │ -> auth_rejection│ │
│                                                     └──────────────────┘ │
│  ┌─────────────────────┐  ┌─────────────────────┐                        │
│  │ list_tenants.py     │  │ get_tenant.py       │                        │
│  │ -> tenant_list      │  │ -> tenant schema    │                        │
│  └─────────────────────┘  └─────────────────────┘                        │
│                                                                          │
│  TEARDOWN PHASE                                                          │
│  ┌──────────────────────┐  ┌─────────────────────┐                       │
│  │ delete_access_key.py │  │ delete_tenant.py    │                       │
│  │ -> teardown schema   │  │ -> teardown schema  │                       │
│  └──────────────────────┘  └─────────────────────┘                       │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Scripts

| Script | Phase | Output Schema | Description |
|--------|-------|---------------|-------------|
| `check_api.py` | setup | `api_health` | Test API connectivity and authentication |
| `create_access_key.py` | setup | `access_key` | Create IAM user and access key |
| `create_tenant.py` | setup | `tenant` | Create resource group (tenant) |
| `test_access_key.py` | test | `auth_result` | Authenticate with access key |
| `disable_access_key.py` | test | `access_key_status` | Disable access key |
| `verify_key_rejected.py` | test | `auth_rejection` | Verify disabled key is rejected |
| `list_tenants.py` | test | `tenant_list` | List resource groups |
| `get_tenant.py` | test | `tenant` | Get resource group info |
| `delete_access_key.py` | teardown | `teardown` | Delete access key and user |
| `delete_tenant.py` | teardown | `teardown` | Delete resource group |

## Output Schemas

All scripts output JSON that is validated against provider-agnostic schemas:

### api_health

```json
{
  "success": true,
  "account_id": "123456789012",
  "region": "us-west-2",
  "tests": {
    "sts_identity": {"passed": true, "latency_ms": 150},
    "ec2_api": {"passed": true, "latency_ms": 230}
  }
}
```

### access_key

```json
{
  "success": true,
  "access_key_id": "AKIA...",
  "secret_access_key": "...",
  "username": "isv-test-user",
  "user_id": "arn:aws:iam::123456789012:user/isv-test-user"
}
```

### auth_result

```json
{
  "success": true,
  "authenticated": true,
  "identity_id": "arn:aws:iam::123456789012:user/isv-test-user",
  "account_id": "123456789012"
}
```

### tenant

```json
{
  "success": true,
  "group_name": "isv-tenant-test-abc123",
  "group_id": "arn:aws:resource-groups:us-west-2:123456789012:group/isv-tenant-test-abc123"
}
```

## Prerequisites

### AWS CLI

```bash
aws --version  # v2 recommended
```

### AWS Credentials

```bash
# Option 1: AWS CLI configuration
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-west-2

# Option 3: STS temporary credentials
export AWS_ACCESS_KEY_ID=ASIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
```

### Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "APIHealthCheck",
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity",
        "iam:ListUsers",
        "ec2:DescribeRegions",
        "s3:ListBuckets"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AccessKeyLifecycle",
      "Effect": "Allow",
      "Action": [
        "iam:CreateUser",
        "iam:DeleteUser",
        "iam:CreateAccessKey",
        "iam:DeleteAccessKey",
        "iam:UpdateAccessKey"
      ],
      "Resource": "arn:aws:iam::*:user/isv-access-key-test-*"
    },
    {
      "Sid": "TenantLifecycle",
      "Effect": "Allow",
      "Action": [
        "resource-groups:CreateGroup",
        "resource-groups:DeleteGroup",
        "resource-groups:ListGroups",
        "resource-groups:GetGroup",
        "resource-groups:GetTags",
        "tag:GetResources"
      ],
      "Resource": "*"
    }
  ]
}
```

## Quick Start

```bash
# Install dependencies
uv sync

# Run control plane validation
uv run isvctl test run -f isvctl/configs/aws-control-plane.yaml
```

**Duration**: ~30 seconds

## Example Output

```shell
============================================================
ORCHESTRATION RESULTS
============================================================
[PASS] SETUP   : check_api: passed; create_access_key: passed; create_tenant: passed
  [check_api] Schema(api_health): PASSED
  [check_api] FieldExistsCheck: PASSED - All required fields present: account_id, tests
  [check_api] FieldValueCheck: PASSED - success=True
  [create_access_key] Schema(access_key): PASSED
  [create_access_key] AccessKeyCreatedCheck: PASSED - Access key AKIAY32T... created for isv-access-key-test-xxx
  [create_tenant] Schema(tenant): PASSED
  [create_tenant] TenantCreatedCheck: PASSED - Tenant 'isv-tenant-test-xxx' created
[PASS] TEST    : test_access_key: passed; disable_access_key: passed; verify_key_rejected: passed; list_tenants: passed; get_tenant: passed
  [test_access_key] Schema(auth_result): PASSED
  [test_access_key] AccessKeyAuthenticatedCheck: PASSED - Authenticated as arn:aws:iam::xxx:user/isv-access-key-test-xxx
  [disable_access_key] Schema(access_key_status): PASSED
  [disable_access_key] AccessKeyDisabledCheck: PASSED - Access key disabled (Inactive)
  [verify_key_rejected] Schema(auth_rejection): PASSED
  [verify_key_rejected] AccessKeyRejectedCheck: PASSED - Disabled key correctly rejected (InvalidClientTokenId)
  [list_tenants] Schema(tenant_list): PASSED
  [list_tenants] TenantListedCheck: PASSED - Tenant 'isv-tenant-test-xxx' found in list
  [get_tenant] Schema(tenant): PASSED
  [get_tenant] TenantInfoCheck: PASSED - Tenant 'isv-tenant-test-xxx' info retrieved
[PASS] TEARDOWN: delete_access_key: passed; delete_tenant: passed
  [delete_access_key] StepSuccessCheck: PASSED - Teardown completed successfully
  [delete_tenant] StepSuccessCheck: PASSED - Teardown completed successfully
------------------------------------------------------------
[PASS] All phases completed successfully
```

## Configuration

```yaml
# isvctl/configs/aws-control-plane.yaml
version: "1.0"

commands:
  control_plane:
    steps:
      - name: check_api
        phase: setup
        command: "python3 ./stubs/aws/control-plane/check_api.py"
        args: ["--region", "{{region}}", "--services", "{{services}}"]

      # ... more steps ...

tests:
  platform: control_plane
  settings:
    region: "us-west-2"
    services: "ec2,s3,iam,sts"

  validations:
    api_health:
      step: check_api
      checks:
        - FieldExistsCheck:
            fields: ["account_id", "tests"]
        - FieldValueCheck:
            field: "success"
            expected: true
```

### Key Configuration Options

| Field | Description |
|-------|-------------|
| `phase` | Step phase: `setup`, `test`, or `teardown` |
| `output_schema` | Explicit schema (auto-detected from step name if not set) |
| `sensitive_args` | Args to mask in logs (e.g., `["--my-secret"]`) |
| `timeout` | Command timeout in seconds |
| `continue_on_failure` | Continue to next step even if this step fails |

## Security

### Sensitive Argument Masking

Sensitive arguments are automatically masked in logs:

```shell
# These patterns are auto-masked:
--secret-access-key, --password, --token, --api-key, --private-key, --secret, --credential, --auth

# Log output shows:
Command: ... --secret-access-key '***' ...
```

### Custom Sensitive Args

```yaml
steps:
  - name: my_step
    command: "my-script.sh"
    args: ["--my-custom-secret", "{{secret}}"]
    sensitive_args: ["--my-custom-secret"]  # Will be masked as ***
```

## Troubleshooting

### "InvalidClientTokenId" or "SignatureDoesNotMatch"

Credentials are invalid or expired:

```bash
aws sts get-caller-identity
```

### "AccessDenied"

Missing permissions. Ensure your credentials have the IAM permissions listed above.

### IAM Propagation Delays

Access key operations may take 5-20 seconds to propagate. The scripts include retry logic with exponential backoff.

## Related Documentation

- [Configuration Guide](../../../../../docs/guides/configuration.md) - Step-based configuration reference
- [Output Schemas](../../../../../isvctl/src/isvctl/config/output_schemas.py) - JSON schema definitions
