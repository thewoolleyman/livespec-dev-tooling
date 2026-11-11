---
topic: a-consumer-declares-its-gate-job-resources
author: claude:implement-test-performance
created_at: 2026-11-10T23:25:25Z
---

## Proposal: A consuming repository declares its gate Job's CPU, memory and test parallelism

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

This proposal adds a **Declared gate resources** bullet and a **Gate lane headroom** bullet to §"Delegated pre-push gate", and a **Replay Job size** bullet to §"Delegated commit-time replay test runs". It also adds sentences to the ratified **Absent verdict** bullets and to §"Delegated gate-runner runs" **Verdict and output**. A consuming repository MAY declare `gate_cpu`, `gate_memory` and `gate_parallelism` in its `[tool.livespec_dev_tooling]` table. The gate client passes each declared value to every full-size gate Job it submits: the pre-push, pre-commit aggregate, gate-runner and suite-green replay Jobs. When a key is absent, its value keeps today's default: CPU 5, `6Gi` and 4 workers. The client refuses before submission, naming the key, in two cases: a value of the wrong type or a non-positive value, and a request that no single committed gates lane can admit. That refusal refuses the commit or push and is not gated locally. Red- and Green-leg replay Jobs run one test module without xdist, so they drop to CPU 2, `3Gi` and 1 worker, and an out-of-memory kill of one is an absent verdict. The gmktec gates lane keeps room for at least three default-size gate Jobs.

### Motivation

Coordinator ruling, 2026-11-10. Every fleet repository's gate Job requests CPU 5, memory 6Gi and 4 xdist workers, because no caller of `render-gate-job.sh` passes `--cpu`, `--memory` or `--parallelism`. `gate_remote_request` (`livespec_dev_tooling/gate_remote_delegate.py` about 323-341) builds the renderer argv without them, so the renderer defaults (`render-gate-job.sh:98`) always apply. gmktec-xubuntu has 32 threads and read 80% idle at 2026-11-10 23:13Z, while the orchestrator's gate spends 2,174 s in pytest at 4 workers. The planned 8- and 12-worker wall-time measurement has to go through the normal gate client, because the fleet host guard refuses a hand `kubectl create` of a gates Job, so the client needs a declared, reviewable way to size the Job. Checking the replay path showed that Red and Green legs run one recorded test module with no `-n` (`_red_green_replay_modes.py`), so a 5-CPU request is waste there. The suite-green leg does pass `-n` with a host-chosen worker count (`_red_green_replay_suite.py` `suite_pytest_argv`), so it keeps full-size resources and its own invocation. The lane-quota refusal turns a Job that no lane could ever admit into an immediate, named refusal, instead of a 1800 s admission-bound timeout with no verdict. The ruling named only the CPU quota. This proposal applies the same refusal to memory, because an oversized memory request fails the same way. The gmktec floor follows the derivation recorded in `cluster-queue-gates.yaml`: CPU binds at 3 × 5 = 15, and memory keeps headroom above 3 × 6 = 18Gi (the file commits 24Gi). It is stated as part of the lane quota's schema, so it does not conflict with §"Tests never pin committed configuration values". The post-step doctor LLM phase (2026-11-10) confirmed several points in live code. The wheel's force-include list (`pyproject.toml` lines 88-91) does not package `cluster-queue-gates.yaml`, so this proposal adds it there. Kueue admits a Job in one flavor that covers both cpu and memory, so the lane check asks for a single flavor that satisfies both requests. Every `gate_remote_request` Failure falls back to a local run today, so the ratified **Absent verdict** bullets are amended to keep a configuration refusal loud. `_adjudicate` reads every non-Complete terminal state as `FAILED`, which would let an out-of-memory-killed Red-leg Job count as a valid Red.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "## Delegated pre-push gate", add these two bullets after the "**Declared gate check suite.**" bullet:

- **Declared gate resources.**
  - *Keys.* A consuming repository MAY declare three keys in its `[tool.livespec_dev_tooling]` table:
    - `gate_cpu` is a positive TOML integer, the gate Job container's CPU request.
    - `gate_memory` is a TOML string holding a Kubernetes memory quantity: a positive integer followed by one of the unit suffixes `Ki`, `Mi`, `Gi`, `Ti`, `k`, `M`, `G` or `T`, such as `"12Gi"`. It is the container's memory request AND its memory limit. A bare number such as `"6"` is not such a quantity.
    - `gate_parallelism` is a positive TOML integer, which the gate Job exports as `LIVESPEC_TEST_PARALLELISM`, the pytest-xdist worker count that consumer test recipes read.

    The keys are read by their own loader from the same `pyproject.toml` as `gate_check_suite`, and they are not role keys.
  - *Passing.* The gate client is `gate_remote_request` in `livespec_dev_tooling/gate_remote_delegate.py`, the single caller of `ci-runner/k3s/phase2/gates/render-gate-job.sh`. It MUST pass each declared value to the renderer's `--cpu`, `--memory` and `--parallelism` for every full-size gate Job it submits. The full-size gate Jobs are:
    - the pre-push gate Job of this section;
    - the Job of §"Delegated pre-commit aggregate";
    - the Job of §"Delegated gate-runner runs";
    - the suite-green leg Job named in §"Delegated commit-time replay test runs" **Replay Job size**.

    A key that is absent MUST leave that Job at the default the renderer carries: CPU `5`, memory `6Gi`, parallelism `4` (`render-gate-job.sh`, its defaults line).
  - *Validation.* Before it renders or submits ANY gate Job, the gate client MUST validate the three keys. It MUST refuse, with a message that names `pyproject.toml` and the key, when a declared value has the wrong type, is a non-positive integer, or is a `gate_memory` string that is not such a quantity. Wrong types include a string, a float or a boolean for `gate_cpu` or `gate_parallelism`, and a number for `gate_memory`.
  - *Lane capacity.* The gate client MUST also refuse when no single flavor of the `gates-cq` ClusterQueue has both a nominal CPU quota of at least the Job's CPU request and a nominal memory quota of at least its memory request. Kueue admits a Job in one flavor covering both resources, so such a Job could never be admitted and would only end without a verdict at the admission bound. The refusal MUST name the declared key or keys, their values, and the CPU and memory quotas of the largest lane. The flavors compared are the ones committed in `ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml`, read from the same tree the gate client reads its renderer from: this repository's in-tree copy, or the copy packaged with `livespec_dev_tooling`. The wheel MUST package that file beside its packaged renderer. A gate client that cannot read or parse the file MUST refuse in the same way, naming the file. A container-worker flavor that `converge-worker-queues.sh` enrolls at converge time is not counted.
  - *A refusal is not an absent verdict.* A validation refusal rejects the committed configuration; it is not a missing cluster verdict. The gate client MUST report it as its own failure kind, distinct from a submission failure. Under it a push MUST be refused, and a gate-runner run MUST end `FAILED`. A commit whose pre-commit aggregate or replay leg would delegate MUST be refused naming the key, and MUST NOT be gated locally in its place.
  - *Spec-first.* As of filing, no caller passes `--cpu`, `--memory` or `--parallelism`, so every gate Job in the fleet requests CPU 5, memory `6Gi` and 4 workers. The revise that ratifies this bullet MUST name the work item that owns the change.
- **Gate lane headroom.** The committed `gates-flavor` lane (gmktec-xubuntu) of `cluster-queue-gates.yaml` MUST keep a nominal quota of at least three default-size gate Jobs, at least 15 CPU and at least 18Gi memory, so that it admits at least three concurrent default-size gate Jobs. This floor is part of the schema that the lane's quota must satisfy under §"Tests never pin committed configuration values". The tests of that file MUST fail, naming the lane, when its committed quota is below three times the renderer's default request. They assert that derivation, never a literal quota. A repository's declared resources MAY lower how many of ITS Jobs the lane admits at once. They MUST NOT be met by lowering that lane's quota below this floor.

In `SPECIFICATION/contracts.md`, section "## Delegated commit-time replay test runs", add this bullet after the "**What the Job runs.**" bullet:

- **Replay Job size.** A Red-leg or Green-leg replay Job runs one recorded test module with no pytest-xdist worker count. It MUST request CPU `2` and memory `3Gi` (request and limit) and export `LIVESPEC_TEST_PARALLELISM` as `1`. The keys of §"Delegated pre-push gate" **Declared gate resources** MUST NOT change that size. A Red-leg or Green-leg replay Job that ends OOMKilled or evicted MUST be treated as an absent verdict, not as a failed run, so a resource kill can never pass as a Red. A suite-green leg Job runs pytest-xdist with the `-n` worker count that the replay gate selected on the committing host. It MUST request the declared `gate_cpu` and `gate_memory`, or the defaults when they are absent, as a full-size gate Job does. Its pytest invocation, including that `-n`, MUST stay the replay gate's own invocation, as **What the Job runs** requires. The `LIVESPEC_TEST_PARALLELISM` value such a Job exports is therefore inert, because its `-n` governs. This bullet is spec-first: as of filing, every replay Job requests CPU 5 and memory `6Gi`, and the client reads every terminal state other than Complete as a failed run.

In `SPECIFICATION/contracts.md`, section "## Delegated commit-time replay test runs", append this sentence to the "**Absent verdict.**" bullet:

A refusal under §"Delegated pre-push gate" **Declared gate resources** is not an absent verdict: the commit is refused naming the key, and the leg is not gated locally.

In `SPECIFICATION/contracts.md`, section "## Delegated pre-commit aggregate", append this sentence to the "**Absent verdict.**" bullet:

A refusal under §"Delegated pre-push gate" **Declared gate resources** is not an absent verdict: the commit is refused naming the key, and the aggregate is not gated locally.

In `SPECIFICATION/contracts.md`, section "## Delegated gate-runner runs", append this sentence to the "**Verdict and output.**" bullet:

A refusal under §"Delegated pre-push gate" **Declared gate resources** is not a cluster that returned no verdict: it MUST end the run `FAILED`, naming the key, and MUST NOT end it `DIED_WITHOUT_VERDICT`.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a repository that declares gate_cpu 9 and gate_parallelism 8 gets a gate Job requesting 9 CPUs whose coverage run uses 8 xdist workers

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`, `gate_cpu = 9` and `gate_parallelism = 8`, and declares no `gate_memory`

And its coverage test run takes its pytest-xdist worker count from `LIVESPEC_TEST_PARALLELISM`, as this repository's `just check` does

When the gate client submits that repository's pre-push gate Job

Then the Job's container MUST request 9 CPUs and request and limit memory `6Gi`

And the Job MUST export `LIVESPEC_TEST_PARALLELISM` as `8`

And the coverage pytest run inside the Job MUST start 8 pytest-xdist workers

## Scenario: a repository that declares no gate resources keeps the default gate Job size

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and declares none of `gate_cpu`, `gate_memory` and `gate_parallelism`

When the gate client submits that repository's pre-push gate Job or its delegated pre-commit aggregate Job

Then the Job's container MUST request 5 CPUs and request and limit memory `6Gi`

And the Job MUST export `LIVESPEC_TEST_PARALLELISM` as `4`

## Scenario: a non-positive declared gate resource is refused before any gate Job is submitted

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `gate_cpu = 0`

When a push in that repository reaches the gate client on a host eligible under **Host eligibility**

Then the gate client MUST refuse before it renders or submits any gate Job

And its message MUST name `pyproject.toml` and the key `gate_cpu`

And the push MUST be refused

## Scenario: a malformed declared gate resource refuses a delegated commit instead of gating it locally

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_pre_commit = true` and `gate_memory = "6"`

When a commit's pre-commit hook would delegate its aggregate on a host eligible under **Host eligibility**

Then the gate client MUST refuse before it renders or submits any gate Job, naming `pyproject.toml` and the key `gate_memory`

And the commit MUST be refused, and the aggregate MUST NOT run on the committing host in its place

## Scenario: a declared gate resource that no single gate lane can admit is refused naming the largest lane's quotas

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `gate_cpu = 40`

And no flavor committed in `cluster-queue-gates.yaml` has a nominal CPU quota of 40 or more, and the largest lane's quotas are 15 CPU and `24Gi`

When a push in that repository reaches the gate client on a host eligible under **Host eligibility**

Then the gate client MUST refuse before it submits any gate Job

And its message MUST name the key `gate_cpu`, the declared value 40 and the largest lane's quotas 15 CPU and `24Gi`

## Scenario: a Red-leg replay Job requests the small replay size whatever the repository declares

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_commit_tests = true` and `gate_cpu = 9`

When a Red commit's replay leg runs as a gate Job

Then the Job's container MUST request 2 CPUs and request and limit memory `3Gi`

And the Job MUST export `LIVESPEC_TEST_PARALLELISM` as `1`

## Scenario: a Red-leg replay Job killed for memory is an absent verdict, not a valid Red

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_commit_tests = true`

And a Red commit whose replay leg runs as a gate Job that ends OOMKilled

When the committing host reads the Job's outcome

Then it MUST treat the outcome as an absent verdict and run the Red leg's test itself

And it MUST record the Red trailers only from that local run

## Scenario: the gmktec gate lane keeps room for three default-size gate Jobs

Given the committed `cluster-queue-gates.yaml`

When its tests run

Then they MUST fail, naming the `gates-flavor` lane, if that lane's nominal CPU quota is below three times the renderer's default CPU request or its nominal memory quota is below three times the renderer's default memory request
