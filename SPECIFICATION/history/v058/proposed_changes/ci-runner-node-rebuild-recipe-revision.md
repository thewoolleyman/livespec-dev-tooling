---
proposal: ci-runner-node-rebuild-recipe.md
decision: accept
revised_at: 2026-09-06T15:15:27Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5-1 (livespec plan k3s-on-gmktec-for-vps-usage session)
---

## Decision and Rationale

Accepted as filed. The section states this repository's provisioning obligation under livespec's ci-host-rebuildable-from-bare-metal property (maintainer-directed 2026-09-06, plan k3s-on-gmktec-for-vps-usage goal 0): one staged rebuild procedure whose first stage is ci-runner/k3s/phase0-bare-metal/ (the home the maintainer ruled the same day), one profile per node, re-runnable with destructive storage steps refused without explicit consent, rehearsed and recorded before trusted, hardware facts in the host record and the procedure here, backup-and-restore never the rebuild path. Independent read-only review (Fable 5.1, 2026-09-06T15:01:33Z) verified replacement-target fidelity byte-for-byte, design-record fidelity against research/002 and the 12:05Z scope event, drift sweep (no contradicting statement, no count to re-derive, no expiring claim in spec text), ratification mechanics (topic equals stem; v057 tip; no anchor overlap with the other pending proposal), and the digest, and returned NO BLOCKERS. Its ordering observation is honored: livespec's clause, which this section cites by its bold lead, ratified first. Two heading-coverage TODO entries are co-edited atomically; the scenarios.md entry names the integration tier. The tree is knowingly out of conformance with the new section until the phase0 child lands, which is the gap the entries and children livespec-ifwnqj.3/.4/.5 under livespec-sab5gn own.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-06T15:01:33Z
verdict: NO BLOCKERS
proposal_stem: ci-runner-node-rebuild-recipe
content_digest: b393c4dd097b50a6c31cb87d49c186b4d1072d79a87f84aba8007d8d9681bd4b
