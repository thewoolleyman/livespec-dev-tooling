---
topic: local-gate-concurrency-limit
author: claude-opus-5-5
created_at: 2026-10-24T02:24:14Z
---

## Proposal: Local gate concurrency limit

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a new H2, `## Local gate concurrency limit`, to non-functional-requirements.md immediately after `## Hooks and CI`. It lets a host set a local-gate slot limit N that bounds how many pytest sessions from fleet checkouts and worktrees run at once host-wide. It states how a waiting session behaves, how slots are released, how nested sessions are handled, that a host with no limit is unchanged, and that the limit is provisioned through a committed converge. It is marked as a stopgap until the fleet's heavy gates are delegated. Matching `## Scenario:` H2s are added to scenarios.md.

### Motivation

Measured on the local dev VPS (vmi3006760, 18 cores) at 2026-10-24 01:34Z: mpstat 95.8% busy, PSI cpu some avg60 69%, load 78. 4-5 concurrent `pytest -n 4 --cov` gate aggregates were running at about 4 cores each, from local pre-push gates, commit-msg replay runs and pre-commit aggregates across fleet worktrees. Nothing limits how many full local gates run at once on one host, so N sessions pushing at once contend instead of queueing, every gate slows, and gates are pushed toward the harness's 20-minute tool-call ceiling. Work item livespec-dev-tooling-c62xtb (filed 2026-10-14) asks for a host-wide slot limit. The maintainer approved turning it on, relayed by coordinator gitops-fleet-capacity-monitoring on 2026-10-24, in these words: "Yes go ahead and turn it on. Hopefully we won't need it much longer, right?" No ratified heading of this repository's spec governs that behavior today (`## Hooks and CI` governs hook ordering and worktree-pack installation only), so c62xtb's Definition of Done has no heading to cite. This heading supplies one. The limit is a stopgap: plan delegated-gate-fleet-rollout (epic livespec-dev-tooling-mvalxq) moves the heavy gates onto the cluster, after which the limit SHOULD be removed.

### Proposed Changes

In `non-functional-requirements.md`, insert immediately after the `## Hooks and CI` section (before `## Commit and merge discipline`):

```markdown
## Local gate concurrency limit

A host MAY set a local-gate slot limit N. The limit bounds the test runs that fleet gates execute on that host, so that concurrent sessions queue for the host instead of contending for it.

When a host's limit is set to N, at most N pytest sessions started from a fleet repository's checkout or worktree MUST run at once across all repositories and worktrees on that host, and every further such session MUST wait for a slot instead of starting. The limit MUST govern the pytest sessions run by the pre-commit check aggregate, the commit-msg replay gate, a local pre-push `just check`, and a hand-run `just check` alike.

A pytest session waiting for a slot MUST print a line naming the limit and that it is waiting, and MUST repeat that line at least once a minute while it waits. The wait MUST NOT be a busy loop: a wait of several minutes MUST add no measurable CPU load.

Waiting MUST NOT produce a verdict: a session that waited MUST run its tests once a slot frees and report their own result. A session killed while waiting MUST hold no slot. A session that holds a slot and dies, by any cause including SIGKILL, MUST free that slot without any cleanup step.

A pytest session started by another pytest session that already holds a slot MUST run without taking a second slot, so that a test suite which spawns pytest in a child process cannot deadlock against its own parent.

On a host with no slot limit set — a factory sandbox, a delegated gate pod, or any host never provisioned with one — pytest sessions MUST start exactly as they would without this section.

A host's limit MUST be provisioned through a committed converge, never set by hand, and removing that one committed setting MUST return the host to no limit.

The limit is a STOPGAP for gates that still run on a shared host. Once the fleet's heavy gates run delegated, the limit SHOULD be removed.
```

In `scenarios.md`, append the following H2 scenarios in the file's existing `## Scenario:` style:

```markdown
## Scenario: a host at its local-gate slot limit queues the next pytest session

Given a host whose local-gate slot limit is set to 2

And two pytest sessions from fleet worktrees each holding a slot

When a third pytest session starts from another fleet worktree

Then the third session MUST wait instead of running its tests

And it MUST print a line naming the limit and that it is waiting, repeated at least once a minute

And when one of the first two sessions ends, the third session MUST run its tests and report their own result

## Scenario: a slot holder that is killed frees its slot without cleanup

Given a host whose local-gate slot limit is set to 1

And one pytest session holding the only slot while another session waits

When the holding session is killed with SIGKILL

Then the waiting session MUST obtain the slot and run its tests without any cleanup step having run

## Scenario: a pytest session nested under a slot holder takes no second slot

Given a host whose local-gate slot limit is set to 1

And a pytest session holding the only slot

When a test in that session starts pytest in a child process

Then the child session MUST run without waiting for a slot

## Scenario: a host with no local-gate slot limit runs pytest sessions unchanged

Given a host with no local-gate slot limit set

When any number of pytest sessions start from fleet worktrees

Then every session MUST start immediately without waiting for a slot
```

## Proposal: Sandbox image gate toolchain

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a new H2, `## Sandbox image gate toolchain`, to non-functional-requirements.md immediately after `## Toolchain pins`. It requires the `python-rust` sandbox image and every layer atop it to carry `jq`, and more generally requires every non-Python tool a fleet consumer's gate member invokes and pins in `.mise.toml` to be present in the sandbox image that consumer's CI container pins, because a delegated gate Job runs in that image without `mise install`. A missing tool is provisioned in the image, never worked around by narrowing the delegated gate. A matching `## Scenario:` H2 is appended to scenarios.md.

### Motivation

Measured 2026-10-24 01:41-01:47Z. A cluster gate run of livespec-console-beads-fabro master 07a224f0 (Job gate-livespec-console-beads-fabro-bc28m) failed only `check-nextest`: four `console-ci-parity-check::ci_telemetry_runner_attributes` tests errored with `jq is required to run the CI telemetry exporter and is pinned in .mise.toml`. The Job runs in console's CI container image (`ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-v1.126.1`), resolved by `render-gate-job.sh` from console's ci.yml, and runs no `mise install`, so console's `.mise.toml` pin of `jq = "1.7.1"` never reaches the gate. Work item livespec-dev-tooling-jxepvj carries the fix; no ratified heading of this spec states the toolchain obligation the image owes delegated gates. Coordinator gitops-fleet-capacity-monitoring directed (2026-10-24) that the obligation be ratified beside the local gate concurrency limit, to cut VPS gate load by unblocking console's delegated gate.

### Proposed Changes

In `non-functional-requirements.md`, insert immediately after the `## Toolchain pins` section (before `## Enforcement-suite invocation`):

```markdown
## Sandbox image gate toolchain

The `python-rust` Fabro sandbox image this repository builds, and every image layer built atop it (`python-rust-agent`, `python-rust-fuzz`), MUST carry `jq` on `PATH`.

More generally, a non-Python tool that a fleet consumer's gate member invokes, and that the consumer pins in its `.mise.toml`, MUST be present on `PATH` in the sandbox image that consumer's CI container pins. A delegated gate Job runs in exactly that image and deliberately runs no `mise install`: `ci-runner/k3s/phase2/gates/render-gate-job.sh` resolves the Job's image from the consumer's own `.github/workflows/ci.yml`. A tool the image does not carry is therefore absent from the gate.

A tool missing from that image MUST be provisioned in the image. It MUST NOT be worked around by narrowing the gate on the delegated path, consistent with livespec's ratified *The set* clause (livespec v229, `non-functional-requirements.md` §"Enforcement-suite invocation", **Delegated gate execution**), under which a tool on a host's path is a host-supplied condition that never leaves a check unarmed.
```

In `scenarios.md`, append the following H2 scenario in the file's existing `## Scenario:` style:

```markdown
## Scenario: a consumer's delegated gate finds the mise-pinned tools its gate members invoke

Given a fleet consumer that pins `jq` in its `.mise.toml` and has a gate member that invokes `jq`

And a CI container that pins a `python-rust` sandbox image released by this repository

When a delegated gate Job runs that consumer's gate in that image without running `mise install`

Then `jq` MUST be found on `PATH` in the Job

And the gate member MUST run its verification rather than fail for the tool's absence
```
