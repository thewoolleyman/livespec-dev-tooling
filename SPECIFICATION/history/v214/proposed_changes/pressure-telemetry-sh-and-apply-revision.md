---
proposal: pressure-telemetry-sh-and-apply.md
decision: accept
revised_at: 2026-11-13T19:10:46Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as written at the dev-tooling revise slot v214, which follows v213 (livespec-dev-tooling#4544) by the order legacy-coordinator-agent set; ci-runtime-and-cost's #4527 topic follows. The spec-change tier record on livespec-dev-tooling-d5k6qc (spec v212) found the core behaviour unstated: no ratified clause keeps a credential out of a child process's argument vector, while pressure-telemetry.sh and apply-triggers.sh pass a Honeycomb key in curl's argv, readable from /proc/<pid>/cmdline on every dev-host and ci-pool host. The rule is placed in constraints.md because it governs code this repository ships for fleet members to run, where a consumer can observe a violation, and §"Execution-target pressure telemetry" names it for the PSI post. The shipped CI run-telemetry exporter already conforms; the ten members' local curl copies clear by adopting it under the existing **One CI run-telemetry exporter** requirement. Sibling items in other repositories (livespec-console-beads-fabro-zwnk3o, bd-ib-fy247q, dolt-server-kbsia2, thewoolleyman/vps-info#79) carry d5k6qc's fix shape.

## Resulting Changes

- constraints.md
- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T19:10:23Z
verdict: NO BLOCKERS
proposal_stem: pressure-telemetry-sh-and-apply
content_digest: c132b66c9ee6090734e3c00cd8150b16973c79522aa5f851c5e189a48e122aab
