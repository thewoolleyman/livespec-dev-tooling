---
proposal: homelab-worker-departure-safe-self.md
decision: modify
revised_at: 2026-11-13T19:47:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted with one modification on the maintainer's ruling of 2026-11-13 (scope event on livespec-dev-tooling-ko26ez): the fixed 24-hour floor for a live-load window is removed. The maintainer, verbatim: "What will another 3 hours of live load tell us that we don't already know?" and "It's a go-ahead to finish the damn plan and stop stalling." A live-load window is now a stated window with a recorded start and end during which the worker completes at least one job of each workload class it is enrolled in. The rule that a replaced agent pod ends the window is kept, and every other sentence is as proposed.

## Modifications

In the new bullet "**Stable networking agents under load.**" of non-functional-requirements.md, the words "over a live-load window of at least 24 hours during which the Node stays Ready, each count MUST NOT rise." become "over a live-load window during which the Node stays Ready, each count MUST NOT rise. A live-load window is a stated window with a recorded start and end during which the worker completes at least one job of each workload class it is enrolled in." In the new scenario of scenarios.md, the Given line "And the restart count of each of its networking agent pods is read at the start of a live-load window of at least 24 hours" becomes "And the restart count of each of its networking agent pods is read at the start of a stated live-load window with a recorded start and end, during which the worker completes at least one job of each workload class it is enrolled in". Nothing else in the proposal is changed.

A second wording change, from the doctor's LLM-driven objective pass, run on this cut on legacy-coordinator-agent's grade of livespec-dev-tooling#4562 (2026-11-13): in the same bullet, "fixed at that cause before the window is counted as proof" becomes "fixed at that cause before a later window is counted as proof", because a window in which a restart was measured is never itself counted.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T19:45:58Z
verdict: NO BLOCKERS
proposal_stem: homelab-worker-departure-safe-self
content_digest: 4e34d0fc678168ea6bf40988dbd53bd2f6e912057a8cc1d20c425e40c4eddf82
