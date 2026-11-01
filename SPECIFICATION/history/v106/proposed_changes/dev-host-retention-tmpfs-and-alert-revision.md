---
proposal: dev-host-retention-tmpfs-and-alert.md
decision: modify
revised_at: 2026-11-01T16:59:08Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

MODIFY. Extends non-functional-requirements.md §"Dev host disk retention" after the 2026-11-01 /tmp-full incident (tmpfs at 100% at 13:50Z broke Bash, gates and factory launches; / at 98%): one run also removes dead agent sessions' scratch directories under /tmp/claude-<uid> and aged pytest base-temp entries, restores the retention user's ownership of root-owned uv cache paths before pruning as that user (the uv leg has aborted on Permission denied since 10-21), bounds a bulk-dump directory that must not be on tmpfs, reports / and /tmp; a 15-minute capacity check alerts through the host's ntfy topic at 85% / and 75% /tmp. Two new scenarios. Modified from the proposal on the first independent review's three blockers: the scratch period is a distinct role variable; the repeat interval has a 1 h default and is listed; the ntfy topic is claude_ntfy_topic; the bulk-dump default is /var/tmp/livespec-dumps; the uv restore runs with root privilege then prunes as the retention user; liveness reads every process's environment; the /tmp scenario asserts no root notification. Spec-led, not drift-origin; no design record contradicted. Decided under delegated revise_decision_mode by seat dev-host-disk-retention on maintainer direction 2026-11-01 (work autonomously). Independent review: separately spawned read-only sonnet agent, NO BLOCKERS on these exact bytes, nits left for the implementing item: rename the existing period to gate-run retention period; state the cache owner is the retention user; split the alert paragraph; no scenarios for the root alert, dump cap, pytest and uv legs.

## Modifications

Resolved the first review's blockers: distinct scratch retention period; repeat-interval wording and 1 h default listed in HOST_VARS.md; ntfy topic = claude_ntfy_topic; bulk-dump default /var/tmp/livespec-dumps on the root filesystem; uv ownership restore under root privilege then prune as the configured retention user; liveness check reads every process's environment; /tmp alert scenario asserts no root-filesystem notification.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-01T16:59:05Z
verdict: NO BLOCKERS
proposal_stem: dev-host-retention-tmpfs-and-alert
content_digest: deaa45d47e6c16cf92e6327b175ebbfcc95188dfdd451a89ed0770bae14994e0
