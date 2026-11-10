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

Add a **Declared gate resources** bullet and a **Gate lane headroom** bullet to §"Delegated pre-push gate", and a **Replay Job size** bullet to §"Delegated commit-time replay test runs". A consuming repository MAY declare `gate_cpu`, `gate_memory` and `gate_parallelism` in its `[tool.livespec_dev_tooling]` table. The gate client passes each declared value to every full-size gate Job it submits: pre-push, pre-commit aggregate, gate-runner, and suite-green replay. Absent keys keep today's CPU 5 / `6Gi` / 4. A wrong-typed or non-positive value, or a request larger than every committed gates lane's quota, is refused before submission with a message naming the key. Red- and Green-leg replay Jobs, which run one test module without xdist, drop to CPU 2 / `3Gi` / 1. The gmktec gates lane must keep room for at least three default-size gate Jobs.

### Motivation

Coordinator ruling, 2026-11-10. Every fleet repository's gate Job requests CPU 5, memory 6Gi and 4 xdist workers, because no caller of `render-gate-job.sh` passes `--cpu`, `--memory` or `--parallelism`. `gate_remote_request` (`livespec_dev_tooling/gate_remote_delegate.py` about 323-341) builds the renderer argv without them, so the renderer defaults (`render-gate-job.sh:98`) always apply. gmktec-xubuntu has 32 threads and read 80% idle at 2026-11-10 23:13Z, while the orchestrator's gate spends 2,174 s in pytest at 4 workers. The planned 8- and 12-worker wall-time measurement has to go through the normal gate client, because the fleet host guard refuses a hand `kubectl create` of a gates Job, so the client needs a declared, reviewable way to size the Job. Checking the replay path showed that Red and Green legs run one recorded test module with no `-n` (`_red_green_replay_modes.py`), so a 5-CPU request is waste there. The suite-green leg does pass `-n` with a host-chosen worker count (`_red_green_replay_suite.py` `suite_pytest_argv`), so it keeps full-size resources and its own invocation. The lane-quota refusal turns a Job that no lane could ever admit into an immediate, named refusal, instead of a 1800 s admission-bound timeout with no verdict. The ruling named only the CPU quota. This proposal applies the same refusal to memory, because an oversized memory request fails the same way. The gmktec floor (15 CPU / 18Gi = three default Jobs) is the lane's documented derivation in `cluster-queue-gates.yaml`, stated as a derivation, not a pinned value, so it does not conflict with §"Tests never pin committed configuration values".

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "## Delegated pre-push gate", add these two bullets after the "**Declared gate check suite.**" bullet:

- **Declared gate resources.** A consuming repository MAY declare three keys in its `[tool.livespec_dev_tooling]` table. `gate_cpu` is a positive TOML integer, the gate Job container's CPU request. `gate_memory` is a TOML string holding a Kubernetes memory quantity: a positive integer followed by an optional unit suffix `Ki`, `Mi`, `Gi`, `Ti`, `k`, `M`, `G` or `T`, such as `"12Gi"`. It is used as the container's memory request AND its memory limit. `gate_parallelism` is a positive TOML integer, which the gate Job exports as `LIVESPEC_TEST_PARALLELISM`, the pytest-xdist worker count that consumer test recipes read. The keys are read by their own loader from the same `pyproject.toml` as `gate_check_suite`, and they are not role keys. The gate client is `gate_remote_request` in `livespec_dev_tooling/gate_remote_delegate.py`, the single caller of `ci-runner/k3s/phase2/gates/render-gate-job.sh`. It MUST pass each declared value to the renderer's `--cpu`, `--memory` and `--parallelism` for every full-size gate Job it submits. Those are the pre-push gate Job of this section, the Job of §"Delegated pre-commit aggregate", the Job of §"Delegated gate-runner runs", and the suite-green leg Job that §"Delegated commit-time replay test runs" **Replay Job size** names. A key that is absent MUST leave that Job at the default the renderer carries: CPU `5`, memory `6Gi`, parallelism `4` (`render-gate-job.sh`, its defaults line). Before it renders or submits ANY gate Job, the gate client MUST validate the three keys. A declared value of the wrong type, a non-positive integer, or a `gate_memory` string that is not such a quantity MUST make the client refuse, with a message that names `pyproject.toml` and the key. Wrong types include a string, a float or a boolean for `gate_cpu` or `gate_parallelism`, and a number for `gate_memory`. The client MUST also refuse in two lane cases. The first is a declared `gate_cpu` larger than the largest nominal CPU quota of any flavor of the `gates-cq` ClusterQueue. The second is a declared `gate_memory` larger than the largest nominal memory quota of any such flavor. No lane could ever admit such a Job, which would only end without a verdict at the admission bound. That refusal MUST name the key, its declared value and the largest lane quota. The flavors compared are those committed in `ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml`, read from the same tree the gate client reads its renderer from: this repository's in-tree copy, or the copy packaged with `livespec_dev_tooling`. A container-worker flavor that `converge-worker-queues.sh` enrolls at converge time is not counted. A validation refusal is a refusal of the committed configuration, not an absent cluster verdict. A push MUST be refused, and a gate-runner run MUST record `FAILED`. A commit whose pre-commit aggregate or replay leg would delegate MUST be refused naming the key, and MUST NOT be gated locally in its place. This bullet is spec-first: as of filing, no caller passes `--cpu`, `--memory` or `--parallelism`, so every gate Job in the fleet requests CPU 5, memory `6Gi` and 4 workers. The revise that ratifies it MUST name the work item that owns the change.
- **Gate lane headroom.** The committed `gates-flavor` lane (gmktec-xubuntu) of `cluster-queue-gates.yaml` MUST keep a nominal quota of at least three default-size gate Jobs, that is at least 15 CPU and at least 18Gi memory, so that it admits at least three concurrent default-size gate Jobs. The tests of that file MUST fail, naming the lane, when its committed quota is below three times the renderer's default request. They assert that derivation, never a literal quota. A repository's declared resources MAY lower how many of ITS Jobs the lane admits at once. They MUST NOT be met by lowering that lane's quota below this floor.

In `SPECIFICATION/contracts.md`, section "## Delegated commit-time replay test runs", add this bullet after the "**What the Job runs.**" bullet:

- **Replay Job size.** A Red-leg or Green-leg replay Job runs one recorded test module with no pytest-xdist worker count. It MUST request CPU `2` and memory `3Gi`, as both request and limit, and export `LIVESPEC_TEST_PARALLELISM` as `1`. The keys of §"Delegated pre-push gate" **Declared gate resources** MUST NOT change that size. A suite-green leg Job runs pytest-xdist with the `-n` worker count that the replay gate selected on the committing host. It MUST request the declared `gate_cpu` and `gate_memory`, or the defaults when they are absent, as a full-size gate Job does. Its pytest invocation, including that `-n`, MUST stay the replay gate's own invocation, as **What the Job runs** requires, so `gate_parallelism` does not change its worker count. This bullet is spec-first: as of filing, every replay Job requests CPU 5 and memory `6Gi`.

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

## Scenario: a declared gate resource larger than every gate lane is refused naming the largest lane quota

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `gate_cpu = 40`

And the largest nominal CPU quota of any flavor committed in `cluster-queue-gates.yaml` is 15

When a push in that repository reaches the gate client on a host eligible under **Host eligibility**

Then the gate client MUST refuse before it submits any gate Job

And its message MUST name the key `gate_cpu`, the declared value 40 and the largest lane quota 15

## Scenario: a Red-leg replay Job requests the small replay size whatever the repository declares

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_commit_tests = true` and `gate_cpu = 9`

When a Red commit's replay leg runs as a gate Job

Then the Job's container MUST request 2 CPUs and request and limit memory `3Gi`

And the Job MUST export `LIVESPEC_TEST_PARALLELISM` as `1`

## Scenario: the gmktec gate lane keeps room for three default-size gate Jobs

Given the committed `cluster-queue-gates.yaml`

When its tests run

Then they MUST fail, naming the `gates-flavor` lane, if that lane's nominal CPU quota is below three times the renderer's default CPU request or its nominal memory quota is below three times the renderer's default memory request

