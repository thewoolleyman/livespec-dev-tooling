---
topic: a-failed-ci-telemetry-export
author: claude-opus-5-5 (seat ci-runtime-and-cost)
created_at: 2026-11-13T23:59:22Z
---

## Proposal: A failed CI telemetry export no longer fails the run it describes and is opened as one deduplicated bug

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Move the CI run-telemetry export out of the CI run it describes. A workflow triggered when a default-branch CI run completes exports that run, so the ci.run span carries the run's real conclusion and failed and cancelled runs are exported too. A failed export MUST NOT fail the CI run. Instead, a dev-host filer opens one deduplicated bug per failure key, collected by address-honeycomb-alerts. This applies the maintainer's 2026-11-13 ruling and is the behaviour livespec-dev-tooling-jgkhr5 implements.

### Motivation

Maintainer ruling, recorded in the scope event on livespec-dev-tooling-q26e3c at 2026-11-13T23:18:44Z, verbatim: "Yes, a failed telemetry export can instead be opened as a bug, via some low-cost means.  Probably a plan that collects it for now, address-honeycomb-alerts can be used for now.  Eventually we will have a dedicated seat in the radar rearchitecture to be responsible for telemetry management." Measured over 7 d to 2026-11-13T22:05Z (throughput-track-organization, GitHub GraphQL checkRuns): 17 of livespec-dev-tooling's 38 failed master CI push runs failed on the export-telemetry job ALONE, with every check job green, and 102 of 745 PRs merged under a failed master run in that window. Honeycomb held 1 failed push run in 24 h where GitHub has 17, because the exporter runs inside the run it describes, so a failed or cancelled run emits nothing and every ci.conclusion is empty. Plan ci-runtime-and-cost (epic livespec-dev-tooling-ib3oe3) carries this as throughput gap 2(a). The filer's cost is about two GitHub REST list calls per exporter repository per 30-minute pass, about 40 calls an hour for 10 repositories. It spends no CI runner-minutes and no Honeycomb queries, and it writes to the ledger only on a failure. The breakage pass (bd-ib-y3hgmv) is not reused because it dedupes per job per head commit, which would file one bug per failed run. The ratified section names no export job and states no fail-the-run rule; only the scenario below names an `export-telemetry` job, so that scenario is the text amended.

### Proposed Changes

In non-functional-requirements.md section "Runner-pool node telemetry", insert this paragraph directly after the paragraph beginning **One CI run-telemetry exporter.** (and after **Exporter failures name themselves.** when the-ci-run-telemetry-exporter is ratified with it):

> **The export runs after the run it describes, and its failure is a bug, not a red run.** A fleet member MUST export each completed CI run of its default branch from a separate workflow that starts when that run completes, and MUST NOT export from a job inside the run it describes. The exporter therefore reads a completed run: the `ci.run` span MUST carry a `ci.conclusion` equal to the conclusion GitHub reports for the run, and a run that GitHub fails or cancels MUST still be exported. A failed export MUST NOT change the conclusion of the CI run it describes. A failed export, or a completed default-branch CI run with no completed export run 60 minutes after it completed, MUST instead be opened as a bug by a dev-host filer, a timer that runs at least every 30 minutes. The filer MUST file into the livespec-orchestrator-beads-fabro ledger as type bug, with the labels `telemetry-export-failure` and `collector:address-honeycomb-alerts` and no parent edge. Each bug MUST carry the metadata key `telemetry_export_dedup_key` = `<owner>/<repo>:<workflow>:<failure-class>`, where `<failure-class>` is `export-refused` or `export-missing-60m` and no run id is part of the key. The filer MUST keep at most one open bug per key: a repeat failure under that key MUST add a comment naming the run id and run URL instead of filing a new bug, and a key whose bug is closed files a fresh one. The filer MUST read only the GitHub API, never Honeycomb, because a successful export run already proves Honeycomb accepted its spans. The collector is address-honeycomb-alerts until a dedicated telemetry seat takes the role by name.

In scenarios.md, replace the line "When that member's CI `export-telemetry` job runs" in "## Scenario: a fleet member's CI runs the CI run-telemetry exporter livespec-dev-tooling ships" with "When the workflow that starts on that member's completed default-branch CI run exports it", keeping the heading. Then add these two scenarios directly after it:

## Scenario: a failed CI telemetry export leaves the run it describes green and opens one bug

Given a completed default-branch CI run of a fleet member whose every check job succeeded

When the workflow that exports that run fails because Honeycomb refuses the spans

Then the CI run's conclusion MUST remain success

And the next pass of the dev-host filer MUST leave exactly one open bug in the livespec-orchestrator-beads-fabro ledger whose telemetry_export_dedup_key is `<owner>/<repo>:<workflow>:export-refused`

And when a later export of that member fails the same way while that bug is open, the filer MUST add one comment naming that run's id and URL to the bug and MUST file no new bug

## Scenario: a failed or cancelled CI run is exported with its real conclusion

Given a default-branch CI run of a fleet member that GitHub concluded as failure

And another that GitHub concluded as cancelled

When the workflow that starts on each completed run exports it

Then each run's `ci.run` span MUST be in the Honeycomb github-ci dataset

And each span's `ci.conclusion` MUST equal the conclusion GitHub reports for that run

The revise that ratifies this MUST add rows for both new scenario headings to tests/heading-coverage.json, owned by livespec-dev-tooling-jgkhr5, and regenerate the debt register in the revise commit.
