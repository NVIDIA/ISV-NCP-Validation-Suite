# Validation Templates

Provider-agnostic templates for ISV Lab validation tests. Copy a template, implement the stub scripts for your platform, and run.

## How It Works

```text
┌──────────────────┐      ┌──────────────────────┐      ┌────────────────────┐
│   YAML Config    │─────▶│  Your Stub Scripts   │─────▶│   Validations      │
│  (steps + args)  │      │  (call your API)     │      │  (check JSON)      │
│                  │      │                      │      │                    │
│  You configure   │      │  YOU IMPLEMENT THESE │      │  Already provided  │
│  step names,     │      │  Output JSON to      │      │  StepSuccessCheck, │
│  args, timeouts  │      │  stdout              │      │  FieldExistsCheck  │
└──────────────────┘      └──────────────────────┘      └────────────────────┘
```

**The contract is JSON.** Your scripts can be written in any language (Python, Bash, Go, etc.). They just need to print a JSON object to stdout with the required fields.

## Available Templates

| Template | Tests | Reference Implementation |
|----------|-------|--------------------------|
| `iam.yaml` | User create -> verify credentials -> delete | `../stubs/aws/iam/` |

## Quick Start (IAM Example)

```bash
# 1. Copy the template
cp -r templates/ my-isv/

# 2. Edit the stub scripts with your platform's API calls
#    - my-isv/stubs/iam/create_user.py      -> call your create user API
#    - my-isv/stubs/iam/test_credentials.py -> verify creds work
#    - my-isv/stubs/iam/delete_user.py      -> call your delete user API

# 3. Update config paths (iam.yaml command: fields)
#    command: "python ./stubs/iam/create_user.py"
#    becomes: "python ./my-isv/stubs/iam/create_user.py"
#    (or adjust the working directory)

# 4. Run
uv run isvctl test run -f isvctl/configs/my-isv/iam.yaml
```

## JSON Output Contract

Each script must print **one JSON object** to stdout. The minimum required fields vary by step:

### `create_user` (setup phase)

```json
{
  "success": true,
  "platform": "iam",
  "username": "isv-test-user-a1b2c3",
  "user_id": "unique-id-from-your-system",
  "access_key_id": "credential-identifier",
  "secret_access_key": "credential-secret"
}
```

### `test_credentials` (test phase)

```json
{
  "success": true,
  "platform": "iam",
  "account_id": "account-or-tenant-id",
  "tests": {
    "identity": { "passed": true },
    "access": { "passed": true }
  }
}
```

### `teardown` (teardown phase)

```json
{
  "success": true,
  "platform": "iam",
  "resources_deleted": ["user:isv-test-user-a1b2c3"],
  "message": "User deleted successfully"
}
```

### On Failure

Any step can report failure by setting `"success": false` and including an `"error"` field:

```json
{
  "success": false,
  "platform": "iam",
  "error": "Connection refused: https://api.example.com/iam"
}
```

## Validations Reference

The template uses these built-in validations (you don't need to modify these):

| Validation | What it checks |
|-----------|----------------|
| `StepSuccessCheck` | `success == true` in JSON output |
| `FieldExistsCheck` | Named fields exist and are non-empty |

Additional validations available in `isvtest/validations/iam.py`:

| Validation | What it checks |
|-----------|----------------|
| `AccessKeyCreatedCheck` | `access_key_id` and `username` exist |
| `AccessKeyAuthenticatedCheck` | `authenticated == true` |
| `TenantCreatedCheck` | `tenant_name` and `tenant_id` exist |

## Tips

- **Any language works** - scripts can be Python, Bash, Go, curl-based, etc.
- **Jinja2 templating** - use `{{steps.create_user.username}}` to pass data between steps
- **Sensitive args** - use `sensitive_args` in the YAML to mask secrets in logs
- **Skip teardown** - set `IAM_SKIP_TEARDOWN=true` to keep resources for debugging
- **Extra fields are fine** - JSON output can include additional fields beyond the required ones
