---
proposal: invocation-set-inventory.md
decision: accept
revised_at: 2026-08-26T02:05:13Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

v051's release_bump_classification inventories __all__ export names only, so it passed VACUOUSLY on the real v1.32.1 -> v1.33.0 changeset: inventory 714 -> 714, required none, declared minor. 56 of the 60 slug modules under checks/ and both under workflow_checks/ declare an empty __all__, so deleting or renaming a slug -- a MAJOR that removes an element of the FIRST entry in this spec's own Semver discipline enumeration -- moved the inventory by zero names and would have passed a fix:-typed patch release. That is the failure shape the check exists to prevent, in the repo that ships it. This models the invocation set alongside the export set, behind one OPTIONAL absent-behaves-as-empty role key so no consumer is conscripted and no existing gate verdict changes, and it corrects the section's overclaim by splitting the honest limit into two distinct limits -- unmodelled element kinds, and behavior-only breaks. Independent review returned BLOCKERS on the first pass (the added/removed finding fields were jointly unsatisfiable with the non-collision keying, and the docstring clause bound only one limit); both are fixed and the final pass returned NO BLOCKERS on digest-confirmed stable bytes.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-08-26T02:04:04Z
verdict: NO BLOCKERS
proposal_stem: invocation-set-inventory
content_digest: 7ba8ba3ca4788f3af3fc8d797b6a4803b57c374800563e46c1c92dfb0c33bcb3
