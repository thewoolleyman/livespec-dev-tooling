---
topic: gate-job-container-sets-pytest
author: claude-opus-5-5
created_at: 2026-11-14T01:08:41Z
---

## Proposal: A gate Job's container sizes CPU-counting tools to its CPU request

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every gate Job the gate client submits must export PYTEST_XDIST_AUTO_NUM_WORKERS and OMP_NUM_THREADS. Each equals the gate container's CPU request in whole CPUs, rounded down and never below 1. The renderer must refuse a --cpu value that is not a Kubernetes CPU quantity before it prints any manifest. LIVESPEC_TEST_PARALLELISM, and an explicit pytest -n, keep governing the committed recipes. The two new variables bound only tools that size themselves from the CPU count.

### Motivation

A gate container requests CPU but sets no CPU limit (§"Delegated pre-push gate", **Declared gate resources**), so its cgroup cpu.max reads "max" and every CPU count a tool can see is the node's. Measured by the kubernetes-sandbox-backend seat on gate pod gate-livespec-dev-tooling-7j4ms on poweredge-xubuntu, 2026-11-14: the gate process saw 72 CPUs, the pod requested cpu 5 with no cpu limit, and its memory limit was 6Gi. LIVESPEC_TEST_PARALLELISM caps the committed recipes. A bare `pytest -n auto`, or a BLAS or OpenMP pool sized from the CPU count, would still start one worker per node CPU against the memory limit. That is the OOM class that killed the factory run of livespec-dev-tooling-vy75ws, 2026-11-13.

The factory sandbox pod gets the same protection in sandbox-driver-kubernetes PR #21 (bd-ib-p3g5tp). That driver sets both variables to the pod's whole-core CPU limit unless the spec already sets them. This proposal makes gate pods and factory pods size the same way. Gate Jobs use the request rather than a limit because a gate container deliberately carries no CPU limit.

The change is defensive, reversible and not urgent: no committed gate recipe runs a bare `-n auto` today. It is filed spec-first, on legacy-coordinator-agent's ruling of 2026-11-14 ~01:2xZ, ahead of the implementation in work item livespec-dev-tooling-3yj6kx (plan gate-job-resources, epic livespec-dev-tooling-ukoeah). It aligns with the in-flight proposal per-node-cpu-budget-honest-requests (livespec-dev-tooling#4565), which moves the renderer's default request. The worker count follows whatever request a Job carries, so neither proposal fixes a number the other changes.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", **Declared gate resources**, add one sub-bullet after *Passing.*:

```
  - *Worker-count environment.* Every gate Job the gate client submits, full-size or replay, MUST export `PYTEST_XDIST_AUTO_NUM_WORKERS` and `OMP_NUM_THREADS` in its gate container. Each MUST equal that container's CPU request in whole CPUs, rounded down and never below 1, so a request of `5` exports `5`, `2500m` exports `2` and `500m` exports `1`. The gate container sets no CPU limit, so a tool that sizes itself from the CPU count reads the node's CPUs rather than the Job's request. These two variables bound such tools. `LIVESPEC_TEST_PARALLELISM`, and a pytest `-n` that a Job's invocation carries, still govern the committed recipes and are not changed by this bullet. `ci-runner/k3s/phase2/gates/render-gate-job.sh` MUST refuse a `--cpu` value that is not a Kubernetes CPU quantity (a whole number, a decimal, or a whole number of millicores with the suffix `m`). It MUST exit non-zero, name the value, and print no manifest. The bullet is spec-first: as of its ratification no gate Job exports either variable, and work item livespec-dev-tooling-3yj6kx owns the change.
```

In SPECIFICATION/scenarios.md, add two scenarios immediately after `## Scenario: a repository that declares no gate resources keeps the default gate Job size`:

```
## Scenario: a gate Job that requests 9 CPUs on a 72-CPU node starts 9 workers for a bare pytest -n auto

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and `gate_cpu = 9`

And the gate Job is admitted on a node that has 72 CPUs

When the gate client submits that repository's pre-push gate Job

Then the Job's gate container MUST export `PYTEST_XDIST_AUTO_NUM_WORKERS` as `9` and `OMP_NUM_THREADS` as `9`

And a `pytest -n auto` run inside that container MUST start 9 pytest-xdist workers, not 72

## Scenario: the gate Job renderer refuses a CPU request that is not a CPU quantity

Given the gate Job renderer `ci-runner/k3s/phase2/gates/render-gate-job.sh`

When it is called with `--cpu 5x`

Then it MUST exit non-zero and name `5x`

And it MUST print no manifest
```

The revise that accepts this proposal adds both new scenario headings to `tests/heading-coverage.json` in the same commit.
