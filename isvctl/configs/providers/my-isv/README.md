# my-isv provider configs

YAML wiring that connects the provider-agnostic [test suites](../../tests/) to
the [my-isv scaffold stubs](../../stubs/my-isv/). Each config `import:`s a
test suite and overrides the commands with paths into `stubs/my-isv/`.

The stubs ship with a demo-mode fallback, so these configs run end-to-end
out of the box under `ISVCTL_DEMO_MODE=1` - that's what `make demo-test`
exercises.

## Configs

| Config | Domain | Stubs |
|--------|--------|-------|
| [`iam.yaml`](iam.yaml) | User lifecycle (create -> verify -> delete) | [`stubs/my-isv/iam/`](../../stubs/my-isv/iam/) |
| [`control-plane.yaml`](control-plane.yaml) | API health, access keys, tenant lifecycle | [`stubs/my-isv/control-plane/`](../../stubs/my-isv/control-plane/) |
| [`vm.yaml`](vm.yaml) | GPU VM lifecycle (launch -> stop/start -> reboot -> teardown) | [`stubs/my-isv/vm/`](../../stubs/my-isv/vm/) |
| [`bare_metal.yaml`](bare_metal.yaml) | BMaaS lifecycle (launch -> topology -> serial -> power-cycle -> teardown) | [`stubs/my-isv/bare_metal/`](../../stubs/my-isv/bare_metal/) |
| [`network.yaml`](network.yaml) | VPC CRUD, subnets, isolation, SG, connectivity, traffic, DDI | [`stubs/my-isv/network/`](../../stubs/my-isv/network/) |
| [`image-registry.yaml`](image-registry.yaml) | Image upload, CRUD, VM launch, install config, BMaaS install | [`stubs/my-isv/image-registry/`](../../stubs/my-isv/image-registry/) |

## Coverage note

These configs exclude validations that require SSH into a real host
(`exclude.markers: [ssh]`) and skip steps that need real cloud APIs
(e.g. `deploy_nim`), because dummy stubs can't spin up real hosts.
Each YAML's header comment documents exactly which checks are excluded
and why - remove those exclusions as your real stubs come online.

## See also

- [`stubs/my-isv/`](../../stubs/my-isv/) - the scaffold these configs invoke (start here)
- [`tests/README.md`](../../tests/README.md) - per-step JSON-field breakdown
- [AWS provider configs](../aws/) - a working reference implementation using the same pattern
