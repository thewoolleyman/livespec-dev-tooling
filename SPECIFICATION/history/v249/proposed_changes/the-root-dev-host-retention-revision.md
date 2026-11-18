---
proposal: the-root-dev-host-retention.md
decision: modify
revised_at: 2026-11-18T18:51:10Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Coordinator (legacy-coordinator-agent, R301) ruled this proposal a security guarantee: a privileged unit must not execute or resolve code through a tree a non-root account can write. That is genuine spec scope per the spec-scope criteria (https://github.com/livespec-ai/livespec/blob/master/.ai/spec-scope-criteria.md). The general paragraph is ratified as proposed. The retention-specific paragraph and scenarios are modified (see Modifications) because the first independent review blocked the filed text: it let the root retention script execute gate-run.sh from a checkout owned by the retention user (ubuntu), which contradicts the general paragraph. The coordinator chose fix (b) over fix (a), dropping privileges to the retention user, because (a) would need an exception to the general MUST NOT and would leave an ubuntu-plantable path under the same retention user. A fresh independent sonnet review of the final bytes returned NO BLOCKERS. Its two non-blocking notes go to the owning item livespec-dev-tooling-jm2tkj: root-run deletion under a user-writable tmp/gate-runs should not follow symlinks, and the uv-cache prune binary's path is worth clarifying.

## Modifications

The retention-specific paragraph now requires the root retention unit to execute only a root-owned, non-group/other-writable copy of the gate-run listing code, installed by provisioning at a fixed root-owned path, and never gate-run.sh or any file from a checkout. The allowed owner set is root only. Checkouts are read as data only, so aged terminal gate runs are still cleaned from every readable checkout including ubuntu-owned ones. A missing or non-root-writable copy makes the unit refuse to start naming the path. A named SKIP is for a checkout path that cannot be read as data, never for file ownership. The three scenarios keep their shape and are rewritten to match: refuse when the root copy is absent or unsafe; never executes anything from a checkout; still cleans from every readable checkout.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-18T18:50:34Z
verdict: NO BLOCKERS
proposal_stem: the-root-dev-host-retention
content_digest: 20322a8682d069b22261b5afa67e6cbc82ce291afe213fd46f1f55f0e68b87f9
