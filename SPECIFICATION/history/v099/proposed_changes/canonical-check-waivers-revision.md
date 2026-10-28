---
proposal: canonical-check-waivers.md
decision: modify
revised_at: 2026-10-28T13:42:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with modifications. livespec core v233 ("Reasoned waivers", NFR §"Shared code sync — livespec-dev-tooling") ratified per-member canonical-check waivers and delegates the single declaration surface to this repository's contracts.md; this pass defines it as [tool.livespec_dev_tooling] canonical_check_waivers in the consumer's pyproject.toml, which every fleet member (the Rust console included) already carries and where repo_local_ci_skips sets the {slug, reason} precedent. The motivating case is livespec-console-beads-fabro's exclusion from the v1.137.1 release fan-out (run 40678729717) on canonical-check-slugs-wired. Decided under delegated revise_decision_mode by the plan seat, under coordinator gitops-fleet-capacity-monitoring direction (2026-10-28) that cmy3kd is spec-first and driven by this seat under the maintainer's delegated authority. Implementation is owed by livespec-dev-tooling-cmy3kd.

## Modifications

(1) MALFORMED widened from 'empty reason or non-canonical slug' to also cover a value that is not an array of tables, a missing slug or reason key, any extra key, a non-string slug or reason, and a whitespace-only reason; a finding for an entry with no string slug names its array position. (2) Both inline and [[...]] array-of-tables TOML forms are named. (3) The fleet row's skip widened from 'cannot be read' to 'cannot be read or parsed'. (4) Added: check-aggregate-completeness applies no waiver (fail-closed) when its own pyproject.toml cannot be read or parsed. (5) Scenarios reshaped from a fenced gherkin block to scenarios.md's bare-line convention (extra scenarios open with a bare 'Scenario:' line), and two scenarios added: the fleet row skipping on an unreadable member pyproject.toml, and the in-repo check applying no waiver on an unparseable one.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-28T13:42:24Z
verdict: NO BLOCKERS
proposal_stem: canonical-check-waivers
content_digest: 729e1127bc12352d88f86f7ed21195507dbb5b64f4fae9eac67c651d8f000aee
