# VAST Storage Provider API Validation (In-Cluster)

Guideline for running the VAST storage-shim checks
(`StorageProviderApiCheck` and `StorageDirectoryQuotaEnforcementCheck`)
against a live Kubernetes cluster with VAST CSI and VMS API access.

The VAST management API is often reachable only from inside the cluster
network. When laptop probes to VMS time out, run the suite from an
in-cluster Pod (or via `isvctl deploy run` on a node that can reach VMS).

---

## What these checks cover

| Check | What it exercises |
| ----- | ----------------- |
| `StorageProviderApiCheck` | Loads the VAST storage-provider manifest, imports the Python shim, checks manifest consistency, VMS auth, CSI volume inventory fallback, and tenant quota aggregation |
| `StorageDirectoryQuotaEnforcementCheck` | On a real RWX PVC: directory-quota CRUD via VMS, then write-under / write-over hard-limit enforcement inside a mount pod |

Config entrypoint in this repo:

```text
isvctl/configs/providers/vast/config/storage-k8s.yaml
  → imports suites/storage.yaml
  → setup step emits steps.setup.storage.manifest_path
  → shim: isvctl/configs/providers/vast/scripts/storage/vast/api.py
```

Typical pytest filter:

```bash
-k "StorageProviderApi or StorageDirectoryQuotaEnforcement"
```

---

## Discover your environment

Fill these from *your* cluster before configuring the runner:

```bash
kubectl get storageclass -o wide
kubectl get csidriver
kubectl get pods -A | grep -i vast   # CSI health hint
```

Inspect the StorageClass you will use (provisioner should be
`csi.vastdata.com` or equivalent):

```bash
kubectl get sc <your-vast-storageclass> -o yaml
```

Note especially:

| Field | Used as |
| ----- | ------- |
| StorageClass name | `K8S_CSI_SHARED_FS_SC` / `K8S_CSI_NFS_SC` and the probe PVC `storageClassName` |
| `parameters.root_export` | `VAST_STORAGE_PATH` (must match exactly) |
| Secret referenced by CSI params | Source of VMS endpoint + API token for the shim |

Do **not** copy sample paths or class names from docs unless they match
what `kubectl get sc` shows on your cluster.

---

## Prerequisites

### 1. VMS credentials

Provide the shim with:

| Env | Meaning |
| --- | ------- |
| `VAST_ENDPOINT` | VMS hostname or URL (`https://…` preferred) |
| `VAST_TOKEN` | API token (`Authorization: Api-Token …`), **or** `VAST_USERNAME` + `VAST_PASSWORD` |
| `VAST_STORAGE_PATH` | Same as StorageClass `root_export` |
| `VAST_INSECURE_SKIP_VERIFY` | Optional `1` / `true` for lab TLS only |
| `VAST_TENANT` | Optional; empty = VMS default tenant |

These are commonly stored in a Kubernetes Secret and projected into the
runner Pod. The env var names above are what the shim reads — map secret
keys accordingly (do not leave values only under an alternate name such
as `VAST_ENDPOINT_SECRET` unless the entrypoint exports them).

### 2. Reusable quota-probe PVC + Pod (recommended)

Avoids needing the runner ServiceAccount to create namespaces or PVCs on
every run.

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
  storageClassName: <your-vast-storageclass>
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

kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/quota-probe -n isvtest-quota --timeout=120s
kubectl wait --for=condition=Ready pod/quota-probe -n isvtest-quota --timeout=180s
```

Match the probe Pod UID/GID (65534) so writes under `/data` are not
squashed unexpectedly.

### 3. RBAC for the runner ServiceAccount

The in-cluster runner needs at least:

- In `isvtest-quota`: get/list/watch Pods and PVCs, and `pods/exec`
- Cluster-scoped: `get`/`list` on PersistentVolumes (to read
  `csi.volumeHandle` when resolving the reused PVC)

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
  name: isvtest-vast-pv-reader
rules:
  - apiGroups: [""]
    resources: ["persistentvolumes"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: isvtest-vast-pv-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: isvtest-vast-pv-reader
subjects:
  - kind: ServiceAccount
    name: <runner-sa>
    namespace: <runner-namespace>
EOF
```

Without PV `get`, the quota check typically fails with a Forbidden error
when reading the PVC’s PersistentVolume `csi.volumeHandle`.

---

## Runner configuration

### Required environment

| Env | How to set |
| --- | ---------- |
| `VAST_ENDPOINT` / `VAST_TOKEN` (or user/pass) | From your VMS credentials Secret |
| `VAST_STORAGE_PATH` | Exact StorageClass `root_export` |
| `K8S_CSI_SHARED_FS_SC` | Your VAST RWX StorageClass name |
| `K8S_CSI_NFS_SC` | Same class when it also fills the NFS role |
| `ISVTEST_INCLUDE_UNRELEASED` | `1` while these checks are unreleased |
| `VAST_INSECURE_SKIP_VERIFY` | Optional, lab TLS only |

### Config overlays

1. **Capability** — must be exactly `kubernetes` (not `k8s`). Allowed values:
   `bare_metal`, `kubernetes`, `slurm`, `vm`.

```yaml
commands:
  kubernetes:
    phases: ["setup", "test", "teardown"]
tests:
  capability: kubernetes
```

2. **Quota reuse** — under `storage_provider_api` (the suite group that
   wires the manifest-backed check), **not** `k8s_storage`:

```yaml
tests:
  validations:
    storage_provider_api:
      checks:
        StorageDirectoryQuotaEnforcementCheck:
          pvc_namespace: isvtest-quota
          pvc_name: quota-probe
          pod_name: quota-probe
```

### Command

From a host or Pod that can reach VMS and has `kubectl` + this repo:

```bash
# Optional isolated preflight
uv run python .cursor/skills/storage-api-stub-authoring/scripts/probe_shim.py \
  --manifest isvctl/configs/providers/vast/config/storage-provider-manifest.yaml

ISVTEST_INCLUDE_UNRELEASED=1 \
  uv run isvctl test run \
    -f isvctl/configs/providers/vast/config/storage-k8s.yaml \
    -f /path/to/k8s-capability.yaml \
    -f /path/to/quota-reuse.yaml \
    -- -v -s -k "StorageProviderApi or StorageDirectoryQuotaEnforcement"
```

`probe_shim` expectations: `health_check` OK, `list_volumes` ≥ 1 (or create a
PVC first), `get_tenant_quota` with `hard_limit_bytes > 0`.

---

## Expected results (success pattern)

| Check / subtest | Expected |
| --------------- | -------- |
| `StorageProviderApiCheck` | PASSED |
| `manifest-consistency[vast-nfs]` | PASSED |
| `api-authentication[vast-nfs]` | PASSED |
| `volume-provisioning[vast-nfs]` | SKIPPED (OK) when CSI owns lifecycle and `list_volumes` sees ≥1 volume |
| `tenant-quota[vast-nfs]` | PASSED |
| `StorageDirectoryQuotaEnforcementCheck` | PASSED |
| `directory-quota-crud[vast-nfs]` | PASSED |
| `directory-quota-enforcement[vast-nfs]` | PASSED (under-limit write OK; over-limit eventually fails with a quota / ENOSPC-style error) |

JUnit is written under `_output/junit-validation.xml` for the orchestration run.

---

## Common pitfalls

1. **`VAST_STORAGE_PATH` must equal StorageClass `root_export`.**
   A wrong path still allows auth, but `tenant-quota` fails with
   `hard_limit_bytes=0` and `list_volumes` may see zero children.
2. **StorageClass name** must be the live class on *your* cluster — do not
   assume README examples.
3. **`tests.capability` must be `kubernetes`**, not `k8s`.
4. **Quota-reuse override group is `storage_provider_api`**, matching
   `suites/storage.yaml`. Putting it under `k8s_storage` does not configure
   the check that loads the VAST manifest.
5. **VMS may be in-cluster only** — if laptop `curl` times out, run inside
   the cluster.
6. **Runner SA needs PersistentVolume `get`** to resolve `csi.volumeHandle`
   for a reused PVC.
7. Export **`VAST_ENDPOINT`** (shim name) before `isvctl`; alternate secret
   key names are not read automatically.

---

## Cleanup

```bash
kubectl delete pod <runner-pod> -n <runner-namespace> --ignore-not-found
# Optional — keep PVC/pod for faster re-runs:
kubectl delete namespace isvtest-quota
kubectl delete clusterrolebinding isvtest-vast-pv-reader
kubectl delete clusterrole isvtest-vast-pv-reader
```

---

## See also

- Provider README: `isvctl/configs/providers/vast/scripts/storage/README.md`
- Shim: `isvctl/configs/providers/vast/scripts/storage/vast/api.py`
- Manifest: `isvctl/configs/providers/vast/config/storage-provider-manifest.yaml`
- K8s config: `isvctl/configs/providers/vast/config/storage-k8s.yaml`
- WEKA counterpart: [weka-in-cluster-storage-validation.md](weka-in-cluster-storage-validation.md)
