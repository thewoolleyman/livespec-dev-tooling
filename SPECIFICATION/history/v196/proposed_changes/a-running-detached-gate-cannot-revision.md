---
proposal: a-running-detached-gate-cannot.md
decision: modify
revised_at: 2026-11-11T21:03:27Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:fleet-flaky-tests-seat
---

## Decision and Rationale

Both proposals in this file are ratified. The first adds the `gate-stop <run-id>` verb and the `STOPPED` terminal state to contracts.md §"Detached gate runner", with two scenarios. Measured 2026-11-11 (gate 20261111T134833Z-2372296, and again 20261111T150246Z-3498800): a caller that has decided a run must not complete has no supported way to stop it. A process-group signal does not reach a lefthook-run gate client in its own session, so a push the fleet rule forbade went through. The second corrects the waiter's stated cadence to the shipped `POLL_INTERVAL_S=0.1`, and keeps the five seconds of **Idle cost.** as a return-latency ceiling. Work item livespec-dev-tooling-kjwanx owns the spec-first Stop bullet.

## Modifications

Decided after a pre-merge doctor pass walked the first draft through the code. (a) The delegated client MUST record its gate Job name in the run record at submit time, because gate_runner_delegate.py writes job_name only after a verdict and the client's cleanup_interrupted_wait holds it only in memory. gate-stop's SIGTERM lets that cleanup delete the Job, and gate-stop then confirms from the cluster that the Job is gone, also after any SIGKILL. A surviving Job is a survivor. This includes a hook-run client that submits a gate Job, and the runner MUST make the run directory available to the wrapped command's hooks. This sentence was added on legacy-coordinator-agent's grade. (b) gate-stop writes no marker for a run whose exit_code is present. The MUST NOT complete rule covers a git push or commit whose hook-run gate client had not yet returned, and the first scenario's Given says so. (c) Every state reader, gate-list and retention included, derives STOPPED from the marker. The STOPPED text MUST NOT tell the operator to re-run. (d) 'requesting identity' becomes the requesting user's name, and 'operator guidance' becomes usage text. (e) The Stop bullet notes that it rests on Stall bound's attribution, which is spec-first and owned by livespec-dev-tooling-5lhafp. (f) Fleet reach is its own bullet. (g) Consistency repairs. The opening sentence no longer names Idle cost as the only unmet requirement. Verdict exit codes names STOPPED beside DIED_WITHOUT_VERDICT for exit 75. The Agent-session gate-command guard's 'What is not refused' list names gate-stop beside the other runner verbs. (h) The scenarios sit beside the other detached gate scenarios. The waiter-cadence proposal is applied verbatim. Idle cost's stale fork note is left alone, because that proposal bars touching the Idle cost bullet.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T21:02:28Z
verdict: NO BLOCKERS
proposal_stem: a-running-detached-gate-cannot
content_digest: d35ec520ca80415521ee80c5132d2afe11b7c5e3371323b2903e784197bab8fe
