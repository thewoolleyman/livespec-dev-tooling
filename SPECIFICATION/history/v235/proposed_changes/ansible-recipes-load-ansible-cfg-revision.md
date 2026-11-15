---
proposal: ansible-recipes-load-ansible-cfg.md
decision: modify
revised_at: 2026-11-15T23:25:35Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The obligation is sound and correctly placed: it governs this repository's own provisioning tree, a contributor-facing concern, beside the existing §"Host provisioning tree" obligations in non-functional-requirements.md, and it closes a measured defect (the recipes resolve no ansible.cfg, so the committed pipelining that secret-bearing stdin tasks rely on is silently off). Accepted with format modifications only; no normative content changes.

## Modifications

(1) The scenario's `## Scenario:` heading is placed above the ```gherkin fence rather than inside it, matching every other scenario in scenarios.md, so the heading is a real H2 that heading-coverage can key on. (2) Then/And steps are stated as observable outcomes ("resolves", "is", "fails") rather than BCP14 MUST, matching this file's scenario style; the MUST lives in the non-functional-requirements.md paragraph. (3) The heading-coverage link is a spec-first `test: "TODO"` row naming work_item livespec-dev-tooling-d2ysfg with an integration-tier-or-above reason, plus its heading-coverage-debt.json entry, co-committed beside the revise as v234 did (first_seen 2026-11-15), because check-ansible-recipes-load-config does not exist until d2ysfg is implemented; the existing §"Host provisioning tree" row (livespec-dev-tooling-k5q54n) is unchanged.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T23:25:08Z
verdict: NO BLOCKERS
proposal_stem: ansible-recipes-load-ansible-cfg
content_digest: 3cdb919a8a9fc4ad39fec0c629da266532e00e9afc2a353afe7d7580d73b5796
