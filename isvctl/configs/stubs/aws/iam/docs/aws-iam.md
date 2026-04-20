# IAM Validation Guide (AWS)

This directory contains lifecycle scripts for AWS IAM validation. The actual IAM operations (user CRUD) are implemented in Python via the `AwsIamProvider` class.

**Provider Architecture**: Uses the `IamProvider` protocol - tests are provider-agnostic. The factory automatically selects the appropriate provider (AWS, Mock, REST) based on config.

## Overview

The IAM validation framework tests user CRUD operations:

| Operation | Implementation |
|-----------|----------------|
| Setup (inventory) | `setup.sh` - Returns IAM system info |
| Teardown (cleanup) | `teardown.sh` - Cleans up test resources |
| Create User | `AwsIamProvider.create_user()` via boto3 |
| Get User | `AwsIamProvider.get_user()` via boto3 |
| Authenticate | `AwsIamProvider.authenticate()` via boto3 |
| Update User | `AwsIamProvider.update_user()` via boto3 |
| Delete User | `AwsIamProvider.delete_user()` via boto3 |

## Architecture

```text
      ┌──────────────────────────────────────────────────────────┐
      │                     Validation Tests                     │
      │  (IamCreateUserCheck, IamLoginCheck, IamDeleteUserCheck) │
      └────────────────────────────┬─────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        IamProvider Protocol                         │
│  (create_user, get_user, authenticate, update_user, delete_user)    │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        ▼                          ▼                           ▼
┌──────────────┐        ┌─────────────────────┐        ┌───────────────┐
│AwsIamProvider│        │ BaseHttpIamProvider │        │MockIamProvider│
│   (boto3)    │        │    (HTTP base)      │        │   (testing)   │
└──────────────┘        └──────────┬──────────┘        └───────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
           ┌───────────────┐           ┌───────────────────┐
           │RestIamProvider│           │YamlRestIamProvider│
           │ (subclass me) │           │   (YAML config)   │
           └───────────────┘           └───────────────────┘
```

## Usage

```bash
# Run AWS IAM validations (requires AWS credentials)
uv run isvctl test run -f isvctl/configs/providers/aws/iam.yaml

# Run with mock provider (no AWS credentials needed)
uv run isvctl test run -f isvctl/configs/providers/aws/iam.yaml -- -k "IamUserLifecycleCheck" --provider mock
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AWS_ACCESS_KEY_ID` | AWS access key | Yes |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Yes |
| `AWS_SESSION_TOKEN` | AWS session token (for SSO) | If using SSO |
| `AWS_REGION` | AWS region (default: us-west-2) | No |

## Required IAM Permissions

The AWS credentials must have the following IAM permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "iam:CreateUser",
                "iam:DeleteUser",
                "iam:GetUser",
                "iam:UpdateUser",
                "iam:TagUser",
                "iam:ListUserTags",
                "iam:CreateLoginProfile",
                "iam:DeleteLoginProfile",
                "iam:GetLoginProfile",
                "iam:ListAccessKeys",
                "iam:DeleteAccessKey",
                "iam:ListGroupsForUser",
                "iam:RemoveUserFromGroup",
                "iam:ListUserPolicies",
                "iam:DeleteUserPolicy",
                "iam:ListAttachedUserPolicies",
                "iam:DetachUserPolicy"
            ],
            "Resource": "arn:aws:iam::*:user/isv-test-*"
        }
    ]
}
```

Note: The resource restriction (`isv-test-*`) limits operations to test users only.

## For Other Providers

To implement IAM validation for a different provider, **start with the my-isv
living example**: [`stubs/my-isv/iam/`](../../../my-isv/iam/) contains
template stubs with TODO blocks and a `DEMO_MODE` gate, and
[`providers/my-isv/iam.yaml`](../../../../providers/my-isv/iam.yaml) wires
them to the canonical [`tests/iam.yaml`](../../../../tests/iam.yaml).

```bash
# See the full pipeline run in demo mode (no real IAM platform needed)
ISVCTL_DEMO_MODE=1 uv run isvctl test run -f isvctl/configs/providers/my-isv/iam.yaml

# Quickest path: copy the scaffolding, implement the stubs
cp -r isvctl/configs/stubs/my-isv/ isvctl/configs/stubs/acme/
cp -r isvctl/configs/providers/my-isv/ isvctl/configs/providers/acme/
# Implement these three Python stubs (each contains a TODO block to fill in):
#   isvctl/configs/stubs/acme/iam/create_user.py
#   isvctl/configs/stubs/acme/iam/test_credentials.py
#   isvctl/configs/stubs/acme/iam/delete_user.py
# isvctl/configs/providers/acme/iam.yaml already references isvctl/configs/stubs/acme/iam/ after the copy above,
# so the command below will pick up your implemented stubs immediately.
uv run isvctl test run -f isvctl/configs/providers/acme/iam.yaml
```

For more advanced integration, see the options below:

### Option A: YAML Configuration (zero code)

For REST APIs, define endpoints in YAML without writing Python. See `isvctl/configs/examples/acme-iam.yaml`:

```yaml
tests:
  settings:
    provider: yaml_rest
    rest_config:
      base_url: "https://api.example.com/iam"
      auth:
        type: bearer
        token: "${IAM_API_KEY}"
      endpoints:
        create_user:
          method: POST
          path: /users
          body:
            username: "{{username}}"
            role: "{{role}}"
          response:
            user_id: "$.id"
            username: "$.username"
```

### Option B: Subclass RestIamProvider (for REST APIs)

```python
from isvtest.providers.base import RestIamProvider

class OktaIamProvider(RestIamProvider):
    def __init__(self, domain: str, api_token: str):
        super().__init__(
            base_url=f"https://{domain}/api/v1",
            api_key=api_token,
            auth_header="Authorization",
            auth_prefix="SSWS",  # Okta uses SSWS prefix
        )

    def create_user(self, username, role="user", email=None, **kwargs):
        # Okta-specific user creation
        response = self.session.post(
            f"{self.base_url}/users",
            json={
                "profile": {"login": username, "email": email},
                "groupIds": [self._role_to_group(role)],
            }
        )
        ...
```

### Option C: Implement IamProvider directly (for SDKs)

```python
from isvtest.providers.iam import IamProvider, CreateUserResult

class AzureAdProvider:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.credential = ClientSecretCredential(...)
        self.client = GraphServiceClient(self.credential)

    def create_user(self, username, role="user", email=None, **kwargs):
        user = User(user_principal_name=username, ...)
        result = self.client.users.post(user)
        return CreateUserResult(success=True, user_id=result.id, ...)
```

## Cost & Cleanup

> **Note**: IAM tests create temporary IAM users and access keys which are
> free-tier resources. The teardown phase automatically deletes them, but if
> teardown fails, you should manually clean up to avoid orphaned credentials.

```bash
# Find orphaned test users
aws iam list-users --query 'Users[?starts_with(UserName, `isv-test-`)].UserName' --output table

# Detach managed policies
aws iam list-attached-user-policies --user-name isv-test-user \
  --query 'AttachedPolicies[].PolicyArn' --output text | tr '\t' '\n' | \
  xargs -I {} aws iam detach-user-policy --user-name isv-test-user --policy-arn {}

# Remove inline policies
aws iam list-user-policies --user-name isv-test-user \
  --query 'PolicyNames[]' --output text | tr '\t' '\n' | \
  xargs -I {} aws iam delete-user-policy --user-name isv-test-user --policy-name {}

# Delete access keys
aws iam list-access-keys --user-name isv-test-user \
  --query 'AccessKeyMetadata[].AccessKeyId' --output text | tr '\t' '\n' | \
  xargs -I {} aws iam delete-access-key --user-name isv-test-user --access-key-id {}

# Delete orphaned user
aws iam delete-user --user-name isv-test-user
```
