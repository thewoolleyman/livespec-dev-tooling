---
topic: docker-engine-guard-half-installed-reunpack
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-17T20:59:44Z
---

## Proposal: the package fence re-unpacks a half-installed intended package from its audited archive

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Amend the package-fence recovery sentence of §"Docker engine install guard" so that a package an interrupted unpack left `half-installed` is re-unpacked from this run's own audited `.deb` with `dpkg --unpack` naming that one archive, instead of being handed to `dpkg --configure`, which cannot complete a half-installed package. Without this, a kill landing during an intended package's unpack strands every later run on the host.

### Motivation

Measured 2026-10-17 on poweredge acceptance VMs against release v1.112.10, which contains guard child 13b (livespec-dev-tooling-mrr7ye, PR #2588). FAULTS B-06 (gate 20261017T204354Z-2505456, guard-vm-0, run r2026101720475766b8): the guard's publish unit and dpkg were SIGKILLed while `dpkg -i` unpacked docker.io; dpkg.log ends at `install docker.io:amd64 <none> 29.1.3-0ubuntu4.1` / `status half-installed docker.io`, and `dpkg --audit` reports docker.io as needing reinstallation with its list and md5sums control files missing. `recover` then configured runc and containerd and completed man-db's trigger (`trigproc man-db` then `status installed man-db` at 20:55:23-25), which is 13b working, and refused with `publish refuse: dpkg --audit names ('docker.io', 'docker.io', 'docker.io') after recovery, so dpkg is still interrupted`, leaving the run in phase publishing. FAULTS R-06/M-04 (gate 20261017T204354Z-2505654, guard-vm-2): after a rollback from publishing left docker.io half-installed, the next run's publish refused with the same message and rolled back, and `dpkg --audit` still names docker.io, so every later run on that host will refuse the same way. The earlier B-06 runs at v1.112.9 (guard-vm-0 at 18:4x and guard-vm-1 at 19:0x) left docker.io in the same half-installed state, and guard-vm-1 still shows it, so this is the kill landing in docker.io's unpack, not timing noise. apt-daily-upgrade fired on guard-vm-0 at 20:55:39, after recover had already exited at 20:55:26, and guard-vm-2 ran no apt job at all, so no foreign transaction caused either refusal. Root cause in the ratified text: recovery may only aim `dpkg --configure` at a half-installed leftover, but dpkg cannot configure a half-installed package; only re-unpacking its archive clears that state. Because the step MUST issue `dpkg -i` only when the post-recovery audit is empty, a half-installed intended package can never be cleared, so a kill during an intended package's unpack strands the run, contrary to FAULTS B-06's pass line (recover completes or rolls back, never stranded) and M-04's (the next publish completes a non-empty audit inside the fence). This blocks mrr7ye's host-captured assertion (recover completes man-db and the run's publish finishes with dpkg --audit empty). Plan petri-factory-on-gmktec, epic bd-ib-fyozyd in livespec-orchestrator-beads-fabro.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Docker engine install guard", in the package-fence paragraph that begins "The package step MUST run `dpkg -i` on exactly the audited `.deb` files", replace the sentence

> Recovery of an interrupted install MUST run `dpkg --configure` only on `half-installed`, `unpacked` or `half-configured` packages that are a guard run's leftover.

with:

> Recovery of an interrupted install MUST first re-unpack each `half-installed` package that is a guard run's leftover, by running `dpkg --unpack` with `DPKG_FRONTEND_LOCKED=1` naming exactly the audited `.deb` of this run whose package name, version and architecture equal the half-installed package's. It MUST refuse naming the package when no audited `.deb` of this run has that name, version and architecture. It MUST then run `dpkg --configure` only on `unpacked` or `half-configured` packages that are a guard run's leftover, and it MUST NOT run `dpkg --configure` on a package while that package is `half-installed`.

Every other sentence of the paragraph stays as it is. In particular, the package step MUST still write the post-recovery `dpkg --audit` output as the run's pre-install audit record, MUST still issue `dpkg -i` only when that output is empty, MUST still complete interrupted triggers with `dpkg --triggers-only` restricted as now, MUST NOT issue `dpkg --configure -a`, and MUST NOT issue `dpkg --unpack` on any file that is not one of this run's audited `.deb` files.

## Proposal: a scenario for a publish resumed after a kill during an intended package's unpack

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add a scenario stating the observable behaviour of the amended recovery: a resumed publish re-unpacks a half-installed intended package from its audited archive and finishes with an empty `dpkg --audit`, and refuses when the half-installed package matches no audited archive of the run.

### Motivation

The behaviour the first proposal adds is load-bearing (a state transition and an error path), so per the authoring discipline it needs a Given/When/Then scenario beside the clause. It is placed immediately after §"Scenario: a Docker engine install guard publish resumed after a kill during dpkg -i completes the trigger handler that install activated", which covers the trigger-handler half of the same kill. The revise that accepts it owes the matching `tests/heading-coverage.json` entry in the same change. Measured 2026-10-17 on poweredge acceptance VMs against release v1.112.10, which contains guard child 13b (livespec-dev-tooling-mrr7ye, PR #2588). FAULTS B-06 (gate 20261017T204354Z-2505456, guard-vm-0, run r2026101720475766b8): the guard's publish unit and dpkg were SIGKILLed while `dpkg -i` unpacked docker.io; dpkg.log ends at `install docker.io:amd64 <none> 29.1.3-0ubuntu4.1` / `status half-ins

### Proposed Changes

In `SPECIFICATION/scenarios.md`, immediately after §"Scenario: a Docker engine install guard publish resumed after a kill during dpkg -i completes the trigger handler that install activated", add:

```
## Scenario: a Docker engine install guard publish resumed after a kill during an intended package's unpack re-unpacks it from its audited archive

Given a run in phase `publishing` whose audited `.deb` files include docker.io

And a kill during that run's `dpkg -i` left docker.io `half-installed` at the audited `.deb`'s version and architecture

When publish resumes for that run

Then the package step MUST run `dpkg --unpack` naming docker.io's audited `.deb` and no other file

And it MUST NOT run `dpkg --configure` on docker.io while docker.io is `half-installed`

And publish MUST finish with `dpkg --audit` empty

Given the same run, and the half-installed docker.io is at a version that no audited `.deb` of the run carries

When publish resumes for that run

Then the package step MUST refuse naming docker.io

And it MUST NOT run `dpkg --unpack` or `dpkg -i`
```
