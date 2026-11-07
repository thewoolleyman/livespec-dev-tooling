---
topic: shell-pipeline-verdicts-every-tracked-script
author: claude-opus-5-5
created_at: 2026-11-07T16:06:48Z
---

## Proposal: Pipeline verdicts govern every shell script, not four directories

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Remove the directory list from "## Shell script pipeline verdicts", so the rule governs every shell script this repository ships or runs in its tests, in whichever directory it lives.

### Motivation

The directory list is what let `homelab-worker/` escape. The clause and its sweep (`tests/test_pipefail_reader_sweep.py`) both named `ansible/`, `ci-runner/`, `dev-tooling/` and `scripts/`, so no gate saw the early-exiting readers added under `homelab-worker/` later. Two flakes followed from that gap: livespec-dev-tooling-nzzyli (`prove-worker.sh`), and livespec-dev-tooling-y53wpo (`approve-serving-csr.sh`), which turned master red at c48dfc52 (CI run 42384603843) and blocked every commit in this repository. The same matcher, run over every tracked shell script, found 29 such readers, all under `homelab-worker/`, and none elsewhere.

ORDER, recorded on purpose: the check went ahead of the spec. livespec-dev-tooling#3692 widened the sweep to every tracked shell script BEFORE this clause changed, on legacy-coordinator-agent's stop-the-line ruling, because master was red and the fix had to land at once. That normally reverses this repository's order, so it is named here rather than left to look like an unratified widening. It was safe because the sweep is local to this repository's tests, so it could not redden a consumer, and the same change rewrote all 29 readers, so the sweep armed against a clean tree. This revise ratifies what the sweep already enforces.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, "## Shell script pipeline verdicts", first sentence:

Before: Every shell script this repository ships or runs in its tests under `ansible/`, `ci-runner/`, `dev-tooling/` and `scripts/` that runs with `set -o pipefail` MUST judge

After: Every shell script this repository ships or runs in its tests, in whichever directory it lives, that runs with `set -o pipefail` MUST judge

The rest of the clause is unchanged. The scenario "a pipefail script reports a match in a large input as a match" stays as written: its `ci-runner/` script is one example of the rule and does not scope it.
