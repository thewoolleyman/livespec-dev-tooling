---
topic: canonical-check-waivers
author: claude-opus-5-5
created_at: 2026-10-28T12:28:11Z
---

## Proposal: Canonical-check waivers declared in pyproject.toml

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Defines the declaration surface that livespec core v233 delegates here: `[tool.livespec_dev_tooling] canonical_check_waivers`, an array of {slug, reason}. check-aggregate-completeness and the fleet row canonical-check-slugs-wired read only this key. Each exempts a waived slug, fails on a stale or malformed waiver, and treats an unreadable member pyproject.toml as a skip.

### Motivation

livespec core v233 ("Reasoned waivers") ratified per-check waivers and requires livespec-dev-tooling's contracts.md to define their one declaration surface. The v1.137.1 release fan-out (run 40678729717) excluded livespec-console-beads-fabro, the Rust member, on canonical-check-slugs-wired. Its check-heading-coverage cannot pass without a second coverage map duplicating its own Rust check-behavior-coverage, which the coordinator ruled against on 2026-10-28. pyproject.toml is chosen because every fleet member, the Rust console included, already carries `[tool.livespec_dev_tooling]`, and repo_local_ci_skips already sets the precedent of an array of {slug, reason} there. The key is defined outside the role-key list because that list's Consumers clauses are recomputed from code, which does not read the key until livespec-dev-tooling-cmy3kd lands. Work item: livespec-dev-tooling-cmy3kd.

### Proposed Changes

1. In contracts.md §"Shared check inventory", after the **The `baseline` profile.** paragraph, add a paragraph:

"**Canonical-check waivers.** A consumer declares a reasoned waiver of a canonical check, as ratified by `livespec/SPECIFICATION/non-functional-requirements.md` §"Shared code sync — livespec-dev-tooling" ("Reasoned waivers", livespec v233), in its own `pyproject.toml` as `canonical_check_waivers` under `[tool.livespec_dev_tooling]`. The value is an array of inline tables, each with exactly two string keys: `slug`, a canonical slug spelled as its `check-<name>` recipe, and `reason`, a non-empty explanation. An absent key declares no waiver. `check-aggregate-completeness` and the fleet-conformance row `canonical-check-slugs-wired` MUST read this one key; neither may read a waiver from any other surface. Each MUST treat a waived slug's absence from the `just check` aggregate as satisfied. Each MUST fail on a STALE waiver, whose slug the aggregate selects, and on a MALFORMED waiver, whose `reason` is empty or whose `slug` is not in the canonical set; the finding names the slug and which of the two it is. The fleet-conformance row MUST log every honoured waiver with its member, slug and reason. The fleet row reads the key from the member's master tree, the same tree it reads the aggregate from; when that `pyproject.toml` cannot be read, the row MUST skip rather than evaluate the member as declaring no waiver, so an unreadable file is never taken as an absent one."

2. In scenarios.md, append a new H2 section:

## Scenario: a canonical check waived in pyproject.toml is exempt from the aggregate and fleet gates

```gherkin
Feature: Canonical-check waivers declared in pyproject.toml

Scenario: A waived slug passes both gates
  Given a fleet member whose pyproject.toml declares canonical_check_waivers with slug check-heading-coverage and a non-empty reason
  And its just check aggregate does not select check-heading-coverage
  When check-aggregate-completeness runs in the member and the fleet-conformance row canonical-check-slugs-wired evaluates it
  Then neither fails on check-heading-coverage
  And the fleet-conformance run logs the waiver with the member, the slug and the reason

Scenario: A stale waiver fails
  Given a member whose canonical_check_waivers names check-file-lloc
  And its just check aggregate selects check-file-lloc
  When check-aggregate-completeness runs
  Then it fails, naming check-file-lloc as a stale waiver

Scenario: A malformed waiver fails
  Given a member whose canonical_check_waivers entry has an empty reason
  When the fleet-conformance row canonical-check-slugs-wired evaluates it
  Then it fails, naming the slug as a malformed waiver
```
