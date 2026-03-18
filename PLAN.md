# Reduce YAML Config Duplication

## Why Not PR #127

PR #127's `__merge__`/`__remove__` strategic merge is **unused** across all 3 providers (AWS, Carbide, OpenShift) and 17+ configs. It strips valuable documentation from templates, uses custom nomenclature with no industry precedent, and was not live-tested. The duplication problem is real, but the solution is over-engineered.

## The Problem

Template and provider configs duplicate validation blocks (~400 lines across configs). Three pairs (control-plane, iam, network) are 100% identical. This compounds with each new provider.

## Solution

Two small changes that work together:

### 1. Dict-Based Checks

`checks:` as a list means `deep_merge` replaces it entirely. As a **dict**, individual checks can be overridden naturally:

```yaml
# Template                          # Provider override (only what differs)
ssh:                                ssh:
  step: describe_instance             checks:
  checks:                               SshOsCheck:
    SshConnectivityCheck: {}               expected_os: "rhel"
    SshOsCheck:
      expected_os: "ubuntu"
```

`deep_merge` handles this recursively. No `__merge__`/`__remove__` needed. Both list and dict formats supported for backward compatibility.

**Files to change:** `_transform_validations_for_pytest()` in `isvtest/src/isvtest/main.py`, `_extract_checks_from_config()` in `isvtest/src/isvtest/catalog.py`, type annotation in `isvctl/src/isvctl/config/schema.py`.

### 2. `import:` Directive

Provider configs declare template dependencies inline. Resolved relative to the importing file.

```yaml
# aws/iam.yaml
import:
  - ../templates/iam.yaml

commands:
  iam:
    steps: [...]

tests:
  cluster_name: "aws-iam-validation"
  # No validations: section needed -- inherited from template
```

**File to change:** ~25 lines in `isvctl/src/isvctl/config/merger.py` -- resolve `import:` before merging, strip it from output, detect circular imports.

```text
Provider YAML ---> 1. resolve import: ---> Load template
                                            |
                                       2. deep_merge
                                            |
                                       3. provider on top ---> Final config
```

## Key Decisions

- Templates stay **self-contained** (commands + validations + docs) -- unchanged
- Import paths resolved **relative to importing file**
- Both list and dict check formats supported (**backward compatible**)
- No `__merge__`/`__remove__` -- dict-based checks makes them unnecessary
