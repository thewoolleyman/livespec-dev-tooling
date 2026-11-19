---
topic: factory-workspace-sweep-safety-guarantees
author: ci-runtime-and-cost-session
created_at: 2026-11-19T18:44:17Z
---

## Proposal: factory-workspace-sweep-safety-guarantees

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Section "Fabro factory host provisioning" gains one clause stating the safety guarantees of the factory-host workspace sweep, and scenarios.md gains the scenario that exercises it.

### Motivation

Measured 2026-11-19: poweredge-xubuntu held DiskPressure from filling root with ended runs' workspaces (livespec-dev-tooling-u5efoi, livespec-dev-tooling-3q3xma). The root fix, livespec-dev-tooling-iwvy4u, adds a controller-manifest-driven reaper that removes directories. Removal of a workspace destroys work that may exist nowhere else, so its never-remove, archive-first and report-only-default rules are safety guarantees (legacy-coordinator-agent ruling, 2026-11-19, under the 2026-11-16 criteria). No ratified clause states them: grep of origin/master SPECIFICATION found `contracts.md` line 18 (worktree-reap, a different object) and the pending ended-run-factory-sandbox-pod-reaper proposal (sandbox pods, not workspace directories). iwvy4u is blocked until this is ratified; the manifest generator, timer and per-host free-space target stay internal tooling and need no clause. In-flight survey: 50 open PRs, none touches the workspace sweep; alignment: no conflict.

### Proposed Changes

Two edits.

(1) SPECIFICATION/non-functional-requirements.md, section "Fabro factory host provisioning": append, after the last existing clause of the section, this paragraph verbatim:

> **A factory host's workspace sweep never removes work it cannot prove is finished and preserved.** This clause governs every sweep this repository provisions over `/srv/factory-workspaces` on a Fabro factory host, the directories where sandbox runs keep their checkouts. The sweep MUST NOT remove a workspace directory in any of these cases: the work item the directory belongs to is `blocked`, `needs-human` or in acceptance, read from the item's live ledger state at run time; the tenant that holds the item cannot be read; the directory's run has no recorded end time; or the directory is under 24 hours old. The sweep MUST archive a directory whose tree is dirty, or whose HEAD is on no origin ref, as a file with a verified sha256, and MUST record the archive's path and digest on the item before it removes the directory. A digest that does not verify MUST stop the removal of that directory. The sweep MUST default to report-only: it MUST remove and archive nothing unless apply mode is set explicitly, and in report-only mode it MUST report every directory it would have removed or archived. The sweep MUST stop removing directories once the root filesystem reaches its configured free-space target. A rule that blocks removal protects work no later run can recreate, so an unreadable input is treated as a reason to keep the directory, never to remove it.

(2) SPECIFICATION/scenarios.md: append this scenario verbatim after the last existing scenario:

## Scenario: a factory workspace sweep keeps what it cannot prove finished and preserved

Given a factory host whose `/srv/factory-workspaces` holds a directory of a blocked item, a directory whose tenant cannot be read, a directory under 24 hours old, and a dirty directory of a finished item

When the workspace sweep runs in apply mode

Then it removes none of the first three directories

And it archives the dirty directory with a verified sha256 and records the path and digest on the item before removing it

And a run in report-only mode removes and archives nothing

HEADING COVERAGE: no `## ` heading is added to a spec file other than the one scenario heading above, so the revise owes one `tests/heading-coverage.json` row for "## Scenario: a factory workspace sweep keeps what it cannot prove finished and preserved", a spec-first `"test": "TODO"` row naming the integration tier and `livespec-dev-tooling-iwvy4u` as its `work_item`, plus the regenerated `tests/heading-coverage-debt.json`.
