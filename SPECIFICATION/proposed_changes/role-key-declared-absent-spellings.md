---
topic: role-key-declared-absent-spellings
author: claude-opus-5
created_at: 2026-07-28T10:11:19Z
---

## Proposal: Retire declared-empty as the sanctioned opt-out for the five union role keys

### Target specification files

- SPECIFICATION/contracts.md

### Summary

§"Consumer configuration schema" still ratifies DECLARED-EMPTY as "the sanctioned, VISIBLE opt-out" that makes a gating check no-op while logging an `info` event, and still names "the two sanctioned outs". Every clause of that is now wrong for the five keys in `UNION_ROLE_KEYS` (`pure_trees`, `target_dirs`, `source_tree_prefixes`, `dataclasses_tree`, `neutral_hook_body_path`). This proposal replaces the DECLARED-EMPTY clause with the four blessed declared-absent spellings, each carrying a non-empty reason in the PARSED VALUE, and records the transitional status of a bare `[]` / `""` on those keys: accepted today with a WARN, a hard load-time error once every consumer has migrated.

### Motivation

The overload this replaces caused a measured fleet-wide failure, and the spec is the last place it is still ratified. One value carried two incompatible meanings — "the concept does not apply to this repo" and "the concept applies and is switched off" — and the shared gate read either as consent. `check-public-api-result-typed` therefore reported GREEN in all nine fleet repos while scanning ZERO files; `check-claude-md-coverage` was disarmed in five repos and the commit-time TDD pairing gate in three, the last of these by a declaration whose own comment named two OTHER checks.

A ratified clause describing the retired regime is not a stale comment — it carries normative BCP 14 force and is what the next implementer builds to. It is also a standing instruction to rebuild the defect: the current text tells an author to write exactly the spelling the loader now flags. All eight Python-bearing consumer repos have already migrated off it and measure zero legacy declarations, so this proposal documents a state the fleet is already in rather than requesting new work.

Stating the guarantee precisely matters as much as making it. TOML has no sum types, so nothing prevents a person TYPING `[]`. What the design buys is exactly two things — after parsing the ambiguity is UNREPRESENTABLE in the domain model, and ambiguous input FAILS LOUD at load. The spec MUST NOT claim it is impossible to express.

### Proposed Changes

In §"Consumer configuration schema" → §"Role keys":

**1. Replace the UNDECLARED clause's remediation.** The current text says a gating check MUST "name both the offending key and the two sanctioned outs (declare the real value, or declare it explicitly empty with a comment giving the reason)". Replace with: the diagnostic MUST name the offending key and every legal spelling for it — a populated value, or (for a key in `UNION_ROLE_KEYS`) exactly one of the four declared-absent spellings below. A remediation that does not say what IS legal only relocates the confusion.

**2. Replace the DECLARED-EMPTY clause.** Introduce a normative distinction between two disjoint groups of role keys:

- The **UNION keys** — `pure_trees`, `target_dirs`, `source_tree_prefixes`, `dataclasses_tree`, `neutral_hook_body_path` — are those whose declared value IS a consuming check's scan universe. For these, a populated value or exactly ONE of four declared-absent spellings MUST be declared:

  ```toml
  pure_trees = { not_applicable         = "<reason>" }
  pure_trees = { superseded_by          = "<reason>" }
  pure_trees = { unarmed_until          = "<ledger-id>" }
  pure_trees = { convention_not_adopted = "<reason>" }
  ```

  Each variant MUST carry a non-empty payload; an empty payload MUST be a load-time error, because an empty payload is a new unreadable emptiness wearing a blessed name. The reason therefore lives in the parsed value rather than in a TOML comment no checker can read.

- A bare `[]` / `""` on a UNION key is TRANSITIONAL. The loader MUST accept it, MUST parse it to a distinct legacy variant, and MUST log at **WARN** (not `info`) naming both the consuming repo and the key. Once every consumer has migrated, the loader MUST reject it as a hard load-time error. The rejecting loader MUST NOT land before every consumer has migrated, per the harden-first ordering §"Consumer configuration schema" already applies to required-key schema changes.

**3. State the guarantee precisely.** The spec MUST describe the property as "fail-loud-at-parse plus unrepresentable-after-parse", and MUST NOT claim the ambiguous spelling is impossible to express. TOML has no sum types; nothing prevents a person typing `[]`.

**4. Update the affected per-key bullets.** The bullets for `pure_trees`, `target_dirs`, `source_tree_prefixes`, `dataclasses_tree` and `neutral_hook_body_path` currently read "`[]` is the sanctioned declared-empty spelling" (or the `""` declared-none equivalent). Each MUST instead name the populated value plus the four declared-absent spellings.

**5. Update the `install_no_shadow_ledger` description.** §"Wrapper CLI surface" describes that installer as no-opping "when that role key is declared empty (`\"\"`) or undeclared". It MUST also no-op when `neutral_hook_body_path` carries any of the four declared-absent variants, since that is now the spelling a consumer without a neutral shared body uses.

## Proposal: Preserve [] as a legitimate spelling for the clean role keys, because emptiness makes those checks stricter

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The spec today says nothing at all about why an empty declaration is SAFE on some role keys and dangerous on others, which makes the four-variant regime above look like a blanket condemnation of `[]`. It is not. For the five keys `source_trees`, `io_trees`, `commands_trees`, `supervisor_entry_files` and `covered_trees`, a bare `[]` MUST remain a legitimate declaration, because those keys do not select a scan universe — their consuming checks derive the universe from the git-tracked first-party set and read the key only to decide what is EXEMPT or what is legacy-severity. For them, emptiness makes the check STRICTER, never blinder.

### Motivation

This is the single clause most likely to be lost in a rewrite, and losing it is expensive in both directions.

Lose it one way and a future editor "tidies" the schema by pushing all ten role keys through the union. That is ceremony with no defect behind it: it forces five keys to declare a reason for an absence that was never ambiguous, and it obscures the actual finding by making the union look like a style rule rather than a fix for a measured disarm.

Lose it the other way and a future editor reads "declared-empty is retired" as universal and "fixes" `io_trees = []` by naming a tree. That would be a REGRESSION with a specific, already-known shape: emptying `io_trees` is what makes the catch-position and domain-raise checks inspect the WHOLE source universe with nothing wholesale exempt. Naming a tree there exempts code that is currently inspected. The `check-hook-trees-not-io-exempt` guard exists precisely because that instinct keeps recurring.

The distinction was established by execution rather than by reading: with these keys empty, the consuming checks were measured still scanning the full first-party universe in all eight repos — 144 files in one repo, 129, 185, 84, 49, 32, 7 and 6 in the others. Emptiness on these keys removes exemptions; it does not remove files.

One caveat belongs in the record rather than being smoothed over: `source_trees` empty WOULD act as a severity softener, reclassifying files from legacy-ERROR to newly-covered WARN. No consumer declares it empty, so there is no live instance — but it is not structurally immune, only currently unexercised.

### Proposed Changes

In §"Consumer configuration schema" → §"Role keys", immediately following the UNION-key clause proposed above, the spec MUST state the complementary rule:

**CLEAN keys retain `[]`.** For `source_trees`, `io_trees`, `commands_trees`, `supervisor_entry_files` and `covered_trees`, a bare `[]` MUST remain a legitimate declared value and MUST NOT be treated as ambiguous. These keys are EXEMPTION or SEVERITY predicates: their consuming checks derive the inspection universe from the git-tracked first-party `.py` set, and read the key only to decide what is exempt from a rule or what carries legacy severity. An empty declaration therefore makes those checks STRICTER — it removes exemptions, not files.

The spec MUST make the partition criterion explicit rather than leaving it as a list to memorize: **a role key belongs in `UNION_ROLE_KEYS` if and only if its declared value IS a consuming check's scan universe, such that an empty declaration causes that check to inspect nothing.** A key that only scopes an exemption or selects a severity is a CLEAN key. This is the criterion a future editor MUST apply when a role key is added, and it MUST be re-evaluated whenever the role-key inventory changes — mirroring the existing re-evaluation obligation in §"Configurability is the partition criterion".

The spec SHOULD additionally warn that "declared-empty is retired" MUST NOT be read as universal, and that naming a real tree in `io_trees` to satisfy such a reading is a regression: it wholesale-exempts code that an empty `io_trees` leaves inspected.

## Proposal: Ratify the ratified-constraint discriminator for choosing between not-applicable and unarmed-until

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Offering four declared-absent spellings without saying how to choose between them re-creates the original defect at one remove: a consumer that cannot tell which variant applies will pick whichever reads tidiest, and `not_applicable` always reads tidiest. This proposal ratifies the discriminator that separates `not_applicable` from `unarmed_until` — whether the consuming repo's OWN ratified specification asserts an obligation the key gates — and requires an `unarmed_until` payload to name a real, still-open work item.

### Motivation

The discriminator is not a matter of taste; it was derived by applying it across all eight consumer repos, where it split one key four ways against four. Two repos with NO pure-module subtree on disk correctly received OPPOSITE answers, because the question is what the repo's ratified specification obliges, not what its directory listing shows. A directory-listing heuristic would have produced four false `not_applicable` declarations — and it would have produced them in exactly the repos that most needed the honest one, since those are the repos whose own constraints require the thing.

The concrete case: two consumers ratify "property-based test coverage on pure modules" in their own constraints and wire the consuming check into their aggregate gate, while declaring the key empty — so the check was wired, obliged, and scanning zero files. `not_applicable` there would put a demonstrable falsehood into parsed data, and `convention_not_adopted` would sanction a repo permanently opting out of its own ratified constraint. Only `unarmed_until` is true.

The liveness requirement follows from the same shift. Because a variant's payload is now PARSED DATA rather than a comment, a wrong or already-closed identifier is a durable lie claiming pending work that is in fact finished — which is the emptiness-means-consent shape wearing a blessed name. Requiring the id to resolve AND still be open is what keeps `unarmed_until` from decaying into a permanent opt-out.

The cross-tenant detail is load-bearing rather than incidental: consumers legitimately cite work items in another repo's tracker, so a verifier that resolves ids only within the declaring repo would fail the majority of live declarations.

### Proposed Changes

In §"Consumer configuration schema" → §"Role keys", the spec MUST define each declared-absent variant by the condition under which it is true, not merely by name:

- **`not_applicable`** — the concept does not exist for this consumer, and no ratified requirement of this consumer's own specification obliges it. Nothing is deferred.
- **`superseded_by`** — the concept applies AND is satisfied by a different mechanism, which the reason MUST name.
- **`unarmed_until`** — the concept applies and is deliberately switched off pending NAMED work. The payload MUST be a work-item identifier.
- **`convention_not_adopted`** — the concept applies and the consumer has declined to adopt it, with the reason stating what arming it would cost. It MUST NOT be used to decline a requirement of the consumer's own ratified specification; that case is `unarmed_until`, or an amendment to that specification.

**The discriminator MUST be stated normatively:** when choosing between `not_applicable` and `unarmed_until`, the deciding question is whether the consumer's OWN ratified specification asserts an obligation the role key gates — NOT whether a corresponding directory exists in the repo. Where such an obligation exists and the key is not populated, the declaration MUST be `unarmed_until`; `not_applicable` in that situation is a false statement in parsed data.

**Liveness of `unarmed_until`.** The payload MUST identify a work item that resolves and is still OPEN. A payload naming a nonexistent item, or one that is already closed, MUST be a conformance failure: it asserts that pending work exists when it does not, which is the same silent-consent defect the union removes. A verifier of this property MUST resolve identifiers ACROSS trackers, since a consumer MAY legitimately cite a work item held in another repository's tracker; a verifier that resolves only within the declaring repo would reject valid declarations.

The spec SHOULD note the accepted cost of blessing `convention_not_adopted`, so it is not mistaken for a loophole: it permanently and VISIBLY sanctions certain structural checks being off in certain consumers. That visibility is the point — the alternative was the same state held silently. It is NOT licence for the set to grow; each use still requires a written reason.

## Proposal: Add acceptance scenarios for the four declared-absent spellings and the clean-key carve-out

### Target specification files

- SPECIFICATION/scenarios.md
- SPECIFICATION/contracts.md

### Summary

The three proposals above introduce observable load-bearing behavior — how each spelling parses, what a bare `[]` does on a union key versus a clean key, and what an `unarmed_until` payload must satisfy. Under this project's authoring discipline, behavior MUST be carried by a Gherkin scenario and not by prose alone. This proposal adds the scenarios that pin that behavior.

### Motivation

Every clause the three proposals above add is an input-to-output behavior with a failure mode, and each one has a cheap look-alike that prose cannot distinguish from the real thing. "The loader accepts the blessed spelling" looks identical to "the loader ignored the key"; "the legacy spelling warns" looks identical to "the legacy spelling was silently accepted"; and "the clean key is unaffected" looks identical to "nobody checked the clean key". A scenario states the observable difference.

The scenario that matters most is the clean-key one, because it is the guard against the specific regression the second proposal describes: without it, a future editor reading "declared-empty is retired" has nothing mechanical stopping them from naming a tree in `io_trees` and wholesale-exempting code that is currently inspected.

This project already treats a green check with an empty scan set as the characteristic failure signature rather than a pass, so a scenario asserting a non-zero effect is worth more here than an exit-code assertion.

### Proposed Changes

`SPECIFICATION/scenarios.md` MUST gain the following acceptance scenarios, in this project's existing Gherkin style (each keyword line separated by blank lines):

**Scenario: a blessed declared-absent spelling parses to a distinct variant carrying its reason** — Given a consumer declares a union role key as one of the four declared-absent inline tables with a non-empty payload, When the configuration loader reads that block, Then the key MUST resolve to a variant distinguishable from every other declared-absent variant, And the payload MUST be retrievable from the parsed value rather than requiring a reader to consult the TOML comment.

**Scenario: a declared-absent variant with an empty payload is rejected at load** — Given a consumer declares a union role key with a blessed variant name but an empty or whitespace-only payload, When the loader reads that block, Then loading MUST fail with an error naming the key and every legal spelling.

**Scenario: the legacy empty spelling on a union key warns and does not silently pass** — Given a consumer declares a union role key as a bare `[]` or `""`, When a check consuming that key runs, Then the run MUST emit a WARN-level structured event naming both the consumer and the key, And the emptiness MUST NOT be reported as a sanctioned opt-out.

**Scenario: an empty clean role key makes its consuming check stricter, not blinder** — Given a consumer declares `io_trees` as a bare `[]`, When the catch-position and domain-raise checks run, Then they MUST inspect the consumer's full first-party universe, And the number of files inspected MUST be non-zero, And no file MUST be wholesale exempt by virtue of that empty declaration.

**Scenario: an unarmed-until payload naming a closed work item is a conformance failure** — Given a consumer declares a union role key as `unarmed_until` whose payload names a work item that is closed, When the conformance verifier runs, Then it MUST report a failure identifying the consumer, the key, and the item, And the failure MUST state that the declaration claims pending work that is already complete.

Where this project links clauses to scenarios via a heading-coverage registry, the corresponding entries MUST be added atomically with these scenarios, per the self-application discipline the spec already applies.
