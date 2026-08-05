---
proposal: charter-detector-importable-surface.md
decision: accept
revised_at: 2026-08-05T05:11:22Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

Accepted as proposed. The change declares an importable charter-defect detector API as a second semver-stable surface and records why it must live outside livespec_dev_tooling/checks/. Verified against shipped code rather than inherited: canonical_check_slugs() walks the live checks/ directory, so a module placed there joins the canonical set, and canonical membership obliges every consumer to wire a just-check slug and a CI matrix entry. One governed repo (homelab) carries neither a justfile nor a pyproject.toml, so it has no just-check aggregate to wire a slug into and nowhere to declare the [tool.livespec_dev_tooling] block, and could not satisfy that obligation by any means, so the placement is load-bearing. An earlier draft of this bullet said that repo had 'no Python surface at all'; the independent reviewer showed that is false read literally (it carries standalone ci/ and provision/ scripts), and the sentence was tightened to the mechanically checkable claim before ratification. The amendment follows the precedent already in the same section for livespec_dev_tooling/workflow_checks/, which sits outside checks/ for the identical mechanical reason, rather than introducing a new form. The prior 'consumers MUST NOT call internal helper modules directly' prohibition is scoped rather than weakened: the surface enumeration becomes the single test of whether an import is sanctioned. The specification requires no consumer to adopt the gate.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: manual-spawn
reviewer_model: claude-fable-5
reviewer_identity: claude-fable-5
separate_reviewer: True
read_only: True
reviewed_at: 2026-08-05T05:09:21Z
verdict: NO BLOCKERS
proposal_stem: charter-detector-importable-surface
content_digest: 7457b0e73a180d3d1b9bcf8de1283e85d91cfcc549c5cade3f92733f639a47b6
