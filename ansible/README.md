# `ansible/` — host provisioning for the legacy Ubuntu fleet

This tree provisions the four pre-Talos Ubuntu machines — `vps`,
`poweredge-xubuntu`, `gmktec-xubuntu`, `hp-xubuntu` — replacing the
home-grown installer/converge shell that grew across three repositories.

livespec work-item `livespec-sab5gn.4`; rationale, the estate inventory and
the phase plan are in `thewoolleyman/livespec` at
`plan/k3s-on-gmktec-for-vps-usage/research/004-ansible-migration-direction-2026-09-09.md`
and `.../005-ansible-migration-estate-inventory-2026-09-09.md`.

## The two commands

```bash
just ansible-drift ansible/gates-kubeconfig.yml   # reports; changes nothing
just ansible-apply ansible/gates-kubeconfig.yml   # converges
```

`ansible-drift` is `--check --diff`. It is the drift report, and it replaces
the bespoke `ci-runner/k3s/phase2/reconstruct/verify-installed-tree.sh`.
Run it before every apply. `just check` runs `check-ansible-lint` over this
tree, at ansible-lint's `production` profile.

## The two rules this tree lives under

**A Talos node must never appear in the inventory.** The long-term fleet is
Talos, Omni and Flux, and that fleet's machines have no shell for Ansible to
reach. An entry here for a machine Omni owns would give it two declared
owners. Read the header of `inventory/legacy.yml` before adding a host.
These four machines are a sunset substrate: when a machine's workload moves
to the Talos fleet, delete its entry rather than porting anything.

**Kubernetes desired state does not migrate into Ansible.** Kueue queues,
ARC scale sets, gate Jobs, RBAC, the provisioner, warm-cache, sccache and
crates-proxy stay as manifests and kustomizations under `../ci-runner/`,
shaped so Flux could reconcile them unchanged. A playbook may `kubectl
apply -k` them; it may not encode their ordering in tasks. What migrates
here is host glue: files, systemd units, sysctls, pinned downloads, and
host-side files rendered from cluster state.

## Playbooks run from committed source

Never from an installed copy on the target. A host once ran a converge
script from before the gates queue existed, exited `Result=success`, and the
queue never appeared — the defect that `verify-installed-tree.sh` was built
to detect and that running from source removes instead.

The control node is `vps`, which manages itself over a local connection and
reaches the other three over the tailnet as `cwoolley`. All four already
carry a modern Python interpreter and passwordless sudo, so no bootstrap
step is needed.

## Why `uvx` rather than a dependency group

Ansible is a tool this repository invokes, never a library it imports, and
`ansible-core` 2.21 requires Python 3.12 while this repository's floor is
3.10.16. Raising that floor is a fleet-wide decision about the shared
enforcement suite and has nothing to do with provisioning hosts. Both
versions are pinned exactly in the justfile recipes, which remain the single
source of truth for how the tool is invoked.

## Roles

| Role | Hosts | Replaces |
|---|---|---|
| `gates_kubeconfig` | `dev_hosts` | `vps-info` `services/gates-kubeconfig/install.sh` |
