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
| 2 | **Base operating system** | `base-os-install.sh <profile>` (here) | **An installed operating system** — the precondition the specification section names for the k3s stage — on the volumes stage 1 created: the pinned release debootstrapped into the root logical volume, an `/etc/fstab` whose every line is found by LABEL, `lvm2` and an initramfs that activates the root volume group, a signed shim and GRUB on the EFI system partition with `root=` by LVM id, the firmware boot entry, the hostname, the profile's network address, and the operator account the later stages are run as. |
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

Neither stage contains a value that belongs to one node: not a device, not a
slot list, not a volume-group name, not a size, not a release, not a hostname,
not an address, not an account name. Every one of those is read from the
`profiles/<node>.env` named on the command line. A second pool node is a
**second profile** consumed by the same scripts — never a second script and
never a hand-edited copy of one.

| Path | Role |
|---|---|
| `storage-layout.sh` | Stage 1. Creates the controller virtual disk, partitions, the physical volumes, the volume groups, the logical volumes, and the filesystems with their role labels. Re-runnable; destructive only on explicit consent; `--dry-run` prints every command and runs none. |
| `base-os-install.sh` | Stage 2. Mounts the profile's root logical volume and EFI system partition, debootstraps the release the profile pins, writes an `/etc/fstab` found entirely by LABEL, installs the kernel, `lvm2` and the bootloader in the chroot, regenerates the initramfs with LVM support, sets the hostname, the network address, the operator account and the firmware boot entry. Re-runnable — a root volume already carrying the profile's release is left alone and reported; destructive only on explicit consent; `--dry-run` prints every command and file write and runs none. |
| `profiles/poweredge-xubuntu.env` | The first node's profile: the PERC H730P RAID-5 virtual disk over slots 0-6 at a 64 KB strip with WriteBack + Read Ahead + Direct IO, a 1 GiB EFI system partition, one LVM physical-volume partition, volume group `poweredge` carrying `root`, `swap` and `ci-cache`, volume group `nvmea` carrying `ci-containerd`, volume group `nvmeb` carrying `ci-workvols`, and the base-OS values stage 2 consumes (Ubuntu 26.04 `resolute`, its mirrors, the kernel package, the initramfs generator, the boot-entry label and the operator account). Its header records the provenance of every value, including which values this repository has NOT measured. |
| `profiles/poweredge-xubuntu.recorded-facts` | That node's storage facts as the host RECORD states them, transcribed from `poweredge-xubuntu-info` `AGENTS.md` §Storage ("LVM (steady state since 2026-09-06)") and confirmed read-only against the live host the same day. The profile beside it carries **the record's values, verified live on 2026-09-06**; `storage-layout-exit-tests.sh` §E fails if the two ever disagree. See "The profile is the record" below. |
| `profile.sh` | The ONE parser for that format, **sourced** by every stage and never run. Each stage refuses a key it does not know, so a per-stage key list would make the key a later stage needs break an earlier one; there is therefore exactly one list, here. |
| `storage-layout-exit-tests.sh` | Stage 1's exit tests. Runs the script only through `--dry-run`, against fake probe tools, with every mutating command replaced by a tripwire — so the suite proves the ordering, the profile validation, the consent refusals and the profile's agreement with the recorded facts while touching no host at all. |
| `base-os-install-exit-tests.sh` | Stage 2's exit tests, built the same way. Proves the `--dry-run` command order, that the rendered `/etc/fstab` finds root, the ESP and the three tiers by LABEL and that its five tier lines are byte-exact with the ones `../phase2/storage-layout/install-storage-layout.sh` ensures, that `lvm2` reaches the chroot before the initramfs is regenerated, and that a populated root volume is refused unless the invocation names it. |

Read the profile's own header for the format. In one line: `KEY=value`, parsed
and never sourced, list-valued keys holding space-separated `:`-delimited
records.

## The profile is the record

`profiles/poweredge-xubuntu.env` carries **the host record's values, verified
live on 2026-09-06**: the record is `poweredge-xubuntu-info` `AGENTS.md`
§Storage, subsection "LVM (steady state since 2026-09-06)", and the same day's
read-only `vgs` / `lvs` / `ls -l /dev/disk/by-id` on the node itself agreed with
it. Nothing in the storage keys is a guess.

It was not always so, and the way it failed is the reason this section exists.
The profile declared `swap` at 64 GiB where the node has 8 GiB, and put
`ci-workvols` on `nvmea` — when the node has **two** NVMe volume groups, `nvmea`
(serial `…25384T801085`) carrying `ci-containerd` and `nvmeb` (serial
`…25374X802154`) carrying `ci-workvols`, and the profile did not declare the
second one at all. Both wrong values parsed cleanly, planned cleanly and dry-ran
cleanly: every test asked whether the profile was WELL FORMED, and none asked
whether it was TRUE. A live rebuild from it would have built a layout the node
does not have.

So the record now has a machine-readable transcription of its own,
`profiles/poweredge-xubuntu.recorded-facts`, and `storage-layout-exit-tests.sh`
§E compares the profile against it — using the parser the stages themselves
source, and as an equality in both directions, so an omitted fact fails as
loudly as an invented one. Two rules follow from that, and they are not
symmetric:

- **Trust flows one way.** A disagreement is a defect in the PROFILE. Fixing §E
  by editing the facts table to match a drifted profile is the exact inversion
  this guards against; the table changes only by re-reading the host record.
- **`VD_ENCLOSURE=auto` earns its keep by test.** `auto` is admissible instead
  of a pinned literal only because case B5 drives the resolver with the
  enclosure table this node's H730P prints and asserts it plans
  `drives=32:0-6`. A node whose enclosure the resolver cannot read that way
  pins the number in its own profile.

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
| the root logical volume's contents | the logical volume's device path | the volume is populated and does NOT already carry the release the profile pins (a volume that DOES carry it is left alone, not destroyed) |

Two things this rule deliberately does NOT do. It does not accept a blanket
"yes to everything" flag: a run that would destroy three volumes needs three
targets spelled out. And it is evaluated identically under `--dry-run`, so a
dry run tells the operator in advance exactly which consents a live run will
need.

## Always dry-run first

```bash
# unprivileged, touches nothing, prints the whole plan:
./storage-layout.sh --dry-run profiles/poweredge-xubuntu.env
./base-os-install.sh --dry-run profiles/poweredge-xubuntu.env

# then, from the Recovery USB, as root:
sudo ./storage-layout.sh --i-consent-to-destroy=/dev/sda profiles/poweredge-xubuntu.env
sudo ./base-os-install.sh profiles/poweredge-xubuntu.env
```

`--dry-run` still runs the read-only PROBES — that is how it derives the plan —
but executes no mutating command. A probe whose tool is not installed reports
"absent", so a dry run on a workstation prints the full sequence a bare node
would take. In stage 2 the mount is one of the printed commands rather than a
probe, so a dry run reads whatever is already at the mount root when it decides
whether the root volume is populated; on a workstation that is nothing, and the
full fresh-install sequence is printed.

## Rehearsed before trusted

The specification section above requires a node's rebuild procedure to be
**rehearsed** — executed from empty storage through to the node executing a job
— before it is relied on for that node, and again after any change to the
procedure or to that node's profile, with the outcome recorded on the owning
ledger item naming the procedure revision and the profile it ran with.

**As of the first landing of this tree, no rehearsal has been performed.** Both
stages are therefore UNPROVEN in the specification's sense, and every value
`profiles/poweredge-xubuntu.env` marks `# UNVERIFIED` is unresolved until one
happens. A step a rehearsal cannot reproduce is a defect in the procedure, to
be scripted — never an accepted gap.

## Out of scope here

The Recovery USB builder and any further node's profile are their own work
items. Nothing in this tree executes against a live host as part of its tests.
Stage 2 deliberately installs NO credential for the operator account it
creates: this tree carries no secret, so authorizing a login for it is the
operator's step at the console.
