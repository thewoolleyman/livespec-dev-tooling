---
topic: incident-fleet-audit-hardening-paginate
author: claude-opus-5-5
created_at: 2026-11-12T14:20:00Z
---

## Proposal: The incident fleet audit never reads a possibly truncated forge list as complete, and runs its interpreter isolated

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds two sentences to the fleet-audit paragraph of contracts.md, the one that begins "The fleet audit MUST be runnable". The first says every list read the audit's evidence readers take from the forge either follows pagination to its last page or counts as unverified whenever the list may be truncated. That includes the recovery-authorization reader's read of a repository's rulesets. A partial list is never read as complete. The second says the `just incident-fleet-audit` recipe runs its Python interpreter in isolated mode (`-I`). Adds one scenario after "the incident fleet audit command refuses enablement for a consumer without verified serving evidence".

### Motivation

Work item livespec-dev-tooling-evcphw (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub) was classified spec-change at dispatch on 2026-11-12 at 13:55Z, linked topic `incident-fleet-audit-hardening-paginate`. It carries two hardening findings from legacy-coordinator-agent's grade of livespec-dev-tooling#4016 (livespec-dev-tooling-3wcldx, merged e9f05024).

Finding (a). The recovery-authorization reader lists a repository's rulesets with one forge read that does not paginate. GitHub returns 30 rows per page by default. In a repository with more than 30 rulesets the reader never sees the later ones, and a ruleset it never saw could grant a bypass. The same risk applies to every list read in the incident fleet readers (`livespec_dev_tooling/fleet/` and the `incident_fleet_*` modules). The ratified paragraph comes close and stops short. It says a row whose evidence is missing or not authenticated is `unclassified`, and that "an authoritative read that is unavailable MUST count as unverified". A failed page read is covered. A read that succeeds and returns a silently truncated first page is not, because nothing says a partial list must not be read as complete.

Finding (b). The audit command's own interpreter runs without `-I`, so a module planted in the working directory or on `PYTHONPATH` could shadow one of its imports. The audit already runs the commands it invokes in a scrubbed environment (3wcldx finding F1). The ratified text says nothing about its own interpreter.

Both rules fail safe. A read that cannot prove the list complete turns a row `unclassified`, so the ready list shrinks and nothing is enabled.

### Proposed Changes

In `SPECIFICATION/contracts.md`, in the paragraph that begins "The fleet audit MUST be runnable: this repository's justfile MUST ship an operator-invoked recipe, `just incident-fleet-audit`", insert the following two sentences immediately after the sentence that ends "and an authoritative read that is unavailable MUST count as unverified." and before the sentence that begins "A row carrying serving-version evidence MUST print". No heading is added, removed or renamed in that file.

Every list those readers take from the forge, a repository's rulesets for the recovery-authorization row included, MUST either follow pagination to its last page or count as unverified whenever the list may be truncated, and a partial list MUST NOT be read as a complete one; a page read that fails or is incomplete makes the whole list unverified. The `just incident-fleet-audit` recipe MUST run the command's Python interpreter in isolated mode (`-I`), so that a module in the working directory or on `PYTHONPATH` cannot shadow one of the command's imports.

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after the scenario "the incident fleet audit command refuses enablement for a consumer without verified serving evidence" and before the scenario "a macOS developer host reads the ledger tenant through the loopback forward".

## Scenario: the incident fleet audit reads every page of a forge list or counts it unverified

```gherkin
Given livespec core's committed fleet manifest, authenticated against core's master
And one manifest consumer whose repository has more rulesets than one page of the forge's list read returns
When the operator runs `just incident-fleet-audit`
Then the recovery-authorization reader MUST read every page of that consumer's rulesets before it classifies that consumer's recovery-authorization row
And when any page of that read fails or is incomplete, that row MUST be unclassified and the ready list MUST NOT include that consumer
And a module named like one of the command's imports, placed in the working directory, MUST NOT be imported in its place.
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same commit. A spec-first `"test": "TODO"` row is acceptable when its reason names the integration tier and it carries `"work_item": "livespec-dev-tooling-evcphw"`, with the heading-coverage debt register regenerated.
