# `factory_sandbox_image_prepull` — per-host values for the inventory's `host_vars`

Keeps the Fabro factory sandbox images present in **k3s's containerd**
(namespace `k8s.io`, the store kubelet pulls into) on every k3s node whose
committed phase0 profile declares `FACTORY_NODE=true`
(ledger item `bd-ib-kogktm`, tenant `livespec-orchestrator-beads-fabro`).

**Why it exists.** The scheduler scores a node higher for already holding a
pod's image. Measured: all 11 factory pods ran on one node, because the other
factory node held `python-agent-v1.93.5` but not `python-agent-v1.114.1`, the
image the pods run. Holding the declared images on every factory node removes
that asymmetry. This is the k3s-side sibling of `sandbox_image_warm`, which
warms **Docker's** store on a docker-backed factory host and is not read by pods.

## A host needs no `host_vars` entry for this role

The role has no per-host variables. The image list is derived, never declared
here.

## Where the image list comes from, and why

The images are the `process_spec.image` of every entry in every
`fabro_server_instances[].sandbox_providers` declared in the host_vars of the
`sandbox_hosts` group (today `gmktec-xubuntu`: `kubernetes`, `kubernetes-rust`,
and the second instance's provider). That is the single source of truth: a pin
bump edits the provider, and the pre-pull follows on the next converge.

Alternatives rejected:

- **A new shared `group_vars/all` list that both the provider and the pre-pull
  read.** The providers' `process_spec.image` values are rewritten in place by
  the release fan-out's pin bump; a shared list would add a second spelling the
  fan-out does not know about, or force the provider to interpolate a variable
  into a file the fan-out edits textually.
- **`hostvars['<host>']`.** `just check-ansible-hostname-free` forbids naming a
  host in `ansible/`. The group (`sandbox_hosts`) is the hostname-free spelling.

The two plays do not need to share a host: `ci-pool.yml` runs on `ci_pool`, and
the images are read from `sandbox_hosts` host_vars, which Ansible loads for
every inventory host regardless of the play's `hosts:`.

## Operator procedure

```bash
just ansible-drift ansible/ci-pool.yml --limit <node>
just ansible-apply ansible/ci-pool.yml --limit <node> --tags factory_sandbox_image_prepull
```

Under `--check` the probe still runs, so a drift read lists what is missing;
the pull itself is skipped. Verify on a node:

```bash
sudo k3s crictl --runtime-endpoint unix:///run/k3s/containerd/containerd.sock images | grep livespec-fabro-sandbox
```

## Failure behaviour

An unreachable containerd fails the play (the version probe), and a failed
pull fails the play; neither is read as "image absent". An empty derived list
fails the play rather than converging with nothing warmed.

## Not covered

Disk tiers are untouched (`.ai/ci-node-storage-tiers.md`): the pull goes through
the existing containerd and moves no store. Pruning old tags stays with
`sandbox_image_prune`, which is server-only. A timer is not installed: the pin
changes only through a committed edit, and the converge that applies it pulls.

## Rollback

Remove the role entry from `ansible/ci-pool.yml`. The pulled images are ordinary
images the prune role reclaims on its own terms.
