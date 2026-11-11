---
topic: ci-job-spans-runner-and-shared-exporter
author: claude-opus-5-5:ci-runtime-and-cost
created_at: 2026-11-11T18:31:40Z
---

## Proposal: CI job spans carry ci.runner_name, and one shared CI run-telemetry exporter serves the fleet

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds two paragraphs to §"Runner-pool node telemetry". First: every ci.job span carries ci.runner_name from the GitHub jobs API, so a CI job joins to k8s.pod.name and then k8s.node.name. Second: the CI run-telemetry exporter is one livespec-dev-tooling module that every member's CI runs through its pin. Adds two scenarios.

### Motivation

Routed by legacy-coordinator-agent 2026-11-11 ~18:31Z and ~18:45Z (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3). The github-ci job spans carry no runner or node, so no CI job p95 can be split per node. On 2026-11-11 the poweredge budget trial's revert leg had to fall back to a fleet-wide p95 stand-in (Honeycomb query iRjvZzjgikv). An ARC runner's runner_name equals its pod name (for example livespec-dev-tooling-k3s-f96mp-runner-vbtlw), so the attribute joins to the node telemetry this section already requires. Separately, measured ~18:4xZ: all nine fleet members carry their own .github/scripts/export-ci-telemetry.sh, and the copies have DRIFTED into 8 distinct sha256 hashes, plus livespec's templates/orchestrator-plugin copy, with no shared source. So every exporter change has to be ported eight times (coordinator-duties §10). No ratified text names the exporter or the ci.job spans today, so both carriers (livespec-dev-tooling-wnwwsl and livespec-dev-tooling-5ua57h) are spec-change tier and wait on this proposal. This mirrors how shared checks already ship: the check module lives in livespec-dev-tooling and consumers run it through their pin.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Runner-pool node telemetry", insert the following two paragraphs immediately BEFORE the paragraph that begins "**Failure contract.**":

**CI job spans name their runner.** Every `ci.job.<name>` span a fleet member's CI run-telemetry exporter emits MUST carry the attribute `ci.runner_name`, equal to the `runner_name` the GitHub jobs API reports for that job, whenever that row carries one. For a job that ran on the self-hosted pool, that value is the runner pod's name, so the span joins to `k8s.pod.name` and, through §"Pod attribution", to `k8s.node.name`. A CI job's duration and queue time can then be read per node. A job whose row carries no `runner_name` MUST still have its span emitted with every other attribute it carries.

**One CI run-telemetry exporter.** The exporter that turns a CI run into a `ci.run` span and one `ci.job.<name>` span per completed job MUST be one module shipped by livespec-dev-tooling, run by every fleet member's CI through its pinned livespec-dev-tooling, with no copy of its logic in the member. A change to the spans the exporter emits therefore lands in one place and reaches a member through its ordinary pin bump.

In SPECIFICATION/scenarios.md, append these two scenarios at the end of the file:

## Scenario: a self-hosted CI job's span names its runner pod, which joins to the node that ran it

Given a fleet member's pull-request CI run whose `check-coverage` job ran on runner `livespec-dev-tooling-k3s-f96mp-runner-kv9mc`

And the runner-pool node telemetry attributes pod `livespec-dev-tooling-k3s-f96mp-runner-kv9mc` to node `poweredge-xubuntu` in that window

When the member's CI run-telemetry exporter emits that run's spans

Then the `ci.job.check-coverage` span MUST carry `ci.runner_name` equal to `livespec-dev-tooling-k3s-f96mp-runner-kv9mc`

And a query joining `ci.runner_name` to `k8s.pod.name` MUST attribute that job to `poweredge-xubuntu`

## Scenario: a fleet member's CI runs the CI run-telemetry exporter livespec-dev-tooling ships

Given a fleet member whose pinned livespec-dev-tooling ships the CI run-telemetry exporter module

When that member's CI `export-telemetry` job runs

Then it MUST emit the run's `ci.run` and `ci.job.<name>` spans by running that module

And the member's repository MUST carry no copy of the exporter's span-building logic

At revise time, tests/heading-coverage.json gains one entry per new scenario heading. Their implementation owners are livespec-dev-tooling-wnwwsl (ci.runner_name) and livespec-dev-tooling-5ua57h (the shared exporter). The per-member adoption followers are filed once 5ua57h ships in a release.
