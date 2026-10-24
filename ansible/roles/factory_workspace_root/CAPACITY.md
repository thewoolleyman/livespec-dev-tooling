# CAPACITY — sizing `/srv/factory-workspaces`

The number in `defaults/main.yml` that needs a derivation is not a number at
all: the role creates a plain directory on a filesystem it does not own, so
"sizing" here means establishing that the filesystem each pool node serves the
path from can hold what the `factory` namespace is allowed to put in it, and
recording what binds first when it cannot. This file sits beside the role for
the reason `../../../ci-runner/k3s/phase2/factory/DERIVATION.md` sits beside the
manifest whose numbers it derives: a capacity claim with no derivation beside it
is re-guessed by whoever next needs it.

Work-item `livespec-dev-tooling-due2h6`. Plan: livespec
`factory-worker-nodes-gitops`, epic `livespec-sqvj7p`.

## RAISED 2026-10-24: the ceiling is now sixteen pods

The `factory-runs` quota was raised from 3 to 8 concurrent runs, so `pods: "16"`
(8 runs x sandbox + replacement); `ci-runner/k3s/phase2/factory/DERIVATION.md`
"The quota, raised to eight runs" carries the derivation. Measured that day at
`/srv/factory-workspaces`:

| Node | Free | Workspace directories present | Per-workspace budget at sixteen pods |
|---|---|---|---|
| `poweredge-xubuntu` | **160 G** | 24 | **10 G** |
| `gmktec-xubuntu` | **153 G** | 10 | **9.6 G** |

`gmktec-xubuntu` now binds (its free space fell from 366 G on 2026-10-16), at
about 9.6 G per workspace if one node took every pod. That is tighter than the
27 G below and still above any committed run's clone, but the per-run
high-water mark remains UNMEASURED; the soak that settles the quota should
record it. The 24 directories on poweredge exceed the live pod count, so
workspace cleanup on pod deletion is worth checking in the same soak.

The section below is the original six-pod sizing, kept as the record.

## The ceiling is the quota, and it was six pods

The `factory-runs` `ResourceQuota` in
`../../../ci-runner/k3s/phase2/factory/factory-namespace.yaml` admits
`pods: "6"` into the `factory` namespace, derived there as *3 concurrent runs x
(1 sandbox + 1 in-flight replacement)*. That quota is the ONLY bound
on what factory runs take from the CI pool (maintainer ruling 2026-10-13: Kueue
is not in the factory path), so six is the most workspaces that can exist at
once ACROSS the pool — not per node. A node that is scheduled all six holds six
workspaces; the scheduler, not this role, decides which node that is.

## What each node serves the path from, measured

Read on 2026-10-16 (work-item `livespec-dev-tooling-due2h6`), with the free
space on the filesystem `/srv` resolves to:

| Node | `/srv` lives on | Free at the measurement | Per-workspace budget at six pods |
|---|---|---|---|
| `poweredge-xubuntu` | the ext4 root filesystem | **163 G** | **27 G** |
| `gmktec-xubuntu` | the ext4 root filesystem | **366 G** | **61 G** |
| `hp-xubuntu` | the ext4 root filesystem | **397 G** | **66 G** |

**`poweredge-xubuntu` binds**, at about 27 G per concurrent workspace if one
node took the whole quota's worth. A factory workspace is a repository clone
plus whatever that run's build writes into it; the sandbox the factory's own
runs are prepared in is the 4 cpu / 8 GB `livespec-ci` environment
`ansible/inventory/host_vars/hp-xubuntu.yml` declares, and no committed run of
it has approached 27 G. The budget is therefore comfortable rather than tight,
and the honest statement about the tail is that the per-run high-water mark has
NOT been measured — this file records the headroom, not a measured demand.

## hp's 3.6 T volume, and why the path is not on it

`hp-xubuntu` carries a 3.6 TiB ext4 filesystem at `/srv/sandbox-storage` (the
`sandbox-stores` label; `../sandbox_storage/`), and the work-item explicitly
permits backing hp's workspace root with it as long as the absolute path stays
`/srv/factory-workspaces`. It is deliberately NOT used:

- hp's root filesystem already offers the most headroom of the three (397 G),
  so the volume would buy capacity at the node that needs it least;
- a bind mount or symlink at the workspace root would make hp's path a
  different SHAPE from the other two nodes' — one node where the path is a
  mount point and two where it is a directory — and the plugin's single
  `workspace_root` is an argument for sameness;
- `/srv/sandbox-storage` is managed by `../sandbox_storage/`, whose cutover
  stops docker and containerd and whose reclaim deletes old store copies.
  Putting factory workspaces under a tree another role migrates and reclaims is
  exactly the coupling this work-item's second assertion exists to prevent.

If `poweredge-xubuntu`'s 163 G ever becomes the binding constraint, the move is
to give THAT node a dedicated filesystem at the path — not to special-case hp.
Whatever serves it must still be persistent and non-tmpfs, which the role
measures on every apply (`factory_workspace_root_volatile_fstypes`).

## Nothing reclaims it

The directory is excluded from every boot-time converge and every reclaimer in
this repository, and that exclusion is asserted rather than documented:
`tests/livespec_dev_tooling/test_factory_workspace_root_not_reclaimed.py`
resolves it over the whole committed tree. The two reclaimers that run on a
Fabro factory host — `../storage_reclaim/files/storage-reclaim.sh` and
`../container_reclaim/files/container-reclaim.sh` — carry the path in their own
deny lists, so neither can be pointed at it even by a host variable. Capacity
is therefore recovered by whoever owns a workspace (the sandbox backend removing
a finished run's directory), never by a sweep that cannot tell a live workspace
from a dead one.
