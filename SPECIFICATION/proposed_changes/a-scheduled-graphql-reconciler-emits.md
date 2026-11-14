---
topic: a-scheduled-graphql-reconciler-emits
author: claude-opus-5-5 (kubernetes-observability)
created_at: 2026-11-14T00:28:27Z
---

## Proposal: A scheduled GraphQL reconciler emits one merged-green event per merged pull request for every fleet repository

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

ADDS the H2 section "## Merged-green throughput telemetry" to non-functional-requirements.md and five scenarios to scenarios.md. Together they state the fleet's one throughput metric, pull requests merged green per repository per hour. The section defines a merged pull request, its merge head, a verdict (a CANCELLED run is not one) and the covering run. It requires one scheduled reconciler, an ansible-converged systemd timer at most 15 minutes apart, covering the fleet's 15 named repositories, that reads GitHub through GraphQL only from a per-repository watermark. The reconciler sends exactly one `pr.merged` event per merged pull request to the Honeycomb `livespec` dataset `pr-throughput`, once its covering run has a verdict or after a 24-hour hold as unverified, with a fixed attribute set including the boolean `pr.merged_green` and `emitter`. It is the only writer of those events: the converge that starts it retires the interim writer. Its first pass reads a fixed 7-day lookback and deduplicates against events already in the dataset. Each pass reports the GraphQL points it spent, under a 1000-point hourly cap, and a dead-man trigger fires when passes stop. The board `livespec family — all activity` is carried as code with that metric as its first panel.

### Motivation

Work item livespec-dev-tooling-gaetnq, the throughput track's first deliverable (plan throughput-track-organization, livespec-dev-tooling-q26e3c), was refused at dispatch rc=5 at 2026-11-14T00:20:47Z at the spec-change tier, verdict unstated, linked topic a-scheduled-graphql-reconciler-emits. No ratified text describes the reconciler, and the nearest clause, the CI run-telemetry exporter scenario, governs a different emitter. The maintainer made throughput priority 4 on 2026-11-13 with one metric, verbatim: "THROUGHPUT AS MEASURED IN PRS PER REPO PER HOUR MERGED TO MAIN BRANCH AND PASSING AS GREEN. Reported as a table of each repo and its throughput, and with a corresponding honeycomb item for me to monitor real-time as the first item on the existing livespec board". plan/throughput-track-organization/research/003 fixes the definition and its measured basis. The exporter's `ci.run` span cannot compute the metric: its `ci.conclusion` is empty because it runs inside the run it describes, a failed or cancelled run emits nothing (1 of 17 failed livespec-dev-tooling push runs and none of 101 cancelled ones reached Honeycomb in 24 h), and it has no PR number. The headline counts the covering run, not the own-head run, because in livespec-dev-tooling 362 of 745 merge-head runs over 7 d were cancelled by a newer merge, so a strict own-run reading falls as a repository merges faster. GraphQL-only, because the REST core budget was measured at 0/5000 on 2026-11-13 21:56Z. The 15-minute interval and the 1000-point hourly cap rest on note 003's measurement of 2 to 21 points per repository for a full 7-day read. At the worst case, 15 repositories cost 315 points a pass, and four passes an hour would cost 1260, over the cap. So the cap is not met by arithmetic alone: a watermark read covers far less than 7 days, and the stop rule ends a pass before the read that would cross the cap. The dataset `pr-throughput` and event `pr.merged` match the panels already placed first on board krThv8DvcwS and the interim writer filling that dataset. The single-writer rule keeps the reconciler from double-counting against that writer. The attribute set and the `emitter` field name are the interim writer's own, so the board's existing panels need no query migration. The 24-hour hold bounds a pull request that can never get a verdict: 1password-env-wrapper has no `CI` push workflow, so every one of its pull requests is one.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, INSERT a new H2 section immediately before "## LLM-spend telemetry pricing" (that is, after the end of "## Runner-pool workload and control-plane telemetry"), with exactly this text:

## Merged-green throughput telemetry

**Scope.** This section governs the telemetry behind the fleet's throughput metric: pull requests merged to each repository's default branch and passing as green, counted per repository per hour. It is the fleet's one throughput measure, so its emitter, its event shape, its dead-man and its board panel are each stated here once.

**Definitions.** A *merged pull request* is a pull request whose `mergedAt` instant is set. A merge that lands several commits, as a rebase-merge does, MUST count once: its commits are grouped by the pull request GitHub associates with each commit. Its *merge head* is the last of those commits in the default branch's first-parent order. A *verdict* is a default-branch `CI` push run conclusion of `SUCCESS`, `FAILURE`, `TIMED_OUT` or `STARTUP_FAILURE`; every other conclusion, `CANCELLED` included, is not a verdict, because a master run cancelled by a newer merge is covered by the newer head's run. A pull request's *covering run* is the verdict-bearing default-branch `CI` push run whose head commit is the merge head or, failing that, its nearest first-parent descendant that has one. A pull request is *merged green* when its covering run concluded `SUCCESS`. Its *own-run conclusion* is the conclusion of the push run on its own merge head, whatever that conclusion is, and `NO_RUN` when that head has no `CI` push run. A run's conclusion is the conclusion of its latest attempt at the moment the pass reads it. An event already sent is never revised by a later re-run.

**One merged-green reconciler.** One reconciler, shipped from source committed in this repository, MUST emit the throughput events. It MUST run on the dev host that `ansible/dev-host.yml` selects, the fleet's Ansible control node, as a systemd timer that playbook converges, never as a hand-started loop, at an interval of at most 15 minutes. It MUST receive its GitHub and Honeycomb credentials through `/usr/local/bin/with-livespec-env.sh`, and `constraints.md`'s rule against a credential in a process's argument vector applies to it. It MUST cover every repository named in a repository list committed beside its source, and that list MUST name every fleet repository; at adoption, those are the 15 of plan/throughput-track-organization/research/003: livespec-dev-tooling, livespec-orchestrator-beads-fabro, livespec-overseer, livespec, livespec-console-beads-fabro, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-orchestrator-git-jsonl, livespec-runtime, dolt-server, homelab, hetzner-xubuntu-info, 1password-env-wrapper and openbrain. A repository that joins or leaves the fleet is added to or removed from that list. Its per-repository watermarks and its record of emitted `(repo, pr.number)` pairs are host state, persisted together under the **Host-state isolation of CLIs** bullet. A pass MUST hold an exclusive lock on that state for its whole run, so two passes never overlap.

**GraphQL only, within a budget.** The reconciler MUST make every GitHub read through the GitHub GraphQL endpoint and MUST NOT request any GitHub REST path, because the fleet's REST core budget is shared with every agent and CI caller and has been measured exhausted. It MUST NOT spend more than 1000 GraphQL points in any clock hour, a fifth of the hourly GraphQL budget. Before each GitHub read, the pass MUST stop if that read could take the clock hour's spend past the cap, or if the last response's `rateLimit.remaining` is exhausted. A stopped pass lists every repository it left unread in its `merged-green.pass` event and leaves their watermarks unchanged. Each pass MUST read from a per-repository watermark, so a pass reads only what merged at or after that repository's watermark. On its first pass for a repository, the watermark MUST be 7 days before that pass, for a repository with earlier events and for one with none alike. Before that pass sends anything, the reconciler MUST seed its record of emitted pull requests with every `repo` and `pr.number` already present as a `pr.merged` event in `pr-throughput`. That way no pull request already counted is emitted again, and none still awaiting its verdict at the cut-over is lost.

**One event per merged pull request.** For each merged pull request whose covering run has reached a verdict, the reconciler MUST send exactly one event to the Honeycomb `livespec` environment's dataset `pr-throughput`, named `pr.merged`, timestamped at the pull request's `mergedAt`, and carrying `repo`, `pr.number`, `pr.merged_at`, `git.merge_head_sha`, `ci.covering_run_id`, `ci.covering_conclusion`, `pr.own_run_conclusion`, the boolean `pr.merged_green`, the boolean `pr.merged_green_own_run` (true exactly when the own-run conclusion is `SUCCESS`), `pr.author`, the boolean `pr.is_factory`, `pr.head_ref`, `pr.open_to_merge_minutes`, and `emitter` equal to `merged-green-reconciler`. While a pull request's covering run has not reached a verdict, and for at most 24 hours after its `mergedAt`, the reconciler MUST NOT send its event and MUST NOT advance that repository's watermark past its `mergedAt`, so a later pass emits it once its verdict lands. A pull request still without a verdict 24 hours after its `mergedAt` MUST be emitted once as unverified: `ci.covering_conclusion` `NO_VERDICT`, an empty `ci.covering_run_id` and `pr.merged_green` false. The watermark MAY then advance past it. A pass that re-reads a pull request it already emitted MUST NOT emit it again: at most one event exists per `repo` and `pr.number`. The pass MUST persist a pull request's pair to the emitted record BEFORE it sends that pull request's event. It removes the pair again only when Honeycomb's response definitely did not accept the event. A crash between the two steps can therefore lose an event but can never send one twice. No process other than the reconciler MAY write `pr.merged` events to `pr-throughput`. The converge that first starts the reconciler MUST, in the same run, stop and disable any interim writer of `pr.merged` events on that host (at adoption, the throughput-track stopgap on hetzner-xubuntu, `~/.local/share/pr-throughput/emit.py`), and MUST seed the record of emitted pull requests only after that writer has stopped, so two writers never run at once.

**Each pass reports itself, and silence fires.** Each pass MUST send one event of its own to `pr-throughput`, named `merged-green.pass`, carrying the GitHub GraphQL points the pass spent (each response's `rateLimit.cost`, summed), the number of `pr.merged` events it sent, the number of those sent as unverified, the number of pull requests still held awaiting a verdict, and every repository it failed to read. A pass that fails to read a repository MUST send no `pr.merged` event for that repository and MUST leave that repository's watermark unchanged. An ungrouped dead-man trigger, committed under `ci-runner/observability/triggers/` and converged by `apply-triggers.sh`, MUST fire when no `merged-green.pass` event arrives for 45 minutes, three intervals, because a stopped reconciler otherwise reads exactly like a fleet that merged nothing. Its description MUST name the emitter path, the receiver path, the owning work item and a runbook.

**The board panel.** The Honeycomb board `livespec family — all activity` MUST be carried as code under `ci-runner/observability/boards/` and converged by `apply-boards.sh`, and its FIRST panel MUST be the count of `pr.merged` events with `pr.merged_green` true per hour, grouped by `repo`, over `pr-throughput`.

In SPECIFICATION/scenarios.md, INSERT immediately after the scenario "## Scenario: a fleet member's CI runs the CI run-telemetry exporter livespec-dev-tooling ships" these five scenarios, with exactly this text:

## Scenario: a rebase-merged pull request whose covering master run succeeded is emitted once as merged green

Given a repository's default-branch history in which one pull request landed three commits by rebase-merge

And the `CI` push run on that pull request's merge head was cancelled, and the `CI` push run on the next first-parent commit concluded `SUCCESS`

When the merged-green reconciler runs a pass over that repository

Then it MUST send exactly one `pr.merged` event for that pull request to `pr-throughput`

And that event MUST carry `pr.own_run_conclusion` `CANCELLED`, `ci.covering_conclusion` `SUCCESS`, `pr.merged_green` true, `pr.merged_green_own_run` false and `emitter` `merged-green-reconciler`

And a second pass from the watermark the first pass wrote MUST send no event for that pull request

## Scenario: a pull request whose covering master run failed is emitted as not merged green

Given a merged pull request whose covering default-branch `CI` push run concluded `FAILURE`

When the merged-green reconciler runs a pass over that repository

Then it MUST send that pull request's `pr.merged` event with `ci.covering_conclusion` `FAILURE` and `pr.merged_green` false

## Scenario: a merged pull request with no master verdict yet is held until its verdict lands

Given a merged pull request with no default-branch `CI` push run at or after its merge head that has reached a verdict

When the merged-green reconciler runs a pass over that repository

Then it MUST send no event for that pull request

And the repository's watermark MUST stay at or before that pull request's `mergedAt`

## Scenario: a merged pull request that never gets a master verdict is emitted as unverified after 24 hours

Given a merged pull request whose repository has no default-branch `CI` push run at or after its merge head that has reached a verdict

And its `mergedAt` is more than 24 hours before the pass

When the merged-green reconciler runs a pass over that repository

Then it MUST send that pull request's `pr.merged` event once, with `ci.covering_conclusion` `NO_VERDICT` and `pr.merged_green` false

And the pass's `merged-green.pass` event MUST count it as sent unverified

## Scenario: a merged-green reconciler pass reports its GraphQL cost and makes no REST request

Given recorded GitHub GraphQL responses for one pass over a repository, each carrying `rateLimit.cost`

When the merged-green reconciler runs that pass

Then it MUST send one `merged-green.pass` event carrying the sum of those costs and the number of `pr.merged` events it sent

And no request of the pass MAY go to a GitHub REST path

The revise that accepts this proposal MUST add one `tests/heading-coverage.json` entry for the new section heading and one for each of the five new scenario headings, each a spec-first `"test": "TODO"` row naming livespec-dev-tooling-gaetnq as its `work_item` and the tier its owed test runs at (the section row's reason also names livespec-dev-tooling-bgespb, which owns the board-panel paragraph), registered in `tests/heading-coverage-debt.json`. Accepting it widens livespec-dev-tooling-gaetnq's work by the interim writer's full attribute set, the `merged-green.pass` event, the first-pass lookback and seeding, the 24-hour unverified hold, the retirement of the interim writer and the dead-man trigger, so that item's Definition of Done MUST be rewritten to this text, with its References line naming the new scenarios, before it is dispatched again.
