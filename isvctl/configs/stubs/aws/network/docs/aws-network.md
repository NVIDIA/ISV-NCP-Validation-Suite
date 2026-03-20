# Network Validation Guide (AWS)

This guide provides a complete walkthrough for validating AWS VPC networking capabilities using the ISV validation framework. These tests verify software-defined networking overlays and fabric behavior for compute-on-demand requirements.

## Overview

The network validation suite includes 6 comprehensive test suites:

| Test Suite | Duration | Description |
|------------|----------|-------------|
| **VPC CRUD** | ~30s | Create, read, update, delete VPC lifecycle |
| **Subnet Config** | ~30s | Multi-AZ subnet distribution and route tables |
| **VPC Isolation** | ~30s | Security boundaries between separate VPCs |
| **Security Blocking** | ~30s | SG/NACL blocking rules (negative tests) |
| **Connectivity** | ~3 min | Instance network assignment via SSM |
| **Traffic Validation** | ~5-7 min | Real ping tests - allowed/blocked traffic |

**Total runtime**: ~10-12 minutes for all tests

**Key Features:**

- All tests are **SELF-CONTAINED** - they create their own VPCs and clean up after
- **No pre-existing infrastructure required** - just AWS credentials
- **Platform-agnostic validations** - scripts output JSON, validations check results
- Includes **negative test cases** to verify security controls work correctly
- **Real traffic tests** using AWS SSM to run actual ping commands

## Architecture

### Step-Based Execution Model

```text
┌─────────────────────────────────────────────────────────────────┐
│                    AWS Network Validation Suite                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Scripts (boto3)              Validations (JSON check)          │
│  ┌──────────────────┐         ┌─────────────────────────┐       │
│  │ vpc_crud_test.py │ ──────▶ │ VpcCrudCheck            │       │
│  │ subnet_test.py   │ ──────▶ │ SubnetConfigCheck       │       │
│  │ isolation_test.py│ ──────▶ │ VpcIsolationCheck       │       │
│  │ security_test.py │ ──────▶ │ SecurityBlockingCheck   │       │
│  │ test_connectivity│ ──────▶ │ NetworkConnectivityCheck│       │
│  │ traffic_test.py  │ ──────▶ │ TrafficFlowCheck        │       │
│  └──────────────────┘         └─────────────────────────┘       │
│                                                                 │
│  Platform-specific            Platform-agnostic                 │
│  (AWS boto3 SDK)              (checks JSON output)              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Traffic Validation Test Architecture

The most comprehensive test actually sends real network traffic:

```text
┌─────────────────────────────────────────────────────────────────┐
│                          Test VPC                               │
│                                                                 │
│  ┌─────────────┐   ping (ok)     ┌────────────────────────────┐ │
│  │   Source    │ ───────────────▶│ Target (SG allows ICMP)    │ │
│  │ (SSM agent) │                 └────────────────────────────┘ │
│  │             │  ping (blocked) ┌────────────────────────────┐ │
│  │             │ ───────────────▶│ Target (SG blocks ICMP)    │ │
│  │             │                 └────────────────────────────┘ │
│  │             │                                                │
│  │             │ ──── ping 8.8.8.8 ────▶ Internet (ICMP) (ok)   │
│  │             │ ── curl amazonaws ────▶ Internet (HTTPS) (ok)  │
│  └─────────────┘                                                │
│         │                                                       │
│         ▼                                                       │
│       [IGW]                                                     │
└─────────┼───────────────────────────────────────────────────────┘
          │
          ▼
      Internet
```

## Scripts

All scripts are located in `isvctl/configs/stubs/aws/network/`:

| Script | Purpose | Output Schema |
|--------|---------|---------------|
| `vpc_crud_test.py` | VPC create/read/update/delete | `vpc_crud` |
| `subnet_test.py` | Multi-AZ subnet configuration | `subnet_config` |
| `isolation_test.py` | VPC isolation verification | `vpc_isolation` |
| `security_test.py` | SG/NACL blocking rules | `security_blocking` |
| `test_connectivity.py` | Instance connectivity via SSM | `connectivity_result` |
| `traffic_test.py` | Real ping traffic tests | `traffic_flow` |
| `create_vpc.py` | Create shared VPC for tests | `network` |
| `teardown.py` | Clean up VPC resources | `teardown` |

## Quick Start

```bash
# Run all network tests
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml

# Run specific test suites
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml -- -k "vpc_crud"
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml -- -k "isolation"
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml -- -k "security"
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml -- -k "traffic"

# Run with verbose output
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml -v
```

## Test Cases

### 1. VPC CRUD Check

**Script**: `vpc_crud_test.py`
**Validation**: `VpcCrudCheck`

Tests the complete VPC lifecycle:

- Create VPC with specified CIDR
- Wait for VPC to become "available"
- Update VPC tags
- Enable DNS hostnames and support
- Delete VPC and verify removal

**Output example**:

```json
{
  "success": true,
  "platform": "network",
  "tests": {
    "create_vpc": {"passed": true, "vpc_id": "vpc-xxx"},
    "read_vpc": {"passed": true, "state": "available"},
    "update_tags": {"passed": true},
    "update_dns": {"passed": true},
    "delete_vpc": {"passed": true}
  }
}
```

### 2. Subnet Configuration Check

**Script**: `subnet_test.py`
**Validation**: `SubnetConfigCheck`

Tests multi-AZ subnet distribution:

- Create VPC with specified CIDR
- Create multiple subnets across availability zones
- Verify AZ distribution
- Check subnet availability state
- Verify route table exists

**Configuration options**:

```yaml
validations:
  - SubnetConfigCheck:
      min_subnets: 4
      require_multi_az: true
```

### 3. VPC Isolation Check

**Script**: `isolation_test.py`
**Validation**: `VpcIsolationCheck`

Verifies security boundaries between VPCs:

- Create two VPCs with non-overlapping CIDRs
- Verify no VPC peering connections exist
- Check route tables don't reference other VPC
- Validate default security groups block cross-VPC traffic

### 4. Security Blocking Check (Negative Tests)

**Script**: `security_test.py`
**Validation**: `SecurityBlockingCheck`

Tests that security rules correctly **block** traffic:

- **Empty SG default deny**: Verifies no inbound rules = default deny
- **SG specific allow**: Creates SG allowing only SSH from specific CIDR
- **SG denies ICMP**: Verifies ICMP is blocked when not explicitly allowed
- **NACL explicit deny**: Creates NACL with explicit deny rule
- **Restricted egress**: Creates SG with HTTPS-only outbound

### 5. Connectivity Check

**Script**: `test_connectivity.py`
**Validation**: `NetworkConnectivityCheck`

Tests instance network connectivity:

- Creates IAM role for SSM access
- Launches EC2 instances in VPC subnets
- Waits for SSM agent to be online
- Tests ping between instances
- Tests internet connectivity

### 6. Traffic Validation Check

**Script**: `traffic_test.py`
**Validation**: `TrafficFlowCheck`

The most comprehensive test - sends real network traffic:

- Creates VPC with Internet Gateway
- Creates IAM role for SSM
- Creates two security groups (allow ICMP / deny ICMP)
- Launches 3 instances (source + 2 targets)
- Tests ping to allowed target (should succeed)
- Tests ping to blocked target (should fail)
- Tests internet ICMP (ping 8.8.8.8)
- Tests internet HTTPS (curl checkip.amazonaws.com)

## Prerequisites

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
export AWS_REGION=us-west-2
```

### Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:DescribeVpcs", "ec2:ModifyVpcAttribute",
        "ec2:CreateSubnet", "ec2:DeleteSubnet", "ec2:DescribeSubnets",
        "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup", "ec2:DescribeSecurityGroups",
        "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:CreateNetworkAcl", "ec2:DeleteNetworkAcl", "ec2:DescribeNetworkAcls",
        "ec2:CreateNetworkAclEntry",
        "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway", "ec2:AttachInternetGateway",
        "ec2:DetachInternetGateway", "ec2:DescribeInternetGateways",
        "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:AssociateRouteTable",
        "ec2:DisassociateRouteTable", "ec2:CreateRoute", "ec2:DescribeRouteTables",
        "ec2:RunInstances", "ec2:TerminateInstances", "ec2:DescribeInstances",
        "ec2:ModifySubnetAttribute",
        "ec2:CreateTags", "ec2:DescribeTags",
        "ec2:DescribeImages", "ec2:DescribeAvailabilityZones",
        "ec2:DescribeVpcPeeringConnections", "ec2:DescribeVpcAttribute"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole", "iam:DeleteRole", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
        "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile",
        "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile",
        "iam:PassRole"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:SendCommand", "ssm:GetCommandInvocation", "ssm:DescribeInstanceInformation"
      ],
      "Resource": "*"
    }
  ]
}
```

## Configuration

### network.yaml Structure

```yaml
version: "1.0"

commands:
  network:
    steps:
      # Test 1: VPC CRUD
      - name: vpc_crud
        phase: test
        command: "python3 ./stubs/aws/network/vpc_crud_test.py"
        args:
          - "--region"
          - "{{region}}"
          - "--cidr"
          - "10.99.0.0/16"
        timeout: 120
        output_schema: vpc_crud
        validations:
          - VpcCrudCheck: {}

      # ... more test steps ...

      # Setup: Create shared VPC
      - name: create_network
        phase: setup
        command: "python3 ./stubs/aws/network/create_vpc.py"
        validations:
          - NetworkProvisionedCheck: {}

      # Teardown
      - name: teardown
        phase: teardown
        command: "python3 ./stubs/aws/network/teardown.py"
        validations:
          - StepSuccessCheck: {}

tests:
  platform: network
  settings:
    region: "us-west-2"
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region for tests | `us-west-2` |
| `AWS_ACCESS_KEY_ID` | AWS access key | From AWS config |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | From AWS config |
| `AWS_SESSION_TOKEN` | STS session token | None |
| `AWS_NETWORK_SKIP_TEARDOWN` | Skip VPC teardown | `false` |

## Example Output

```shell
============================================================
ORCHESTRATION RESULTS
============================================================
[PASS] SETUP   : create_network: passed
  [create_network] NetworkProvisionedCheck: PASSED - Network vpc-xxx provisioned: CIDR=10.0.0.0/16, subnets=2
[PASS] TEST    : vpc_crud: passed; subnet_config: passed; vpc_isolation: passed; security_blocking: passed; connectivity_test: passed; traffic_validation: passed
  [vpc_crud] VpcCrudCheck: PASSED - All 5 CRUD tests passed
  [subnet_config] SubnetConfigCheck: PASSED - 4 subnets across 2 AZs
  [vpc_isolation] VpcIsolationCheck: PASSED - VPCs vpc-a and vpc-b are properly isolated
  [security_blocking] SecurityBlockingCheck: PASSED - All 5 security blocking tests passed
  [connectivity_test] NetworkConnectivityCheck: PASSED - 2 instances with network connectivity
  [traffic_validation] TrafficFlowCheck: PASSED - All 4 traffic tests passed (latency: 0.5ms)
[PASS] TEARDOWN: teardown: passed
  [teardown] StepSuccessCheck: PASSED - Teardown successful
------------------------------------------------------------
[PASS] All phases completed successfully
```

## Troubleshooting

### "VPC limit exceeded"

AWS accounts have default VPC limits (5 per region). Delete unused VPCs or request a limit increase.

```bash
aws ec2 describe-vpcs --query 'length(Vpcs)'
```

### "UnauthorizedOperation"

Missing IAM permissions. See [Required IAM Permissions](#required-iam-permissions).

### "SSM not ready" or "InvalidInstanceId"

The SSM agent takes time to register. The tests include retry logic, but if it still fails:

- Ensure instances have public IP (for SSM endpoint connectivity)
- Verify IAM role has `AmazonSSMManagedInstanceCore` policy
- Check VPC has internet gateway and route to 0.0.0.0/0

### Tests timing out

Increase timeout in config:

```yaml
- name: traffic_validation
  timeout: 1200  # 20 minutes
```

## Cost & Cleanup

> **Warning**: These tests create AWS resources (VPCs, subnets, security groups,
> internet gateways, EC2 instances) that incur costs. Resources are
> automatically cleaned up during the teardown phase, but if teardown fails
> or is skipped, you must manually delete them to avoid ongoing charges.

```bash
# Find VPCs tagged by isvtest
aws ec2 describe-vpcs --filters "Name=tag:CreatedBy,Values=isvtest" \
  --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0],State]' --output table

# Delete orphaned VPCs (must remove dependent resources first — see below)
VPC_ID="vpc-xxx"
```

`delete-vpc` fails with `DependencyViolation` if any resources still reference
the VPC. Remove dependencies in this order before deleting:

1. Terminate EC2 instances, load balancers, RDS/EFS mount targets (`terminate-instances`)
2. Delete NAT Gateways and VPC Endpoints (`delete-nat-gateway`, `delete-vpc-endpoints`)
3. Detach & delete remaining ENIs and release Elastic IPs (`delete-network-interface`)
4. Detach & delete Internet/VPN Gateways (`detach-internet-gateway`, `delete-internet-gateway`)
5. Delete peering/VPN connections (`delete-vpc-peering-connection`)
6. Disassociate & delete custom route tables (`disassociate-route-table`, `delete-route-table`)
7. Delete subnets (`delete-subnet`)
8. Delete non-default security groups and NACLs (`delete-security-group`, `delete-network-acl`)

> **Key check:** there must be **zero ENIs** remaining before `delete-vpc` succeeds.
> Verify with: `aws ec2 describe-network-interfaces --filters Name=vpc-id,Values=$VPC_ID`

```bash
# Quick manual cleanup example
VPC_ID="vpc-xxx"
aws ec2 terminate-instances --instance-ids $(aws ec2 describe-instances \
  --filters "Name=vpc-id,Values=$VPC_ID" --query 'Reservations[*].Instances[*].InstanceId' --output text)
aws ec2 detach-internet-gateway --internet-gateway-id igw-xxx --vpc-id $VPC_ID
aws ec2 delete-internet-gateway --internet-gateway-id igw-xxx
aws ec2 delete-subnet --subnet-id subnet-xxx
aws ec2 delete-security-group --group-id sg-xxx
aws ec2 delete-vpc --vpc-id $VPC_ID
```

For automated cleanup, use the suite's teardown phase which handles the full
dependency sequence via [`teardown_vpc.py`](../teardown_vpc.py):

```bash
uv run isvctl test run -f isvctl/configs/providers/aws/network.yaml --phase teardown
```

## Related Documentation

- [Configuration Guide](../../../../../docs/guides/configuration.md)
- [isvctl Documentation](../../../../../docs/packages/isvctl.md)
- [AWS EKS Validation Guide](../../eks/docs/aws-eks.md)
