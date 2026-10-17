---
topic: docker-engine-guard-trigger-handlers
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-17T13:33:09Z
---

## Proposal: the package fence completes the trigger handlers its own interrupted install activated

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Amend the Package fence paragraph of §"Docker engine install guard" so that a trigger handler the guard's own `dpkg -i` activated, such as man-db, is the guard's to finish, attributed through an empty pre-install `dpkg --audit` record and dpkg's own log, while any other pending package still refuses and `dpkg --configure -a` is never issued.

### Motivation

Measured 2026-10-17 13:00Z, FAULTS case B-06 on poweredge guard-vm-7, run r20261017125530c8e7: the guard's publish unit and dpkg were SIGKILLed while `dpkg -i` ran. containerd, runc and docker.io all ended settled, but man-db was left half-configured, because its trigger had been activated by this install's own man pages and the kill interrupted it, so `dpkg --audit` named man-db. recover from `publishing` resumed publish, which reported the inert install published with dpkg still interrupted, because the settled-packages return skipped the audit; on a real host that blocks apt and unattended-upgrades until someone runs `dpkg --configure -a` by hand. livespec-dev-tooling-2v3hxz (in flight) makes that path refuse naming man-db, which is what the Package fence paragraph as ratified in v071 requires: man-db is in no recorded intended set. That refusal is honest but strands the run, and FAULTS R-06 ('the next run is not stranded; the next publish handles the non-empty dpkg --audit') and M-04 ('the next publish completes it inside the fence') both require the opposite; they stay unmet until this proposal is ratified. The design already allows it: docs/docker-engine-guard-design.md G7 completes interrupted trigger processing 'on this run's packages, or on the handlers they activate, systemd and man-db being the measured ones', and F6 requires a fresh transaction to start from an empty `dpkg --audit`. v071 ratified only the intended-set half. The attribution rule here is what turns G7's 'handlers they activate' into a test the step can run: an empty pre-install audit proves the guard's `dpkg -i` started on a clean database, and dpkg's log proves no other transaction has touched a package outside the guard's sets since, so anything flagged is the guard's own leftover. Implementation rider point 4 (recovery not keyed to one run id) is preserved, because the record is read across every guard run on the host.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Docker engine install guard", in the paragraph that follows the **Package fence.** refusal list (the paragraph beginning "The package step MUST run `dpkg -i` on exactly the audited `.deb` files"), replace these three sentences:

> Recovery of an interrupted install MUST run `dpkg --configure` only on `half-installed`, `unpacked` or `half-configured` packages in a guard run's recorded intended set. It MUST complete interrupted triggers with `dpkg --triggers-only`, restricted to packages in a guard run's recorded intended set, so that a rollback from `publishing` never strands a later run. The package step MUST refuse when `dpkg --audit` names a package outside every recorded intended set.

with:

> Before it issues `dpkg -i`, the package step MUST write the `dpkg --audit` output it read, after recovering any guard run's leftover packages, into the run's directory as that run's pre-install audit record, and it MUST issue `dpkg -i` only when that output is empty. A package that `dpkg --audit` names is a guard run's leftover when it is in a guard run's recorded intended set, or when the most recent pre-install audit record any guard run wrote on the host is empty and dpkg's own log (`/var/log/dpkg.log`) records no `install`, `upgrade`, `remove`, `purge` or `configure` action since that record was written on a package outside every recorded intended set. The second arm is what makes a trigger handler that the guard's own `dpkg -i` activated (man-db, libc-bin and systemd are the measured ones) the guard's to finish, while a package touched by any other transaction stays somebody else's. Recovery of an interrupted install MUST run `dpkg --configure` only on `half-installed`, `unpacked` or `half-configured` packages that are a guard run's leftover. It MUST complete interrupted triggers with `dpkg --triggers-only`, restricted to `triggers-awaited` or `triggers-pending` packages that are a guard run's leftover, so that neither a rollback from `publishing` nor a kill during `dpkg -i` strands a later run. The package step MUST NOT issue `dpkg --configure -a`. The package step MUST refuse when `dpkg --audit` names a package that is no guard run's leftover, and it MUST NOT report the audited additions installed while `dpkg --audit` names any package.

The two sentences before them ("The package step MUST run `dpkg -i` on exactly the audited `.deb` files, with `DPKG_FRONTEND_LOCKED=1` in its environment. It MUST require the post-install `dpkg-query` difference to equal the audited additions.") are unchanged, and so is the refusal list above the paragraph.

## Proposal: scenario: a publish resumed after a kill during dpkg -i completes the trigger handler that install activated

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add a scenario stating the amended clause end to end, with both the completing branch and the refusing branch, as the authoring discipline requires for a load-bearing clause.

### Motivation

The defect was observable only as a run that reported published over an interrupted dpkg (B-06), and the fix's danger is the opposite direction, adopting somebody else's transaction, so both branches need a scenario of their own. The revise pass that ratifies this adds the matching `tests/heading-coverage.json` entry.

### Proposed Changes

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after `## Scenario: the Docker engine install guard's recover resumes an interrupted publish and rolls back any other uncommitted run`:

## Scenario: a Docker engine install guard publish resumed after a kill during dpkg -i completes the trigger handler that install activated

Given a run in phase `publishing` whose pre-install audit record is empty and is the most recent one any guard run wrote

And a kill during that run's `dpkg -i` left man-db, which is in no recorded intended set, `half-configured` or `triggers-pending`

And dpkg's log records no `install`, `upgrade`, `remove`, `purge` or `configure` action on a package outside every recorded intended set since that record was written

When publish resumes for that run

Then the package step MUST complete man-db with `dpkg --configure` or `dpkg --triggers-only` named on man-db

And it MUST NOT issue `dpkg --configure -a`

And publish MUST NOT report the inert install published while `dpkg --audit` names any package

Given the same run, and dpkg's log records an `install` action on a package outside every recorded intended set since that record was written

When publish resumes for that run

Then the package step MUST refuse naming man-db

And it MUST NOT run `dpkg --configure` or `dpkg --triggers-only` on man-db
