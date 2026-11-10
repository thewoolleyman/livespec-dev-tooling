---
topic: no-check-refuses-a-delegated
author: claude:dev-host-test-gate-load
created_at: 2026-11-09T23:43:36Z
---

## Proposal: A shared check refuses a delegated gate Job path that would run an authority member

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Admit a warn-default shared check, `delegated_job_authority_skip`, into §"Shared check inventory". For each enabled delegated path, it traces the recipe the gate Job runs and reports any route that runs a declared authority member without honouring the repository's skip variable, naming the path, the Job recipe and the member. It accepts the three measured honouring shapes and fixed lists free of authority members, and it passes a repository with nothing to judge. Its lever may be armed in a repository only once that repository passes it. A new scenario states the behaviour.

### Motivation

Work item livespec-dev-tooling-zqrg7d (plan dev-host-test-gate-load, epic livespec-dev-tooling-6vuiwe) was refused at dispatch on 2026-11-09 at 23:36:58Z as spec-change tier, held for this topic. The spec-stated judgement found the asked-for behaviour partial: the ratified text states the invariant (an authority-reading member does not run in the gate Job, §"Delegated pre-push gate" and the scenario "an authority-reading member of an opted-in push runs on the pushing host and joins the delegated verdict"), but no clause admits a check that traces the delegated Job recipe for the skip read. Nor does any clause cover its failure naming, the accepted skip-read shapes, the fixed-list pass, or the arming order. The judgement named §"Shared check inventory" as the heading to generalize. The defect class is real and silent: a 2026-11-08 static sweep of the 11 fleet repositories with a delegated path found livespec-orchestrator-beads-fabro's full pre-commit path reaching `just check-skipping <fixed list>` → dev-tooling/just-check.sh, which never reads SKIP_TARGETS. check-no-workflow-edits and check-branch-protection-alignment therefore run in the Job and fail closed on every correct tree. bd-ib-oxx6eo owns that fix. The sweep found the skip read in three shapes: a justfile `check` recipe line (livespec, the console, both drivers, driver-pi, git-jsonl, runtime, dev-tooling), a script the recipe calls (the orchestrator's pre-push), and a carried or unioned list (livespec's `SKIP_TARGETS="${SKIP_TARGETS:+$SKIP_TARGETS }..."`, livespec-overseer's LIVESPEC_CHECK_SKIP union). The arming-order clause applies this repository's "confirm the reader before you write" rule and the rop-railway-enforcement precedent: arming the check fleet-wide while bd-ib-oxx6eo is unmerged would turn the orchestrator red for a defect that already has an owner.

### Proposed Changes

Two co-edits.

1. SPECIFICATION/contracts.md, §"Shared check inventory". Insert this H3 subsection immediately before the existing "### `branch_protection_alignment` check" subsection:

```
### `delegated_job_authority_skip` check

Invocation: `python -m livespec_dev_tooling.checks.delegated_job_authority_skip`. It is a warn-default check of the `just check` aggregate, and its severity lever is `LIVESPEC_FAIL_IF_DELEGATED_JOB_RUNS_AUTHORITY_MEMBERS` (§"Gate-surface severity levers"). It protects the invariant that §"Delegated pre-push gate" and §"Delegated pre-commit aggregate" state for a member that declares it reads an authorization held outside the tree: such a member does not run in a gate Job. The delegated client keeps such a member out of the Job by naming it under the repository's own skip variable. That holds only when the recipe the Job actually runs reads that variable. A recipe that reaches the aggregate by a route that ignores it runs the member in a pod that holds no credential, where it correctly fails closed, so every correct tree reads red.

- **Scope.** For each delegated path the repository enables, the check MUST trace the recipe that path's gate Job runs, through the justfile recipes and the repository scripts it calls, to every route that reaches an aggregate running a declared authority member. The pre-commit path is enabled by `delegated_pre_commit = true`, and its Job runs `check-pre-commit-gated-tree`. The pre-push path is enabled by `delegated_gate = true`, and its Job runs the declared `gate_check_suite`, or the shared fall-through sequence when none is declared.
- **Finding.** The check MUST report a finding for each route that runs a declared authority member without honouring the repository's skip variable. The finding MUST name the delegated path, the Job recipe and the member.
- **Honouring shapes.** A route honours the skip variable when any of these holds: the justfile recipe that runs the aggregate reads it, as in a `read -ra skip_targets <<< "${SKIP_TARGETS:-}"` line; a script the recipe calls reads it and then honours the list it was given; or the route carries the list into `just check` by appending to it or unioning it with its own list. The check MUST pass each of these.
- **Fixed lists.** A route that runs only a fixed list of members, none of which is a declared authority member, MUST pass.
- **Nothing to judge.** A repository that enables no delegated path, or declares no authority member, MUST pass with no finding.
- **Arming order.** A repository MUST NOT name this check's lever in its committed lever source until its own tree passes the check. The check ships warn-default so that wiring it into a consuming repository's aggregate cannot turn red a repository whose finding already has an owner.
```

2. SPECIFICATION/scenarios.md. Insert this new H2 scenario immediately after "## Scenario: an authority-reading member of an opted-in push runs on the pushing host and joins the delegated verdict" (and before the scenario that follows it):

```
## Scenario: a delegated gate Job path that runs an authority member without honouring the skip variable is reported

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_pre_commit = true`

And a member of the repository's check set that declares it reads an authorization held outside the tree

And the recipe the delegated pre-commit Job runs reaches an aggregate that runs that member by a route that does not read the repository's skip variable

When the `delegated_job_authority_skip` check runs against the repository's tree

Then the check MUST report a finding naming the delegated pre-commit path, the Job recipe and the member

And when that route instead reads the skip variable in the justfile recipe, reads it in a script the recipe calls that honours the list, or carries it into `just check` by appending or unioning it, the check MUST report no finding for that route

And when the route runs only a fixed list of members that holds no declared authority member, the check MUST report no finding for that route
```

The new `## Scenario:` heading adds one H2, so the revise commit adds its tests/heading-coverage.json row. That row is a spec-first `test: "TODO"` naming the factory tier and `work_item: livespec-dev-tooling-zqrg7d`, and the revise commit regenerates the debt register. No other heading changes.
