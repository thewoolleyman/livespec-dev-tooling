---
proposal: gate-job-only-tests.md
decision: modify
revised_at: 2026-11-12T11:16:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The gate-Job-only rule is accepted as graded PASS-WITH-ONE-FIX by legacy-coordinator-agent (livespec-dev-tooling#4280, the fix already in the proposal): a repository declares `gate_job_only_tests` globs and the agent guard refuses a foreground pytest naming a matching module whatever its worker count, with this repository declaring its ansible-playbook-driving modules and a check keeping the declaration complete. Drafting found that the proposal amended only the **What is not refused** bullet, while the **Foreground full-suite pytest** bullet itself still says the guard MUST NOT refuse a pytest that names explicit files without `-n`, which would contradict the new rule. A pre-review doctor pass confirmed the rule is implementable from command text (`_foreground_pytest.py`) and asked for a mechanical definition of 'invokes ansible-playbook' (about 40 modules merely quote the string) and for node-id matching. The modifications add those; the independent sonnet review returned NO BLOCKERS on the exact bytes. No design record is contradicted.

## Modifications

Relative to the proposal: (1) the **Foreground full-suite pytest** bullet's own MUST NOT sentence gains the same 'matches no declared `gate_job_only_tests` glob' exception as **What is not refused**; (2) a node id matches on its path part, before `::`; (3) a module invokes `ansible-playbook` when it passes it as an argv element to a process it starts, and one that only quotes playbook text does not; (4) a spec-first note names livespec-dev-tooling-cvef23, the implementing item filed under plan dev-host-test-gate-load.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T11:15:31Z
verdict: NO BLOCKERS
proposal_stem: gate-job-only-tests
content_digest: a0eeb2f5ce4232abe10455cfa89ba2848e0bd2126ff74eaf9b4def7c6dfb62ff
