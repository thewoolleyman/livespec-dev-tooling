---
topic: incident-authority-test-fakes-model
author: claude-opus-5-5
created_at: 2026-11-12T19:10:00Z
---

## Proposal: An incident-authority outage reads as unavailable, never as a verdict on the head, and test fakes model only the outage shapes the real reader emits

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds two sentences to contracts.md, section "Expedited incident execution", in the paragraph that begins "Repair output MUST contain a legal adjacent code/test comment". They come immediately after the sentence "Normal range readers MUST verify historical PR/head/landed provenance after the environment and label disappear."

- **First sentence.** When the incident-authority read that verification depends on fails, the reader reports the provenance as unverified because the authority is unavailable. It never reports that the head is unrecorded. The incident observer's provenance and query routes answer `unavailable` on such an outage, distinct from a refusal on the head's merits.
- **Second sentence.** A test that fakes the incident-authority reader models an outage only in a shape the real reader emits.

Adds one scenario after "incident commit provenance remains verifiable on normal master".

### Motivation

Work item livespec-dev-tooling-rmig3q (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub) was classified spec-change at dispatch at 2026-11-12T18:54:56Z (verdict unstated, linked topic `incident-authority-test-fakes-model`). The rationale says nothing ratified covers four things: authority outages, the observer answering unavailable, the range gate's wording for an outage, or the shapes test fakes must model.

**The misreport.** When the observer's authority read fails, the observer answers 403: `incident_observer_service.py` has no unavailable answer, and every refusal it returns is `403 Forbidden`. The client (`incident_ci_authority.py`) never reads the body of a non-202 answer. So the range gate (`checks/_red_green_replay_incident.py:162` on master at this filing) reports "the observer does not record this head", a semantic no about a head it never checked. This is the same class of defect as livespec-dev-tooling-qeu4cx and livespec-dev-tooling-a6wgjz.

**The fakes.** Review finding F1 on livespec-dev-tooling#4002 found a test fake that modelled an outage as exit 1. A sweep then found seven more fakes modelling shapes the real reader never emits: an invented `status: 'unavailable'`, refusal codes that do not exist, and an `OSError` the port never raises. The real reader exits 78 for every refusal, and only the refusal code separates an outage (`incident-authority-unavailable`, `-transition-unavailable`, `-genesis-unavailable`, `-filing-unavailable`, `-receipt-unavailable`, and the retryable `*-outcome-unknown` variants) from a semantic no. A lifecycle outage mid-action leaks as exit 1 with a traceback, and a client timeout is the third shape. A fake in any other shape lets a caller's outage handling pass tests while the real outage takes a different path.

Both rules fail safe. An unavailable reading is never a pass. It only stops an outage being reported as a verdict on the head.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "Expedited incident execution", in the paragraph that begins "Repair output MUST contain a legal adjacent code/test comment `EXPEDITED_INCIDENT_RESPONSE flag: <incident-item>`", insert the following two sentences immediately after the sentence "Normal range readers MUST verify historical PR/head/landed provenance after the environment and label disappear." and before the sentence that begins "Revert validates the original receipt". No heading is added, removed or renamed in that file.

When an incident-authority read that this verification depends on fails, whether through the authority reader's outage refusal (an `*-unavailable` or `*-outcome-unknown` refusal code), a lifecycle failure or a client timeout, the reader MUST report the provenance as unverified because the authority is unavailable and MUST NOT report that the head is unrecorded or its provenance invalid; the incident observer's provenance and query routes MUST answer `unavailable` on such an outage, distinctly from a refusal on the head's merits, and a client of those routes MUST read that answer as an outage. A test that fakes the incident-authority reader MUST model an outage only in a shape the real reader emits: exit 78 with one of its outage refusal codes, a lifecycle failure that exits 1 with a traceback, or a client timeout.

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after the scenario "incident commit provenance remains verifiable on normal master" and before the scenario "an expedited PR defers coverage and spec work while master runs normally".

## Scenario: an incident-authority outage reads as unavailable, never as an unrecorded head

```gherkin
Given a normal range reader verifying an incident commit's provenance through the incident observer
When the observer's incident-authority read answers exit 78 with incident-authority-unavailable
Then the observer's provenance route MUST answer unavailable, distinct from its refusal on the head's merits.
And the range reader MUST report that the authority is unavailable and the head was not checked, never that the observer does not record the head.
And the same holds when the authority read fails through a lifecycle failure or a client timeout.
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same commit. A spec-first `"test": "TODO"` row is acceptable when its reason names the integration tier and it carries `"work_item": "livespec-dev-tooling-rmig3q"`, with the heading-coverage debt register regenerated.
