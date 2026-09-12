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
| 1 | **Storage layout** | `storage-layout.sh <profile>` (here) | The storage-controller virtual disk, the GPT partition table (EFI system partition + LVM physical volume), the volume groups, the logical volumes, and the `mkfs` that puts the role LABELS on them. On a node that KEEPS the operating system it already has, `DISK_PLAN=free-space` skips the controller and the erase and takes only the device's unpartitioned tail — see "The two disk plans" below. |
| 2 | **Base operating system** | `base-os-install.sh <profile>` (here) | **An installed operating system** — the precondition the specification section names for the k3s stage — on the volumes stage 1 created: the pinned release debootstrapped into the root logical volume, an `/etc/fstab` whose every line is found by LABEL, `lvm2` and an initramfs that activates the root volume group, a signed shim and GRUB on the EFI system partition with `root=` by LVM id, the firmware boot entry, the hostname, the profile's network address, and the operator account the later stages are run as. |
| 3 | **k3s** | on an `agent` first: `with-github-ci-runners-env.sh -- ../secret-reinjection/seed-k3s-agent-join-token.sh profiles/<node>.env`; then `../provision-k3s.sh profiles/<node>.env` | The pinned k3s in the role this node's `CLUSTER_ROLE` declares. A `server` gets the control plane, its config installed before the first start, and the admin kubeconfig every later step reads; an `agent` gets the pinned agent join to `CLUSTER_JOIN_ADDRESS`, pinning `--node-ip` from `NODE_ADDRESS` and registering every `NODE_TAINTS` taint, with the join token read at run time out of `CLUSTER_TOKEN_FILE`. **On an `agent` the seed step comes first** — this tree carries no secret, and `provision-k3s.sh` refuses (in `--dry-run` too) until `CLUSTER_TOKEN_FILE` exists `0600 root:root`. The seed is the ONE attended step that puts it there, from the `github-ci-runners` 1Password Environment; a `server` runs neither it nor anything that needs it, because a server MINTS that token at `/var/lib/rancher/k3s/server/node-token`. The seed also CREATES `/etc/rancher/k3s` when this node has never run k3s: that directory is normally made by the k3s installer, which on an agent runs in this same stage but AFTER the seed — so no hand-run `mkdir` stands between stage 2 and stage 3, and this stage is executable exactly as written (the deadlock was found live on `gmktec-xubuntu` 2026-09-07). A missing parent anywhere ELSE it still refuses, so a mistyped `CLUSTER_TOKEN_FILE` is refused rather than manufactured. |
| 4 | **Node-local runbook** | `sudo ../phase2/install-node.sh profiles/<node>.env` | Every node-local installer under `../phase2/` plus `../secret-reinjection/` that this node's `CLUSTER_ROLE` calls for, at the `ADMISSION_CAPACITY_C` the same profile carries — including `../phase2/storage-layout/install-storage-layout.sh`, which is stage 1's CONSUMER: it MOUNTS the three tiers stage 1 labelled, creates the two tier mountpoints on the cache volume, writes the five fstab lines and the k3s drop-in, and — because it runs HERE, after stage 3 — moves a running k3s's containerd store onto its tier rather than letting a bind hide it. No mount, `mkdir` or re-run is done by hand at any point, and nothing in this stage has to run before k3s. A `server` runs the whole list; an `agent` runs its node-local subset and skips the cluster-side and datastore steps, logging the reason for each. |

**Why stage 1 must come first, and why stage 4 cannot substitute for it.**
`../phase2/storage-layout/install-storage-layout.sh` mounts each tier BY LABEL
and writes the five `/etc/fstab` lines and the k3s drop-in that find it that
way, and it refuses when a label resolves to zero block devices. It never
formats anything. Producing the labelled filesystems it looks for is what
stage 1 does; running stage 4 on a node that never had stage 1 fails closed,
by design. What it does NOT need is to run before k3s: the k3s stage is 3 and
this is 4, and step 5 of the installer is what makes that safe — a bind laid
over a live containerd store would hide it, so the store is moved onto its
tier with the k3s unit stopped and the unit is started again afterwards.
Until `livespec-dev-tooling-3qyv` the installer neither mounted anything nor
knew about a running k3s: it printed a hand step, wrote the five lines and
exited 1 on the `findmnt --verify` that the unmounted tier mountpoints failed,
which is how `gmktec-xubuntu` was left half-applied on 2026-09-07.

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
| `profiles/poweredge-xubuntu.expected-plan` | Every mutating command that node's `--dry-run` plans against bare storage, in order, byte for byte. `storage-layout-exit-tests.sh` §F13 compares the run against it as an EQUALITY, which is what §B's ordered-subset assertions cannot do: a step silently added, dropped or reworded between two asserted rungs passes §B and fails §F13. It is the guard that let `free-space` be added to this script without changing what the first node's rebuild does. |
| `profiles/poweredge-xubuntu.recorded-facts` | That node's storage facts as the host RECORD states them, transcribed from `poweredge-xubuntu-info` `AGENTS.md` §Storage ("LVM (steady state since 2026-09-06)") and confirmed read-only against the live host the same day. The profile beside it carries **the record's values, verified live on 2026-09-06**; `storage-layout-exit-tests.sh` §E fails if the two ever disagree. See "The profile is the record" below. |
| `profiles/gmktec-xubuntu.env` | **The second node's profile — and this plan's rehearsal of the recipe.** No storage controller; `DISK_PLAN=free-space` on `/dev/nvme0n1`, preserving the ext4 root at `nvme0n1p1` and the EFI system partition at `nvme0n1p2` the node already boots from; volume group `nvmea` on the tail partition `nvme0n1p3` carrying all three tiers (`ci-cache` 350 GiB ext4, `ci-containerd` 525 GiB ext4, `ci-workvols` 525 GiB XFS with reflink) out of the measured 1441 GiB of unpartitioned space; `eno1` at `192.168.1.156/24`, both PINNED; `CLUSTER_ROLE=agent` joining `https://192.168.1.200:6443` with the join token read at run time out of `/etc/rancher/k3s/agent-join-token`; and `node-role/ci=pending:NoSchedule` with `ADMISSION_CAPACITY_C=0`, which is "joined, and taking nothing" said twice on purpose. The base-OS keys are INERT — stage 2 is not a stage this node runs — but they are the NODE's, not the first node's: the 2026-09-06 read found all four of the values originally copied across wrong, so `ESP_LABEL` and `ROOT_LABEL` are EMPTY (neither partition carries a label), `BOOT_ENTRY_LABEL` is `Ubuntu` and `OPERATOR_ACCOUNT` is `cwoolley`. **No line of this profile is marked `# UNVERIFIED`.** The empty root label is what stage 2 now refuses on, by name, rather than debootstrapping over the operating system `free-space` exists to keep — see the profile's own header. `storage-layout-exit-tests.sh` §G and `../provision-k3s-exit-tests.sh` §E assert this profile's plans off-host. |
| `profiles/gmktec-xubuntu.expected-plan` | Every mutating command that node's `--dry-run` plans, in order, byte for byte — captured from the run BEFORE the four base-OS values were resolved, so "resolving them changed no storage command" is an assertion rather than a claim. `storage-layout-exit-tests.sh` §G13 compares the run against it as an EQUALITY; §G4 and §G5 assert a partition number and an ordered subset, which a step silently added, dropped or reworded between two asserted rungs would pass. |
| `profiles/gmktec-xubuntu.recorded-facts` | That node's facts as the 2026-09-06 read-only read of the live host found them: the volumes and tiers the procedure creates, the two partitions it preserves (`p1` ext4 465.7G at `/`, `p2` vfat 1G at `/boot/efi`), and the four base-OS values — two of them EMPTY, which the format spells as a `key` record with no value. `storage-layout-exit-tests.sh` §G9–§G12 fail if the profile and the record ever disagree, in either direction. This node earned its record before it was ever built: four of its values were placeholders copied from the first node's profile and the read found ALL FOUR wrong. See "The profile is the record" below. |
| `profile.sh` | The ONE parser for that format, **sourced** by every stage and never run. Each stage refuses a key it does not know, so a per-stage key list would make the key a later stage needs break an earlier one; there is therefore exactly one list, here. |
| `storage-layout-exit-tests.sh` | Stage 1's exit tests. Runs the script only through `--dry-run`, against fake probe tools, with every mutating command replaced by a tripwire — so the suite proves the ordering, the profile validation, the consent refusals, the free-space plan's skips and preservation refusals, the first profile's agreement with the recorded facts, and (§G) that the committed `gmktec-xubuntu` profile declares the second node's measured facts, agrees with that node's own recorded facts, and yields the plan they imply byte for byte, while touching no host at all. |
| `base-os-install-exit-tests.sh` | Stage 2's exit tests, built the same way. Proves the `--dry-run` command order, that the rendered `/etc/fstab` finds root, the ESP and the three tiers by LABEL and that its five tier lines are byte-exact with the ones the single committed source `ansible/roles/storage_layout/files/ci-tiers.fstab` carries — §B3 and §B4 READ that fragment rather than restating the lines, which makes the suite the arbiter both of what this stage renders and of what `../phase2/storage-layout/install-storage-layout.sh` ensures — that `lvm2` reaches the chroot before the initramfs is regenerated, that a populated root volume is refused unless the invocation names it, and (§F) that a profile whose root filesystem carries NO label — a node that KEEPS the root it already has — is refused by that reason before anything is derived or mounted. |

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

**Every node gets one.** `profiles/gmktec-xubuntu.recorded-facts` is the second
node's, compared the same way by §G9–§G12 and under the same one-way trust rule.
That node makes the case more sharply than the first: it had never been built,
so four of its values were placeholders copied from the first node's profile and
marked `# UNVERIFIED` — and when the host was finally read, on 2026-09-06, **all
four were wrong.** `ESP` and `root` are labels neither of its partitions carries,
`ubuntu` is not the case its firmware entry uses, and `ci-admin` has no passwd
entry there. Every one of them read as a perfectly ordinary profile line, which
is the same failure mode as the 64 GiB swap and not a different one. The record
also holds the two partitions the node preserves, which is what makes "stage 1
derives partition **3**" an assertion against a fact rather than against a
constant: the record says 1 and 2 are taken, so 3 is the next free number, and
`VOLUME_GROUPS` must spell out that same number as a path.

## The two disk plans

The first pool node's disk is a RAID-5 virtual disk this procedure creates, so
stage 1 is free to erase it. The second is not: `gmktec-xubuntu` keeps the
operating system it already runs — a 2 TB NVMe whose partition 1 is the ext4
root and partition 2 the EFI system partition, with the rest of the device
unpartitioned. The tiers go in that unpartitioned tail, and nothing else on the
device may be touched. That node's profile is committed beside the first's, as
`profiles/gmktec-xubuntu.env`, and it is the plan below expressed entirely as
data — no line of this tree's code is second-node-specific.

That is one procedure with two plans, selected by the profile's `DISK_PLAN`,
and NOT two scripts:

| | `DISK_PLAN=whole-device` (the default) | `DISK_PLAN=free-space` |
|---|---|---|
| What the device holds first | nothing this node needs | this node's running operating system |
| Storage controller | the virtual disk is created | skipped: the node boots off the storage it already has |
| Erase | `wipefs` (on consent) + `sgdisk --zap-all` | none |
| Partitions written | 2 — the EFI system partition, then the LVM physical volume | 1 — `sgdisk --new=N:0:0` typed `8e00`, `N` the next free number read off the device's own table, filling the largest free region |
| EFI system partition | made, as the profile's type and label | left alone; the profile's `ESP_*` keys describe the existing one so the later stages can find it |
| `ESP_LABEL` and `ROOT_LABEL` | REQUIRED to be non-empty: the procedure makes both filesystems with `mkfs -L`, and the fstab stage 2 renders finds them by LABEL | MAY be EMPTY, which is this format's spelling for "carries no label" — a fact about filesystems the node already has, and one a plain installer leaves behind routinely |
| Physical volume onward | identical | identical |

`PRESERVED_PARTITIONS` names the device paths no step may write to.
`free-space` REQUIRES it to be non-empty — that plan exists to protect
something — and `whole-device` requires it to be EMPTY, because a plan that
erases the whole device cannot keep a partition, and a key promising otherwise
would be a lie the run does not tell. Both are refusals at parse time.

Two consequences worth stating plainly:

- **Preservation outranks consent.** `--i-consent-to-destroy` names a target
  the profile is willing to lose; a `PRESERVED_PARTITIONS` entry names one it
  is not. No flag unlocks a preserved partition, and the refusal names it. The
  guard sits in the one function every mutating command passes through and
  scans that command's arguments, so it covers steps this script does not have
  yet.
- **The profile still names the tail partition's device.** `N` is derived from
  the device, but `VOLUME_GROUPS` names the physical volume as a path
  (`…nvme0n1p3`). Those must agree; a dry run prints the number it derived, so
  read it before the live run rather than assuming.

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

A third: it does not reach a partition the profile lists in
`PRESERVED_PARTITIONS`. Consent is per-target permission to destroy;
preservation is a standing refusal, and the two keys are answering different
questions. See "The two disk plans" above.

## Always dry-run first

```bash
# unprivileged, touches nothing, prints the whole plan:
./storage-layout.sh --dry-run profiles/poweredge-xubuntu.env
./base-os-install.sh --dry-run profiles/poweredge-xubuntu.env

# then, from the Recovery USB, as root:
sudo ./storage-layout.sh --i-consent-to-destroy=/dev/sda profiles/poweredge-xubuntu.env
sudo ./base-os-install.sh profiles/poweredge-xubuntu.env

# the second node — same script, different profile, and no consent flag at all:
# a free-space plan touches nothing that already holds something.
./storage-layout.sh --dry-run profiles/gmktec-xubuntu.env
sudo ./storage-layout.sh profiles/gmktec-xubuntu.env
```

For `gmktec-xubuntu` the dry run is not optional advice. It prints the
partition NUMBER it derived off the device's own table, and that number must be
the one `VOLUME_GROUPS` spells out as a path (`…nvme0n1p3`) — the profile
cannot state it and the script cannot check it. `base-os-install.sh` is NOT run
on that node: it keeps the operating system `free-space` exists to preserve,
and the stage refuses against its profile rather than debootstrapping over it.

The dry run also prints the **tool preflight**, which is stage 1 of the storage
run and sits ahead of every mutating command precisely so a node cannot start a
layout it has no way to finish. It derives the tools the plan will reach for
from the plan itself — `sgdisk`, `partprobe`, the LVM trio, and the maker each
declared filesystem type is made with — and the two disk plans answer an absent
one differently, because they run in different places:

* under `DISK_PLAN=free-space` the run is on the node's own installed operating
  system, which has a package manager and may simply never have been given
  lvm2. The missing packages are installed FIRST, printed as a single
  `+ apt-get install -y --no-install-recommends lvm2 xfsprogs` line ahead of
  the first `+ sgdisk`, and every tool is re-probed afterwards. This is not
  hypothetical: `gmktec-xubuntu` was read on 2026-09-07 and has `sgdisk`,
  `partprobe` and `mkfs.ext4` and has neither lvm2 nor xfsprogs. Without the
  preflight its first live run would have cut partition 3, re-read the table,
  died at `pvcreate: command not found` and left a partition with nothing on
  it — after which a re-run would size its "largest free region" against a
  device that had changed under it;
* under `DISK_PLAN=whole-device` the run is from the Recovery USB, which is
  BUILT to carry these tools, so installing them would paper over a defect in
  the USB. An absent tool is a refusal before anything is written, naming the
  package to add to `recovery-usb/build-recovery-usb.sh`. Under `--dry-run` it
  is printed as `WOULD REFUSE: <tool> absent (<package>)` and the run carries
  on, so a workstation dry run still shows the whole plan.

On a node carrying every tool the stage prints neither line, which is why the
committed `profiles/*.expected-plan` captures are unaffected by it.

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

**The `gmktec-xubuntu` build IS that rehearsal**, and it is the first one this
recipe gets. The first node's profile was written from a rebuild that had
already been done by hand on 2026-09-04, so the procedure describes that node
rather than having produced it; the second node has not been built yet, which
makes building it the first end-to-end execution of the one procedure from a
committed artifact. It is a partial rehearsal by construction — a `free-space`
node keeps its operating system, so stage 2 is not exercised — and it is
nonetheless what turns stages 1, 3 and 4 from written into run. Record its
outcome on the plan's ledger item, naming the procedure revision and
`profiles/gmktec-xubuntu.env` as the profile it ran with.

That profile carries **no `# UNVERIFIED` line at all**: its four remaining
placeholders were read off the live host on 2026-09-06, ahead of the rehearsal,
and all four were wrong — two labels the node does not have, a boot entry whose
case did not match, and an operator account with no passwd entry there. What
replaces the marker is `profiles/gmktec-xubuntu.recorded-facts` and the
assertions that compare the two, because a resolved value drifts as silently as
an unverified one and the marker was the only thing that had been watching.
`profiles/poweredge-xubuntu.env` still carries its own `# UNVERIFIED` lines, and
those remain unresolved until a rehearsal of THAT node reads them.

## Out of scope here

The Recovery USB builder is its own work item, as is any node's profile beyond
the two committed here. Nothing in this tree executes against a live host as
part of its tests.
Stage 2 deliberately installs NO credential for the operator account it
creates: this tree carries no secret, so authorizing a login for it is the
operator's step at the console.
