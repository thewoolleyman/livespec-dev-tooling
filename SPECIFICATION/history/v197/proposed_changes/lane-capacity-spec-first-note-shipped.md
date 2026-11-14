---
topic: lane-capacity-spec-first-note-shipped
author: claude-opus-5-5
created_at: 2026-11-11T20:36:11Z
---

## Proposal: The Declared gate resources spec-first note names Lane capacity as shipped

### Target specification files

- SPECIFICATION/contracts.md

### Summary

In contracts.md §"Delegated pre-push gate" **Declared gate resources**, the *Spec-first* sub-bullet still says "*Lane capacity* remains spec-first, and work item livespec-dev-tooling-yznwz7 owns it. A revise that ratifies Lane capacity's implementation MUST update this note." That stopped being true when livespec-dev-tooling-yznwz7 merged as livespec-dev-tooling#4199. This proposal rewrites the note to name the work item and pull request that implement Lane capacity, and the work item that owns its scenario-tier tests.

### Motivation

livespec-dev-tooling-yznwz7 merged as livespec-dev-tooling#4199 (e8908b3e6) on 2026-11-11. A declaration of `gate_cpu` or `gate_memory` that no single committed `gates-cq` flavor can admit is now refused as a declaration refusal, naming the largest lane. The refusal compares the effective request by quantity value and reads the queue file from the renderer's source. It parses with the vendored `livespec_yaml`, and the wheel packages `cluster-queue-gates.yaml` at `livespec_dev_tooling/gates/`. A note that still calls this spec-first misleads the next revise about what is still owed. The note itself says a revise ratifying Lane capacity's implementation MUST update it. The gate-resource scenarios still owe tests.consumer-tier tests, and livespec-dev-tooling-4g7als owns them (livespec-dev-tooling#4181). legacy-coordinator-agent asked for this follow-up when grading #4199.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", **Declared gate resources**, the *Spec-first* sub-bullet, replace the sentences "*Lane capacity* remains spec-first, and work item livespec-dev-tooling-yznwz7 owns it. A revise that ratifies Lane capacity's implementation MUST update this note." with: "*Lane capacity* is implemented by livespec-dev-tooling-yznwz7 (livespec-dev-tooling#4199). Work item livespec-dev-tooling-4g7als owns the consumer-tier tests of the gate-resource scenarios." The sub-bullet's first sentence, which names c3nd2h (#4148), is unchanged. No other text changes, and no heading is added, renamed or removed.
