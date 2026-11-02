---
topic: shell-pipeline-verdicts-under-pipefail
author: claude-opus-5-5
created_at: 2026-11-02T13:08:46Z
---

## Proposal: Shell script pipeline verdicts under pipefail

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an H2 `## Shell script pipeline verdicts` to non-functional-requirements.md and a matching scenario. The H2 requires every shell script this repository ships or tests that runs under `set -o pipefail` to judge a pipeline's success only from a reader that consumes its whole input. An early-exiting reader can then never turn a match into a failure through SIGPIPE, and the script gives the same verdict on input larger than a pipe buffer as on a small one.

### Motivation

On 2026-11-02 dev-tooling master went red on a flake. `printf ... | grep -q PATTERN` ran under `pipefail` in the refresh-gates/node-status/factory kubeconfig tools: `grep -q` exits on its first match, the writer's next write takes SIGPIPE, the pipeline exits 141, and pipefail turns a match into a failure. Measured: 16 failures in 3000 runs on a ~200-byte input, and certain failure past 64 KiB. PR #3121 fixed those three tools. Work item livespec-dev-tooling-ftgiu4 sweeps the remaining ~47 scripts under ansible/, ci-runner/, dev-tooling/ and scripts/. Its pre-dispatch Definition-of-Done judgement refused it because no ratified H2 states this behaviour: `## Host provisioning tree` covers playbook coverage, and `## Hooks and CI` covers hook ordering. This proposal gives the sweep, and any later shell script, a governing heading and scenario. It is a contributor-side robustness rule for this repository's own scripts, so it belongs in non-functional-requirements.md.

### Proposed Changes

1. Add to `SPECIFICATION/non-functional-requirements.md` a new H2, `## Shell script pipeline verdicts`, with this body:

Every shell script this repository ships or runs in its tests, under `ansible/`, `ci-runner/`, `dev-tooling/` and `scripts/`, that runs with `set -o pipefail` MUST judge a pipeline's success only from a reader that consumes the pipeline's whole input. A pipeline whose status the script uses MUST NOT end in a reader that can exit before its writer finishes. Such readers include `grep -q`, `grep --quiet`, `grep -m N`, `head -n N`, `head -c N` and an `awk` program that calls `exit`. Under `pipefail`, the writer's SIGPIPE (exit 141) would turn a match into a failure. Where only a membership test is wanted, the script SHOULD use a here-string (`grep -q PAT <<<"$var"`), a reader that drains its input (`grep PAT >/dev/null`), or a grouping whose status does not include the writer's. Such a script MUST give the same verdict on an input larger than a pipe buffer (64 KiB) as on a small one. A pipeline whose status the script does not use, or one that runs where `pipefail` is off, is out of scope.

2. Add to `SPECIFICATION/scenarios.md` a new scenario:

## Scenario: a pipefail script reports a match in a large input as a match

Given a shell script under `ci-runner/` that runs with `set -o pipefail` and tests whether its input contains a pattern

When the input contains the pattern near its start and is larger than 64 KiB

Then the script MUST report the pattern as present

And its verdict MUST be the same as for a 200-byte input that contains the pattern

3. The revise that accepts this proposal MUST co-edit `tests/heading-coverage.json` with entries for both new headings. Each MAY be a spec-first `TODO` naming the integration tier and livespec-dev-tooling-ftgiu4 as the owner.
