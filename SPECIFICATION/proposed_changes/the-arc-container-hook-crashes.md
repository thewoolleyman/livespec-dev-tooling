---
topic: the-arc-container-hook-crashes
author: claude-opus-5-5 (ci-cache-optimization seat)
created_at: 2026-11-12T04:08:24Z
---

## Proposal: The runner container hook survives a circular job-start value and names its own job-start failure

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a clause to non-functional-requirements.md §"Runner-pool build cache tiers" and one scenario to scenarios.md. Together they require the pool's runner container hook (the fleet-patched ARC kubernetes hook every scale set selects) to complete a job's start step when a value it serializes contains a circular reference, and, when its job-start step fails for any cause, to write a line naming that cause before it exits non-zero.

### Motivation

Work item livespec-dev-tooling-ddcvyd, a child of plan ci-cache-optimization (epic livespec-dev-tooling-7zozck). livespec-dev-tooling CI run 42106043980 (release PR livespec-dev-tooling#3522) lost jobs check-lint (job 127521016775) and check-format at 2026-11-05T20:45:27Z, before any check ran. Each job log ends with `TypeError: Converting circular structure to JSON` from `/home/runner/fleet-hook/index.js`, then `Executing the custom container implementation failed`. The job failed inside the pool's own hook, and the serialization error hid whatever the hook was handling.

The ratified spec does not state this behaviour. The 0.320.0 pre-dispatch wall judged ddcvyd's asked-for behaviour unstated (refused 2026-11-12T04:03:16Z, linked topic the-arc-container-hook-crashes). The ci-cache-optimization seat agrees: **Fail-soft** covers cache faults and the **Failure contract** covers pod-lifecycle emitters, and the hook's job-start step is neither. The hook is pool infrastructure in this heading's sense: it is the runner container hook that places each checkout's git alternate onto the seeded object store (scenarios.md, the seeded-object-store scenario), built and pinned under ci-runner/k3s/phase2/container-hook/. So the obligation generalizes under §"Runner-pool build cache tiers", as the wall named.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, §"Runner-pool build cache tiers", add this paragraph directly after the **Fail-soft and kill switch.** paragraph:

> **The runner container hook names its own job-start failure.** The pool's runner container hook, the fleet-patched ARC kubernetes container hook that every scale set selects, MUST complete a job's start step when a value it serializes during that step contains a circular reference. That value may be the job-start payload it receives or an error it handles. Serializing such a value MUST NOT itself fail the job. When the hook's job-start step fails for any cause, the hook MUST write to its output, before it exits non-zero, a line naming the operation that failed and the underlying error's message, so that a job log never ends on a serialization error that hides the fault the hook was handling.

In SPECIFICATION/scenarios.md, add:

> ## Scenario: the runner container hook survives a circular job-start value and names its own job-start failure
>
> Given the pool's runner container hook bundle
> When its job-start step runs on a job-start payload that contains a circular reference
> Then the step MUST complete without a "Converting circular structure to JSON" error
> And when its job-start step fails for any cause, the hook MUST write a line naming the operation that failed and the underlying error's message before it exits non-zero

The revise that accepts this adds the scenario's heading to tests/heading-coverage.json, owned by livespec-dev-tooling-ddcvyd.
