---
proposal: fleet-conformance-and-manifest-discovery.md
decision: accept
revised_at: 2026-06-12T14:42:32Z
author_human: Test <test@example.com>
author_llm: claude-fable-5
---

## Decision and Rationale

The family contract (livespec v108 §"Fleet membership contract") is hierarchically authoritative and the implementation has already landed in this repo (livespec_dev_tooling/fleet/ with contract.py, fleet_conformance, wire_fleet_member; the fleet-preflight job in reusable-release-dispatch.yml; the check-fleet-conformance just target wired into the check aggregate, CI, and the scheduled fleet-conformance.yml). The local §"Sibling discovery" still declared topic search the sole source of truth, which directly contradicts the manifest-driven family contract; this acceptance realigns the local spec while preserving the original section's surviving intent (the member list MUST NOT live in this library — it lives in livespec core). Acceptance pre-authorized by the user for this revise pass.

## Resulting Changes

- contracts.md
