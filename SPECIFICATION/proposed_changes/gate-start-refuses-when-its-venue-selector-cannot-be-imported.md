---
topic: gate-start-refuses-when-its-venue-selector-cannot-be-imported
author: claude:dev-host-test-gate-load
created_at: 2026-11-05T08:14:00Z
---

## Proposal: gate-start refuses by name when its venue selector cannot be imported

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a **Venue selector unavailable.** bullet to contracts.md §"Delegated gate-runner runs". When gate-start cannot import the venue selector through the project environment or python3, it refuses before starting a gate, writes no run record, and names the selector, each interpreter it tried, and the remedy. It exits with a code other than 70, and keeps the selector's stderr when the selector runs but returns no venue. One scenario states the behaviour.

### Motivation

On 2026-11-05 at about 07:10Z, `just gate-start` in the livespec-driver-codex primary checkout exited 70 with only "gate venue selection did not return a venue and reason". The checkout's venv was fine. Its gitignored dev-tooling/gate-run.sh was a stale pack copy calling bare python3, which under `just` resolves to /usr/bin/python3 without the venv. Refreshing the pack fixed that checkout. But the current canonical gate-run.sh still ends in the same generic EX_SOFTWARE 70 when both interpreters fail, and it discards the `uv run` stderr. EX_SOFTWARE 70 is the runner-fault code that §"Detached gate runner" Launch already uses, so a seat cannot tell a missing selector from a runner fault, and nothing names the remedy. The carrier is livespec-dev-tooling-p3mhfh, held at pending-approval. legacy-coordinator-agent ruled under R301 on 2026-11-05 that a named refusal with a distinct exit code is new contract behaviour that needs this propose-change.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated gate-runner runs", insert after the **Explicit local choice.** bullet:

- **Venue selector unavailable.** Before it chooses a venue, `gate-start` imports the venue selector shipped in `livespec_dev_tooling`, first through the checkout's project environment and then through `python3`. When neither interpreter can import it, `gate-start` MUST refuse before starting any gate and MUST write no run record. The refusal MUST name the venue selector and each interpreter it tried. It MUST name the remedy: sync or bootstrap that checkout's project environment, or refresh the worktree pack with `just install-worktree-pack` when the installed pack is older than the pinned package. It MUST exit with a code other than `70`, so a caller can tell a missing selector from a runner fault. When the selector runs but does not return a venue and a reason, the error MUST carry the selector's own standard error and MUST NOT discard it.

In SPECIFICATION/scenarios.md, add after §"Scenario: a delegated gate-runner run with no cluster verdict ends without a verdict":

## Scenario: a gate-start whose venue selector cannot be imported refuses by name

Given a checkout whose project environment and `python3` both fail to import `livespec_dev_tooling`

When a seat runs `just gate-start -- true` in that checkout

Then `gate-start` MUST start no gate and write no run record

And it MUST print a refusal naming the venue selector, each interpreter it tried and the remedy

And it MUST exit with a code other than `70`

The revise that accepts this proposal MUST add the new `## Scenario:` heading to tests/heading-coverage.json in the same commit.
