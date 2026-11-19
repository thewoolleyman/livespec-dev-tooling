---
proposal: ansible-recipes-pipelining-setting-name-is-wrong.md
decision: accept
revised_at: 2026-11-19T16:00:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

The measured pinned ansible-core 2.21.4 shows DEFAULT_PIPELINING does not exist and the committed [ssh_connection] pipelining key is ignored; the ratified name is wrong. Accepted as proposed: rename to ANSIBLE_PIPELINING in two places and require the key in a section the pinned version honours.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-19T16:00:39Z
verdict: NO BLOCKERS
proposal_stem: ansible-recipes-pipelining-setting-name-is-wrong
content_digest: c32438b82c38f26a7f8db3bae363be14656fa174c550288448cdf0f7b97e0c1b
