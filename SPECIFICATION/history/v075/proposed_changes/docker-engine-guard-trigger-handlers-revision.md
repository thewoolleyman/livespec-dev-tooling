---
proposal: docker-engine-guard-trigger-handlers.md
decision: accept
revised_at: 2026-10-17T16:39:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:petri-factory-on-gmktec
---

## Decision and Rationale

Accepted as written on the maintainer's explicit approval (2026-10-17, in the petri-factory-on-gmktec session). The amended Package fence paragraph makes a trigger handler the guard's own interrupted dpkg -i activated (man-db, libc-bin, systemd) the guard's to finish, attributed through an empty pre-install dpkg --audit record and dpkg's own log, while any package another transaction touched still refuses and dpkg --configure -a stays forbidden. It realizes design record G7 (completing the handlers this run's packages activate) and F6 (a fresh transaction starts from an empty audit), so it does not depart from the design record. It unblocks FAULTS R-06 and M-04, which require the next publish to complete a non-empty audit inside the fence. The new scenario states both branches; its heading-coverage TODO row and debt entry are owned by livespec-dev-tooling-mrr7ye (guard child 13b). An independent read-only Fable review returned NO BLOCKERS on the exact final bytes.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-17T16:36:11Z
verdict: NO BLOCKERS
proposal_stem: docker-engine-guard-trigger-handlers
content_digest: a6898d8382607993cdd871267de0f8c0a68ba08cf6b46343eff58bf58a5513ce
