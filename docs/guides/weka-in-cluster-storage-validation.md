# WEKA Storage Provider API Validation (In-Cluster)

Guideline for running the WEKA storage-shim checks
(`StorageProviderApiCheck` and `StorageDirectoryQuotaEnforcementCheck`)
against a live Kubernetes cluster with WEKA CSI and REST API access.

The WEKA management API (typically HTTPS on port **14000**) is often
reachable only from inside the cluster network. When laptop probes time
out, run the suite from an in-cluster Pod (or via `isvctl deploy run` on
a node that can reach the API).

---

## What these checks cover

| Check | What it exercises |
| ----- | ----------------- |
| `StorageProviderApiCheck` | Loads the WEKA storage-provider manifest, imports the Python shim, checks manifest consistency, REST auth, CSI volume inventory fallback, and tenant quota for `WEKA_FILESYSTEM` |
| `StorageDirectoryQuotaEnforcementCheck` | On a real RWX PVC: directory-quota CRUD via REST, then write-under / write-over hard-limit enforcement inside a mount pod |
| `StorageUserQuotaEnforcementCheck` | On a real `weka/v2` volume: per-UID quota CRUD via REST (`probe_user`, default `65534`), then write-under / write-over enforcement as that UID |

Config entrypoint in this repo:

```text
isvctl/configs/providers/weka/config/storage-k8s.yaml
  → imports suites/storage.yaml
  → setup step emits steps.setup.storage.manifest_path
  → shim: isvctl/configs/providers/weka/scripts/storage/weka/api.py
```

Typical pytest filter:

```bash
-k "StorageProviderApi or StorageDirectoryQuotaEnforcement or StorageUserQuotaEnforcement"
```

---

## Discover your environment

```bash
kubectl get storageclass -o wide
kubectl get csidriver
kubectl get pods -A | grep -i weka   # CSI / client health hint
```

Inspect the StorageClass you will use (provisioner should be
`csi.weka.io` or equivalent):

```bash
kubectl get sc <your-weka-storageclass> -o yaml
```

Note especially:

| Field | Used as |
| ----- | ------- |
| StorageClass name | `K8S_CSI_SHARED_FS_SC` and the probe PVC `storageClassName` |
| `parameters.volumeType` | Often `weka/v2` (each PVC is its own filesystem) |
| `parameters.filesystemName` or `filesystemGroupName` | Informs which filesystem / group CSI uses |
| CSI secret refs | Driver credentials (may differ from the shim account) |

Choose a filesystem that exists for **tenant quota** (`WEKA_FILESYSTEM`) —
commonly a long-lived shared FS, not necessarily the per-PVC `weka/v2`
filesystem created for the probe.

List filesystems via the WEKA REST API from a host that can reach it
(authenticated `GET /api/v2/fileSystems`) and pick one with a positive
capacity budget.

---

## Prerequisites

### 1. WEKA credentials for the shim

| Env | Meaning |
| --- | ------- |
| `WEKA_ENDPOINTS` or `WEKA_ENDPOINT` | Comma-separated or single `host:port` list |
| `WEKA_USERNAME` / `WEKA_PASSWORD` | Account with filesystem + directory-quota permissions |
| `WEKA_ORGANIZATION` | Optional; default `Root`. Shim login body uses field `org` |
| `WEKA_FILESYSTEM` | Filesystem name used for tenant quota |
| `WEKA_SCHEME` | Optional; default `https` |
| `WEKA_INSECURE_SKIP_VERIFY` | Optional `1` / `true` for lab TLS only |
| `WEKA_STORAGE_PATH` | Optional path prefix for scoped tenant-quota aggregation |

Prefer a **tenant-admin** (or equivalent) account for the shim. A
lower-privilege CSI-only account may authenticate for inventory checks
but fail directory-quota CRUD.

Common Secret key → env mapping:

| Secret key | Env var |
| ---------- | ------- |
| `endpoints` | `WEKA_ENDPOINTS` |
| `username` | `WEKA_USERNAME` |
| `password` | `WEKA_PASSWORD` |
| `organization` | `WEKA_ORGANIZATION` |
| `scheme` | `WEKA_SCHEME` |

### 2. Reusable quota-probe PVC + Pod (recommended)

```bash
kubectl create namespace isvtest-quota --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: quota-probe
  namespace: isvtest-quota
spec:
  accessModes: [ReadWriteMany]
  storageClassName: <your-weka-storageclass>
  resources:
    requests:
      storage: 5Gi
---
apiVersion: v1
kind: Pod
metadata:
  name: quota-probe
  namespace: isvtest-quota
spec:
  securityContext:
    runAsUser: 65534
    runAsGroup: 65534
    fsGroup: 65534
  containers:
    - name: probe
      image: busybox:1.36
      command: ["sh", "-c", "while true; do sleep 3600; done"]
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: quota-probe
EOF

kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/quota-probe -n isvtest-quota --timeout=180s
kubectl wait --for=condition=Ready pod/quota-probe -n isvtest-quota --timeout=180s
```

Match the probe Pod UID/GID (65534) so writes under `/data` are not
squashed unexpectedly.

### 3. RBAC for the runner ServiceAccount

Replace `<runner-namespace>` / `<runner-sa>` with the ServiceAccount your
runner Pod uses:

```bash
kubectl apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: isvtest-quota-probe
  namespace: isvtest-quota
rules:
  - apiGroups: [""]
    resources: ["pods", "persistentvolumeclaims"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create", "get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: isvtest-quota-probe
  namespace: isvtest-quota
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: isvtest-quota-probe
subjects:
  - kind: ServiceAccount
    name: <runner-sa>
    namespace: <runner-namespace>
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: isvtest-weka-pv-reader
rules:
  - apiGroups: [""]
    resources: ["persistentvolumes"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: isvtest-weka-pv-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: isvtest-weka-pv-reader
subjects:
  - kind: ServiceAccount
    name: <runner-sa>
    namespace: <runner-namespace>
EOF
```

Without PV `get`, the quota check typically fails with Forbidden when
reading the PVC’s PersistentVolume `csi.volumeHandle` (often shaped like
`weka/v2/<filesystem-name>`).

---

## Runner configuration

### Required environment

| Env | How to set |
| --- | ---------- |
| `WEKA_ENDPOINTS` / `WEKA_USERNAME` / `WEKA_PASSWORD` | From your management-API credentials |
| `WEKA_ORGANIZATION` | Match your WEKA org (default `Root`) |
| `WEKA_FILESYSTEM` | Existing filesystem used for tenant quota |
| `K8S_CSI_SHARED_FS_SC` | Your WEKA RWX StorageClass name |
| `ISVTEST_INCLUDE_UNRELEASED` | `1` while these checks are unreleased |
| `WEKA_INSECURE_SKIP_VERIFY` | Optional, lab TLS only |

Leave `K8S_CSI_NFS_SC` unset when the class is native wekafs (not NFS);
`K8sNfsMountOptionsCheck` will skip cleanly.

### Config overlays

1. **Capability** — must be exactly `kubernetes` (not `k8s`):

```yaml
commands:
  kubernetes:
    phases: ["setup", "test", "teardown"]
tests:
  capability: kubernetes
```

2. **Quota reuse** — under `storage_provider_api` (not `k8s_storage`):

```yaml
tests:
  validations:
    storage_provider_api:
      checks:
        StorageDirectoryQuotaEnforcementCheck:
          pvc_namespace: isvtest-quota
          pvc_name: quota-probe
          pod_name: quota-probe
        StorageUserQuotaEnforcementCheck:
          pvc_namespace: isvtest-quota
          pvc_name: quota-probe
          pod_name: quota-probe
          probe_user: "65534"
```

### Command

```bash
# Optional isolated preflight
uv run python .cursor/skills/storage-api-stub-authoring/scripts/probe_shim.py \
  --manifest isvctl/configs/providers/weka/config/storage-provider-manifest.yaml

ISVTEST_INCLUDE_UNRELEASED=1 \
  uv run isvctl test run \
    -f isvctl/configs/providers/weka/config/storage-k8s.yaml \
    -f /path/to/k8s-capability.yaml \
    -f /path/to/quota-reuse.yaml \
            -- -v -s -k "StorageProviderApi or StorageDirectoryQuotaEnforcement or StorageUserQuotaEnforcement"
```

`probe_shim` expectations: `health_check` OK, `list_volumes` ≥ 1 (or
create a PVC first), `get_tenant_quota` with `hard_limit_bytes > 0`.

---

## Expected results (success pattern)

| Check / subtest | Expected |
| --------------- | -------- |
| `StorageProviderApiCheck` | PASSED |
| `manifest-consistency[weka-shared-fs]` | PASSED |
| `api-authentication[weka-shared-fs]` | PASSED |
| `volume-provisioning[weka-shared-fs]` | SKIPPED (OK) when CSI owns lifecycle and `list_volumes` sees ≥1 volume |
| `tenant-quota[weka-shared-fs]` | PASSED |
| `StorageDirectoryQuotaEnforcementCheck` | PASSED |
| `directory-quota-crud[weka-shared-fs]` | PASSED |
| `directory-quota-enforcement[weka-shared-fs]` | PASSED |
| `StorageUserQuotaEnforcementCheck` | PASSED |
| `user-quota-crud[weka-shared-fs]` | PASSED |
| `user-quota-enforcement[weka-shared-fs]` | PASSED |

JUnit is written under `_output/junit-validation.xml` for the orchestration run.

---

## Common pitfalls

1. **WEKA API may be in-cluster only** — if laptop TCP to the management
   port times out, run inside the cluster.
2. **Login body field is `org`**, not `organization`. Sending
   `organization` can yield HTTP 400 `unknown_params`. The shim sets
   `org` from `WEKA_ORGANIZATION`.
3. **Use an account with directory-quota rights** for the shim; a
   CSI-only user may be insufficient.
4. **`WEKA_FILESYSTEM` must name a real filesystem** with a positive
   capacity budget for tenant-quota.
5. **`tests.capability` must be `kubernetes`**, not `k8s`.
6. **Quota-reuse override group is `storage_provider_api`**. Some older
   examples place it under `k8s_storage` — that does not configure the
   manifest-backed check in `suites/storage.yaml`.
7. **Runner SA needs PersistentVolume `get`** to resolve
   `csi.volumeHandle` for a reused PVC.
8. Trim accidental whitespace when exporting credentials from the shell
   before mapping them to shim env vars.

---

## Cleanup

```bash
kubectl delete pod <runner-pod> -n <runner-namespace> --ignore-not-found
# Optional — keep PVC/pod for faster re-runs:
kubectl delete namespace isvtest-quota
kubectl delete clusterrolebinding isvtest-weka-pv-reader
kubectl delete clusterrole isvtest-weka-pv-reader
```

---

## See also

- Provider README: `isvctl/configs/providers/weka/scripts/storage/README.md`
- Shim: `isvctl/configs/providers/weka/scripts/storage/weka/api.py`
- Manifest: `isvctl/configs/providers/weka/config/storage-provider-manifest.yaml`
- K8s config: `isvctl/configs/providers/weka/config/storage-k8s.yaml`
- VAST counterpart: [vast-in-cluster-storage-validation.md](vast-in-cluster-storage-validation.md)
