# phase 0 — bare metal: from powered-on hardware to a node k3s can be installed on

Everything under `../` assumes a node that already has an operating system, a
partition table, volume groups and the three role-labelled filesystems the CI
tiers live on. This tree is where those come from.

Until 2026-09-06 they came from nowhere in git: the seven-drive RAID-5 virtual
disk, the drive erase, the EFI system partition, the LVM physical volume, the
volume group and its logical volumes and every `mkfs` were hand-run from a
Recovery USB on 2026-09-04, and only the END STATE was recorded, in the
per-host information repository. That is exactly the gap
`SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild
recipe" closes: one procedure, staged, every stage a committed executable
artifact, with each node's values in a profile beside it.

## Stage order

A rebuild done exactly as written starts from **empty storage**, not from a
prepared disk. The stages run in this order, and none of them may be skipped
because a node "already looks right":

| # | Stage | Artifact | State it establishes |
|---|---|---|---|
| 1 | **Storage layout** | `storage-layout.sh <profile>` (here) | The storage-controller virtual disk, the GPT partition table (EFI system partition + LVM physical volume), the volume groups, the logical volumes, and the `mkfs` that puts the role LABELS on them. |
| 2 | **Base operating system** | *not yet scripted — its own work item, depends on this stage* | An installed, bootable operating system on the volumes stage 1 created, and the base packages the later stages need. |
| 3 | **k3s** | `../provision-k3s.sh` | The pinned single-node k3s server, its config installed before the first start, and the admin kubeconfig every later step reads. |
| 4 | **Node-local runbook** | `sudo ../phase2/install-node.sh profiles/<node>.env` | Every node-local installer under `../phase2/` plus `../secret-reinjection/` that this node's `CLUSTER_ROLE` calls for, at the `ADMISSION_CAPACITY_C` the same profile carries — including `../phase2/storage-layout/install-storage-layout.sh`, which is stage 1's CONSUMER. A `server` runs the whole list; an `agent` runs its node-local subset and skips the cluster-side and datastore steps, logging the reason for each. |

**Why stage 1 must come first, and why stage 4 cannot substitute for it.**
`../phase2/storage-layout/install-storage-layout.sh` writes the five `/etc/fstab`
lines and the k3s drop-in that find each tier BY LABEL, and it refuses when a
label resolves to zero block devices. It never formats anything. Producing the
labelled filesystems it looks for is what stage 1 does; running stage 4 on a
node that never had stage 1 fails closed, by design.

`C` for stage 4 is the value in the node's profile
(`ADMISSION_CAPACITY_C`), which is also the value the ten ClusterQueue quotas
sum to — never a stale literal. See `../phase2/kueue/DERIVATION.md`.

## One procedure, one profile per node

`storage-layout.sh` contains no value that belongs to one node: not a device,
not a slot list, not a volume-group name, not a size. Every one of those is
read from the `profiles/<node>.env` named on the command line. A second pool
node is a **second profile** consumed by the same script — never a second
script and never a hand-edited copy of one.

| Path | Role |
|---|---|
| `storage-layout.sh` | Stage 1. Creates the controller virtual disk, partitions, the physical volumes, the volume groups, the logical volumes, and the filesystems with their role labels. Re-runnable; destructive only on explicit consent; `--dry-run` prints every command and runs none. |
| `profiles/poweredge-xubuntu.env` | The first node's profile: the PERC H730P RAID-5 virtual disk over slots 0-6 at a 64 KB strip with WriteBack + Read Ahead + Direct IO, a 1 GiB EFI system partition, one LVM physical-volume partition, volume group `poweredge` carrying `ci-cache`, and volume group `nvmea` carrying `ci-containerd` and `ci-workvols`. Its header records the provenance of every value, including which values this repository has NOT measured. |
| `storage-layout-exit-tests.sh` | The stage's exit tests. Runs the script only through `--dry-run`, against fake probe tools, with every mutating command replaced by a tripwire — so the suite proves the ordering, the profile validation and the consent refusals while touching no host at all. |

Read the profile's own header for the format. In one line: `KEY=value`, parsed
and never sourced, list-valued keys holding space-separated `:`-delimited
records.

## The consent rule

Every step that would destroy existing storage **refuses** unless the
invocation carries

```text
--i-consent-to-destroy=<target>
```

naming that **exact** target, and the refusal names the target it refused.
Consent for one target is never consent for another; the flag is repeatable
when a run legitimately needs several.

A step is destructive when — and only when — the thing it is about to write
over currently holds something. On genuinely empty storage nothing is
destructive and no consent is needed. The targets are:

| Target | Named as | Destroyed when |
|---|---|---|
| the storage controller's virtual disk | `vd:c<controller-id>` | a virtual disk already exists and does not match the profile |
| the target disk | its device path | the disk already carries a partition table or a filesystem signature |
| an LVM physical volume | its device path | the device already carries a non-LVM signature |
| a filesystem | the logical volume's (or partition's) device path | the volume already carries a filesystem, and the profile declares a different type or label |

Two things this rule deliberately does NOT do. It does not accept a blanket
"yes to everything" flag: a run that would destroy three volumes needs three
targets spelled out. And it is evaluated identically under `--dry-run`, so a
dry run tells the operator in advance exactly which consents a live run will
need.

## Always dry-run first

```bash
# unprivileged, touches nothing, prints the whole plan:
./storage-layout.sh --dry-run profiles/poweredge-xubuntu.env

# then, from the Recovery USB, as root:
sudo ./storage-layout.sh --i-consent-to-destroy=/dev/sda profiles/poweredge-xubuntu.env
```

`--dry-run` still runs the read-only PROBES — that is how it derives the plan —
but executes no mutating command. A probe whose tool is not installed reports
"absent", so a dry run on a workstation prints the full sequence a bare node
would take.

## Rehearsed before trusted

The specification section above requires a node's rebuild procedure to be
**rehearsed** — executed from empty storage through to the node executing a job
— before it is relied on for that node, and again after any change to the
procedure or to that node's profile, with the outcome recorded on the owning
ledger item naming the procedure revision and the profile it ran with.

**As of the first landing of this tree, no rehearsal has been performed.** The
stage is therefore UNPROVEN in the specification's sense, and the two values
`profiles/poweredge-xubuntu.env` marks `# UNVERIFIED` are unresolved until one
happens. A step a rehearsal cannot reproduce is a defect in the procedure, to
be scripted — never an accepted gap.

## Out of scope here

The base-OS install stage (2), the Recovery USB builder, and any further node's
profile are their own work items. Nothing in this tree executes against a live
host as part of its tests.
