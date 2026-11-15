---
topic: quiet-off-appends-its-merge
author: claude-opus-5-5 (throughput-metric)
created_at: 2026-11-15T05:55:36Z
---

## Proposal: A committed disruption-window record that QUIET OFF appends to, and the throughput board charts only clean pull requests from it

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

ADDS the H2 section "## Throughput disruption windows" to non-functional-requirements.md and two scenarios to scenarios.md. They state three things. First, the committed record ci-runner/observability/throughput/disruption-windows.json of merge-quiet and CI-pool-stall windows, plus the lead-time start-rule change. Second, the mechanical append: the actor that lifts a merge-quiet window opens a pull request appending that window, with no duplicate. Third, the throughput board's use of the record: derived columns pr.disruption and pr.lead_rule, lead-time and stage charts filtered to clean pull requests, and the excluded population counted in a table.

### Motivation

Work item livespec-dev-tooling-35iexd, the mechanical window append, was routed to the RATIFY route on 2026-11-15 by legacy-coordinator-agent. It reads spec-change tier: no ratified dev-tooling text states the quiet-off append, the disruption-windows record or the board's pr.disruption column, and "## Commit and merge discipline" covers only commit prefixes and rebase-merge. The record and columns already shipped in livespec-dev-tooling#4756 (plan throughput-metric, livespec-dev-tooling-oe7cfw). That work was maintainer-directed on 2026-11-15, after Honeycomb's Canvas agent, shown only the throughput board, read merge-quiet holds and the CI pool stall as a fleet-wide slowdown. The maintainer then ruled that confound series must not be charted beside the trend line (.ai/honeycomb-board-charts.md), so this proposal states the filtered-chart shape. throughput-plans-coordinator ruled that the append must be mechanical, done by whoever writes QUIET OFF, not a step a session has to remember. This proposal ALIGNS with two pending proposals. arm-on-green-automation-honours keeps the live per-repository merge-quiet marker; this proposal adds only the closed historical window. a-scheduled-graphql-reconciler-emits keeps the pr-throughput event shape; this proposal adds query-time derived columns over that dataset and changes no emitted field.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, INSERT a new H2 section immediately before "## LLM-spend telemetry pricing", with exactly this text. If the revise that ratifies a-scheduled-graphql-reconciler-emits lands first, insert it immediately after that proposal's "## Merged-green throughput telemetry" section instead.

## Throughput disruption windows

**Scope.** This section governs the committed record of the windows in which the fleet's pull requests were held from merging or slowed by a stalled CI pool, how a window enters that record, and how the throughput board reads it. It exists so that a reader who sees only the board can tell a held or slowed pull request from a slower pipeline.

**The record.** The record MUST be one committed file, `ci-runner/observability/throughput/disruption-windows.json`, and it MUST be the only source of disruption windows for the throughput board. Each window MUST carry a unique `id`; a `kind` of `merge-quiet` (one repository's pull requests held from merging) or `ci-pool-stall` (the shared CI pool stalled, every repository); the `repos` it applies to, or `["*"]` for every repository; its `start` and `end` as UTC instants with `start` before `end`; a label; and the ledger comment or log line that recorded each bound. The record MUST also carry the lead-time start-rule change: the date it took effect, and the event field that tells new-rule events from old-rule events. A window is distinct from a repository's merge-quiet marker. The marker is the live per-repository property that holds arming while it is present. A window is the closed historical interval written once the hold has ended.

**The append at QUIET OFF.** The actor that lifts a repository's merge-quiet window (today the quiet-off step of legacy-dispatcher-agent) MUST, in the same act, open one pull request to livespec-dev-tooling that appends that window to the record. The window MUST name the held repository, and its start and end MUST be the instants the hold began and ended. The append MUST NOT need a session to remember a separate step. When the record already holds a window with the same repository and bounds, the actor MUST NOT open a second pull request or append a duplicate. A `ci-pool-stall` window MAY be appended by hand through a pull request, naming the incident that measured it.

**The board's use of the record.** `apply-disruption-columns.sh` MUST generate, from the record alone, two derived columns on the `pr-throughput` dataset. `pr.disruption` labels a pull request with the window whose kind and repository match and whose interval overlaps the pull request's opened-to-merged life; a merge-quiet window outranks a CI-pool stall, and a pull request that overlaps no window is labelled `clean`. `pr.lead_rule` labels each event new or old start rule. `apply-boards.sh` MUST converge these columns before it applies any board, read-only under `--drift`, and MUST render the record's windows wherever a text panel carries `{{disruption-windows}}`. The throughput board's lead-time and stage charts MUST plot only the comparable population: lead time MUST be filtered to `clean` pull requests under the new start rule, and stages to `clean` pull requests. The pull requests those filters leave out MUST be counted, by `pr.disruption` and `pr.lead_rule`, in one table panel, never drawn as lines beside the trend. Adding a window to the record MUST relabel every past event at the next apply, with no board edit and no re-emission.

**Implementation.** livespec-dev-tooling-35iexd implements the append at QUIET OFF. The record, the columns and the board's filters landed in livespec-dev-tooling#4756.

In SPECIFICATION/scenarios.md, APPEND these two scenarios after "## Scenario: a hand-edited board or trigger is reported by its applier's drift mode and left unchanged":

## Scenario: lifting a merge-quiet window appends that window to the throughput disruption record

Given livespec-orchestrator-beads-fabro has been held under a merge-quiet window since 01:45:00Z

And `ci-runner/observability/throughput/disruption-windows.json` holds no window for that repository with those bounds

When the actor lifting the window posts QUIET OFF for livespec-orchestrator-beads-fabro at 03:05:55Z

Then that actor MUST, in the same act, open one pull request to livespec-dev-tooling that appends one `merge-quiet` window naming livespec-orchestrator-beads-fabro, starting at 01:45:00Z, ending at 03:05:55Z, and citing the ledger line for each bound

And when that QUIET OFF is processed a second time, the actor MUST NOT open another pull request or append a second window with the same repository and bounds

## Scenario: the throughput board labels a pull request held through a merge-quiet window and leaves it out of its charts

Given the disruption record holds a `merge-quiet` window for livespec-dev-tooling from 03:44:40Z to 07:03:17Z

And a livespec-dev-tooling pull request was opened at 05:00Z and merged green at 07:30Z

And another livespec-dev-tooling pull request was opened and merged green after 07:03:17Z, overlapping no window

When `apply-boards.sh` converges the throughput board

Then `pr.disruption` MUST label the first pull request with that window's label and the second `clean`

And the board's lead-time and stage charts MUST include the second pull request and MUST NOT include the first

And the board's table of pull requests left out of the charts MUST count the first pull request under that window's label

The revise that ratifies this MUST add rows to tests/heading-coverage.json for the new section heading and both scenario headings. The scenario rows are owned by livespec-dev-tooling-35iexd, which owes their tests (the append at the host tier, the board labelling at the consumer tier). The revise MUST also regenerate tests/heading-coverage-debt.json in the revise commit.
