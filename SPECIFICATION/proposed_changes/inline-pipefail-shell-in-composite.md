---
topic: inline-pipefail-shell-in-composite
author: claude-opus-5-5 (seat:fleet-flaky-tests)
created_at: 2026-11-12T18:51:42Z
---

## Proposal: Shell script pipeline verdicts reach inline shell in composite actions and workflows

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend "Shell script pipeline verdicts" from shell script files to the inline shell bodies that this repository's composite actions and workflow files run under pipefail. State that under `set -e` a pipeline's exit status is used unless the pipeline is a condition or is followed by `|| true`. Add one scenario for a composite action step.

### Motivation

The ratified clause covers "every shell script this repository ships or runs in its tests, in whichever directory it lives". That reads as script files, so the inline `run:` bodies of `.github/actions/*/action.yml` and `.github/workflows/*` fall outside it, though GitHub runs a step that names `shell: bash` (directly or through `defaults.run.shell`) as `bash --noprofile --norc -eo pipefail {0}`. A step that names no shell runs on Linux as `bash -e {0}`, without pipefail, unless its body sets pipefail itself. A read-only scan on 2026-11-12, over the composite actions and workflow files of the ten fleet repositories (livespec, livespec-dev-tooling, livespec-orchestrator-beads-fabro, livespec-overseer, livespec-runtime, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-console-beads-fabro, dolt-server), found early-exiting pipeline readers under pipefail only in livespec-dev-tooling:
- `.github/actions/bump-pin-rewrite/action.yml`: `git diff --cached --raw | awk '{ print $2 }' | grep -q '^160000$'`. This is a real verdict: it guards against committing a stray gitlink, and a SIGPIPE reads as "no gitlink".
- `.github/workflows/reusable-release-dispatch.yml`: `echo "$manifest" | head -20 >&2`. Its status is used through `-e`. It sits in a failure branch that exits 1 on the next line, so on a manifest larger than a pipe buffer the SIGPIPE changes the step's exit code from 1 to 141.
- `.github/workflows/reusable-release-dispatch.yml`: `... | head -1 | awk '{print $2}' || true`. Its status is discarded, so it is out of scope.
The other nine repositories hold 1 to 6 inline early-reader sites each, none of them under pipefail today, so the clause reaches them only if they turn pipefail on. Each repository's own specification governs its own files; this proposal amends livespec-dev-tooling's.

Two of those nine state the same reader rule in their own specifications, so each needs a follow-up that copies this proposal's text once it is ratified:
- livespec-overseer carries the identical clause in its non-functional-requirements.md (around line 202, under `## Constraints`) and has 6 inline sites. Its follow-up is overseer-jzyobr.
- livespec core states the rule for a "governed shell file" whose option policy enables pipefail (its non-functional-requirements.md, around lines 623 and 627, under `### Shell and Justfile discipline`) and does not say whether an action or workflow `run:` body is such a file. It has 4 inline sites. Its follow-up is livespec-3xyody.
Both follow-ups wait for this proposal to ratify. No fix is owed in either repository today, because none of their inline sites runs under pipefail. The other seven repositories state no such rule, so they need nothing. Work item livespec-dev-tooling-ljmpht (plan fleet-flaky-tests, epic livespec-dev-tooling-zwveqp) carries the fix and the widened sweep. Its launch was refused at 18:48Z on 2026-11-12 as spec-change tier, under topic inline-pipefail-shell-in-composite. The coordinator directed this proposal.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section `## Shell script pipeline verdicts`, replace the first sentence with:

"Every shell script this repository ships or runs in its tests, in whichever directory it lives, that runs with `set -o pipefail`, and every inline shell body that one of this repository's composite actions (`.github/actions/*/action.yml`) or workflow files (`.github/workflows/*`) runs under pipefail (each called a script below), MUST judge a pipeline's success only from a reader that consumes the pipeline's whole input. An inline body runs under pipefail when its step names `shell: bash`, directly or through `defaults.run.shell`, which GitHub runs as `bash --noprofile --norc -eo pipefail {0}`, or when the body sets `pipefail` itself. A step that names no shell runs on Linux as `bash -e {0}`, which is not pipefail unless the body sets it."

Append after the sentence that begins "A pipeline whose status the script does not use":

"A pipeline's exit status is also used under `set -e`, unless the pipeline is the condition of an `if`, `while` or `until`, is negated with `!`, or is a member of an `&&` or `||` list other than its last, which includes a pipeline followed by `|| true`. Such a pipeline MUST obey the reader rule above even when nothing tests its output."

Replace the section's closing sentence, `Scenario: "a pipefail script reports a match in a large input as a match".`, with:

`Scenarios: "a pipefail script reports a match in a large input as a match" and "a composite action's pipefail step reports a match in a large input as a match".`

In `SPECIFICATION/scenarios.md`, add after `## Scenario: a pipefail script reports a match in a large input as a match`:

"## Scenario: a composite action's pipefail step reports a match in a large input as a match

Given a composite action under `.github/actions/` whose step runs with `shell: bash` and tests whether its input contains a pattern

When the input contains the pattern near its start and is larger than 64 KiB

Then the step MUST report the pattern as present

And its verdict MUST be the same as for a 200-byte input that contains the pattern"

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the revise commit, with a TODO row whose `reason` names the integration tier and work item livespec-dev-tooling-ljmpht, and which carries the explicit key `"work_item": "livespec-dev-tooling-ljmpht"`. The revise MUST also regenerate the debt register.
