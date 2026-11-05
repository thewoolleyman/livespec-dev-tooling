---
topic: honeycomb-board-and-trigger-appliers
author: claude-opus-5-5
created_at: 2026-11-05T02:54:36Z
---

## Proposal: Board and trigger appliers report drift from the committed definitions without writing

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Give `ci-runner/observability/boards/apply-boards.sh` and `ci-runner/observability/triggers/apply-triggers.sh` a read-only drift mode. It reads every live board and trigger by name and compares each with its committed definition. For every definition that differs or is missing it names the definition and each differing field, and it exits non-zero. It never creates, updates or deletes anything. The boards and triggers then get the same drift-report contract the node collector already has through `just ansible-drift ansible/ci-pool.yml`.

### Motivation

Plan kubernetes-observability (epic livespec-dev-tooling-s2aqob) assertion 6, which was dfixhe assertion 12, requires that every board and trigger definition be converged from committed GitOps state, so that a drift report on a definition that differs from the merged configuration reports the difference. Measured 2026-11-01: both appliers converge the committed definitions idempotently by name (proved on livespec-dev-tooling-t6om4l), but neither has a read-only mode. A board or trigger edited by hand in Honeycomb is silently overwritten on the next apply, and nothing reports it beforehand. §"Runner-pool node telemetry" states a drift report only for the collector (**Converged, never hand-installed.**). Both of its **Board and triggers.** paragraphs, in that section and in §"Runner-pool workload and control-plane telemetry", say only that the definitions are "converged by their `apply-*.sh`". The implementation item livespec-dev-tooling-4vopaj is held as spec-change tier against this topic until the behaviour is stated. This proposal adds a new paragraph and leaves the existing **Board and triggers.** paragraph untouched. It therefore aligns with the pending alert-thresholds-match-packed-fleet proposal, which rewrites that paragraph's trigger list.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool node telemetry", insert this new paragraph immediately after the **Board and triggers.** paragraph and before **Failure contract.**:

"**Board and trigger drift.** `ci-runner/observability/boards/apply-boards.sh` and `ci-runner/observability/triggers/apply-triggers.sh` MUST each offer a read-only drift mode covering every definition committed beside it. That includes the definitions §"Runner-pool workload and control-plane telemetry" requires. In that mode the applier MUST read each live board or trigger of the fleet observability surface by the committed definition's name and compare the two. Fields the service assigns, such as ids, timestamps and query ids it computes, MUST be left out of the comparison. For every live definition that differs from its committed one, the applier MUST print the definition's name and each differing field or panel. A committed definition with no live counterpart of that name MUST be reported as missing. The applier MUST exit non-zero when it reports any difference or missing definition, and zero when every committed definition matches. The drift mode MUST NOT send any create, update or delete request, so a definition edited by hand is reported before the next apply overwrites it."

In `SPECIFICATION/scenarios.md`, insert this scenario immediately after `## Scenario: a silent cluster-state emitter fires its dead-man`:

"## Scenario: a hand-edited board or trigger is reported by its applier's drift mode and left unchanged

Given every committed board and trigger definition under `ci-runner/observability/` has been applied to the fleet observability surface

When one live trigger's threshold and one live board's panel are edited by hand, and a committed trigger definition's live counterpart is deleted

Then running `apply-triggers.sh` in its drift mode MUST print the edited trigger's name and its threshold field, MUST report the deleted trigger's definition as missing, and MUST exit non-zero

And running `apply-boards.sh` in its drift mode MUST print the edited board's name and the differing panel, and MUST exit non-zero

And neither run MUST send a create, update or delete request, so the hand edits are still live afterwards

And straight after a normal apply, both drift modes MUST report no difference and exit zero"

The revise commit that accepts this proposal MUST also add `tests/heading-coverage.json` entries for the new scenario heading. The entries are spec-first `TODO` rows naming the tier of the owed test and livespec-dev-tooling-4vopaj as their owner, and the commit regenerates `tests/heading-coverage-debt.json` to match. The non-functional-requirements.md change adds a paragraph, not an H2 heading, so it needs no new coverage row.
