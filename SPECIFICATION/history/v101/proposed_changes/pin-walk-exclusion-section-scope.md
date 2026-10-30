---
topic: pin-walk-exclusion-section-scope
author: claude-opus-5
created_at: 2026-09-08T03:10:00Z
---

## Proposal: The nested-repository exclusion and the any-depth directory rule belong to the WALK, not to one bullet — and the walk root's own `.git` must be named

### Target specification files

- SPECIFICATION/contracts.md

### Summary

v063 defined the `uses:` ref format's scan set over three axes — DIRECTORY (any depth), SUFFIX,
and EXCLUSION (never descend into a directory carrying a `.git` entry) — and stated all three
INSIDE that one bullet. Two of the three are properties of the WALK rather than of that format,
and leaving them bullet-local has three consequences, one of which is a contradiction v063
introduced rather than inherited. This proposal hoists the DIRECTORY and EXCLUSION axes into the
§"Pin autodiscovery rules" preamble that governs every format, and states explicitly that the
walk root's own `.git` entry does not exclude the walk root.

### Motivation

Filed as a follow-up from the v063 revise pass, with the ratification reviewer's explicit
agreement that it is a follow-up and NOT a ratification condition on that amendment.

**1. v063 made a sentence in the neighbouring bullet FALSE.** The fabro-sandbox docker image tag
bullet asserts, about itself and the `uses:` ref format:

> This is a SECOND surface inside `.github/workflows/` beyond the `uses:` ref format above; the
> two formats scan the same files for different lines and never overlap.

That was true before v063 — both formats read `.github/workflows/*.yml` / `*.yaml` at the
repository root. It is not true now. The `uses:` format scans `.github/workflows/` at ANY DEPTH
and additionally `*.jinja`; the fabro-sandbox format's own text still says only "GitHub Actions
workflow files under `.github/workflows/` (`*.yml` / `*.yaml`)". The two formats therefore scan
DIFFERENT file sets, while the spec continues to claim they scan the same ones. This is a live
internal contradiction, and it is exactly the class of drift that gets resolved by an implementer
guessing.

**2. The EXCLUSION is a safety property of the walk, and only one format currently has it.** The
exclusion's stated reason is not tidiness — v063 recorded it as measured harm:

> A record sourced from a nested repository would misattribute another repository's pin to this
> consumer, and the corresponding rewrite would MUTATE that other repository's checkout. The walk
> is purely filesystem-based, so neither git tracking nor `.gitignore` prevents that on its own
> and the `.git`-entry test is the operative discrimination.

Every word of that applies unchanged to the fabro-sandbox format, which walks Fabro
`workflow.toml` files and `container:` image lines and carries NO exclusion of any kind. A nested
clone's `workflow.toml` is as much another repository's pin as its `uses:` line is, and the
consequence is worse in kind: the fabro-sandbox format's own contract requires that EVERY matching
line in EVERY file be rewritten in the same bump commit, so a misattributed record is not merely
reported, it is written. The reasoning that justified the exclusion for one format does not stop
at that format's bullet.

**3. Read literally, the exclusion excludes the walk root.** The rule is:

> the walk MUST NOT descend into any directory carrying a `.git` entry

The walk root of a consumer repository ALWAYS carries a `.git` entry — that is what makes it a
repository. A conforming implementer reading only this sentence has been told not to descend into
the very tree being walked, which would yield zero records for every consumer. The intended
meaning is plainly "do not descend into a NESTED repository", and the current wording leaves that
to inference. v063's commit message says the exclusion covers "a DIRECTORY for a nested clone, a
FILE for a linked worktree" — nested is the operative word, and it is missing from the normative
sentence.

This one is latent rather than live: an implementation that excluded its own walk root would
return no pins at all and be caught immediately. But a rule whose literal reading is absurd is a
rule that has to be re-derived by every reader, and the re-derivation is where a walk that also
skips a legitimate top-level `.github/` gets written.

### Proposed Changes

**(a)** In §"Pin autodiscovery rules", extend the preamble paragraph

> The pin-autodiscovery walk inspects the consumer repository for every supported pin format and
> yields a normalized `(pin_format, file_path, pin_key, current_value)` record per discovered pin.
> The walk MUST cover the following formats:

by inserting, before "The walk MUST cover the following formats:", two rules that govern EVERY
format below:

> **Walk scope — applies to every format in this section.** Unless a format's own bullet states a
> narrower root, a path pattern names a directory at ANY DEPTH beneath the walk root, not only the
> one at the repository root: a consumer that carries the same pin under a nested product or
> template tree holds the same pin.
>
> **Nested-repository exclusion — applies to every format in this section.** The walk MUST NOT
> descend into any directory OTHER THAN THE WALK ROOT ITSELF that carries a `.git` entry — a
> DIRECTORY for a nested clone, a FILE for a linked worktree. The walk root's own `.git` entry
> does NOT exclude the walk root; the test identifies a NESTED repository, and the walk root is
> the repository being walked. A tree beneath such an entry belongs to a DIFFERENT repository and
> its pins are not this consumer's pins: a record sourced from one would misattribute another
> repository's pin to this consumer, and the corresponding rewrite would MUTATE that other
> repository's checkout. The walk is purely filesystem-based, so neither git tracking nor
> `.gitignore` prevents that on its own, and the `.git`-entry test is the operative
> discrimination.

**(b)** In the `uses:` ref bullet, replace the now-duplicated **DIRECTORY** and **EXCLUSION** axis
text with a reference to the preamble, keeping the **SUFFIX** axis — which IS specific to that
format — stated in full. The bullet's record-semantics sentences are unchanged.

**(c)** In the fabro-sandbox docker image tag bullet, replace

> This is a SECOND surface inside `.github/workflows/` beyond the `uses:` ref format above; the
> two formats scan the same files for different lines and never overlap.

with

> This is a SECOND surface inside `.github/workflows/` beyond the `uses:` ref format above. The
> two formats read the same `*.yml` / `*.yaml` workflow files for different lines and never
> overlap; they do NOT have identical scan sets, because the `uses:` format additionally covers
> `*.jinja` workflow TEMPLATES, which this format does not — a rendered container image tag is
> pinned in the rendered workflow, not in the template.

If instead the ratifying pass concludes that the fabro-sandbox format SHOULD cover `*.jinja`
templates, that is a widening of a second format's scan set and MUST be carried by its own
proposal with its own measurement, not folded into this reconciliation.

### Rationale

- **It fixes a false statement the spec makes about itself today**, which no amount of careful
  implementation can satisfy.
- **It extends a measured safety property to the format that can do more damage with it missing.**
  The fabro-sandbox format rewrites every matching line in every file by contract; misattribution
  there is a write into another repository's checkout.
- **It removes an absurd literal reading** without changing the rule's intent or its discriminator.
- **It does not widen any scan set.** (a) states for all formats what was already true of the walk
  in practice, (b) is pure de-duplication, and (c) corrects a claim rather than a behaviour. Any
  covered-format COUNT stated in this section or in the walk's module docstring is unchanged.

### Non-goals of this proposal

- It does NOT add `*.jinja` coverage to the fabro-sandbox format, or to any format other than the
  one v063 ratified it for.
- It does NOT revisit v063's SUFFIX axis, which is ratified and stands.
- It does NOT change record semantics, `pin_key` derivation, or source-repo filtering for any
  format.
