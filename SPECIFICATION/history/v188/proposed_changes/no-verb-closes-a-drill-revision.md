---
proposal: no-verb-closes-a-drill.md
decision: modify
revised_at: 2026-11-11T05:04:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance for work item livespec-dev-tooling-io6hyk (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub). It settles both spec decisions the item raised. (1) The drill-close verb belongs to the implementation orchestrator's incident transition, whose owning spec governs the incident phase table; no surface this repository owns writes the phase. (2) A drill ends in a distinct terminal phase, drill-closed, never in closed, so a drill closure never counts as a completed incident, a completed repayment, or recovery capability for master. This repository contributes the scratch-branch boundary, keyed on forge evidence rather than a label: at least one bound carrier pull request, every carrier bound, every bound pull request's base branch matching incident-scratch/**, and no landed commit reachable from master. The four live drills (feh3s4, lli7hc, sdxw2v, wxeybc, whose PRs #4052, #4054, #4058 and #4062 all merged into incident-scratch/thhgeg-proof) qualify. A master incident is refused with incident-not-a-recorded-drill, and one with no bound PR yet is refused by the at-least-one clause. Independent sonnet ratification review (2026-11-11T04:03:42Z) returned NO BLOCKERS on these exact bytes. Its first pass found three low-severity wording gaps; this decision applies them.

## Modifications

Against the filed text, two sentences of the inserted contracts.md paragraph change. (1) 'Its owning spec governs the terminal incident phase drill-closed, the drill-close verb that writes it, and that verb's fencing, and this repository's contract with that verb is the scratch-branch boundary below.' now reads '... Its owning spec MUST govern ... is the scratch-branch boundary stated here.' The orchestrator's ratified spec does not yet carry the phase, so the sentence states a requirement rather than a present fact. (2) 'A drill MUST end in drill-closed and never in closed.' gains ', and a drill-closed item owes no repayment', which makes the paragraph match the scenario's 'with no repayment owed'. The scenario is as filed. The orchestrator's companion proposal and work item (the drill-closed phase row, the drill-close verb, and its carve-out from 'only the incident transition may establish these phases') are owed after this revise and are tracked by plan dh3hub.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T04:03:42Z
verdict: NO BLOCKERS
proposal_stem: no-verb-closes-a-drill
content_digest: 46e26cdf4d3ecec8893d285986db3bf197df18c132d3f226dbd03e44d9033be9
