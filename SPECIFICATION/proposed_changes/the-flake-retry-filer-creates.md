---
topic: the-flake-retry-filer-creates
author: claude-opus-5-5
created_at: 2026-11-12T02:23:04Z
---

## Proposal: A root-fix item the flake reader files is routed through intake

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend the Untouched-test retry rule for the host-side flake reader. A root-fix work item the reader files MUST be routed through intake like any captured item, naming an open claim token where the tenant commits claim tokens. When intake refuses the routing, the reader's pass MUST exit non-zero naming the item id and the refusal text, and the reader's next pass MUST route that item again, not treat its retry record as accounted for. Add a scenario for the refused-routing path.

### Motivation

livespec-dev-tooling-5bbk5n measured the reader creating each root-fix item with a raw bd create that named no claim token. Intake refused it, the item stayed unrouted in backlog, and the reader had already marked its retry record as filed, so the root fix the rule promises never reached a factory and nothing reported the loss. The ratified text says only that the reader MUST file one root-fix work item per node id, and none for a node id that already has an open one. On 2026-11-12 the spec-change tier judge, on orchestrator v0.320.0, classified 5bbk5n as spec-change tier (verdict unstated, topic the-flake-retry-filer-creates) and it was merge-held. This proposal states the routing and refusal behaviour 5bbk5n implements.

### Proposed Changes

In non-functional-requirements.md, section "## Testing approach", bullet "Untouched-test retry", replace the sentence "A host-side reader of those records MUST file one root-fix work item per node id at once, and none for a node id that already has an open root-fix item." with:

"A host-side reader of those records MUST file one root-fix work item per node id at once, and none for a node id that already has an open root-fix item. The reader MUST route each item it files through the work-item store's intake gate, exactly as a captured work item is routed, and where the tenant commits claim tokens the filed item MUST name an open claim token, so the item rests in the status intake routes it to and never stays unrouted. When intake refuses that routing, the reader's pass MUST exit non-zero and its log MUST name the item id and the refusal text the intake gate returned. The reader MUST NOT treat a node id's retry record as accounted for until its root-fix item has been routed, so its next pass MUST route that item again rather than filing a second item for the same node id."

In scenarios.md, add this scenario directly after "## Scenario: every retried failure files one root-fix work item":

## Scenario: a root-fix item whose intake routing is refused is routed again on the reader's next pass

Given `tmp/flake-retries/` holds a record for one node id that has no open root-fix work item

And the work-item store's intake gate refuses the first routing of the item the reader files for it

When the host-side flake reader runs

Then its pass MUST exit non-zero, and its log MUST name the filed item's id and the refusal text

And when the reader runs again with the intake gate accepting, it MUST route that same item and MUST NOT file a second root-fix item for the node id
