---
topic: total-absence-returns-declaration-key
author: claude-opus-5
created_at: 2026-07-30T09:40:00Z
---

## Proposal: A `total_absence_returns` role key — the declared `X | None` whose `None` is an ABSENCE, not a failure

### Target specification files

- SPECIFICATION/contracts.md

### Summary

`livespec` v179 (`non-functional-requirements.md` §"ROP composition", ratified as PR #1827) scopes
the Result-return rule to a public function that HAS an expected failure mode, in two members.
**Member 1 is MECHANICAL** and already implemented here as
`checks/_no_expected_failure_mode.py` — it stores no claim and is recomputed every run. **Member 2
is ACTIVELY DECLARED**, and it names its carrier: "the `total_absence_returns` role key of its
`[tool.livespec_dev_tooling]` block".

§"Role keys" MUST therefore gain a `total_absence_returns` key: the consumer's per-function
declaration that a `X | None` return models a legitimate ABSENCE rather than a failure. An absence
is an ordinary answer the caller acts on; a failure is an outcome the caller must handle. Wrapping
an absence in `Failure` forces every caller to unwrap for an ordinary answer.

The ratified rule attaches **FOUR BOUNDS** to the key and states that they "are part of the rule,
not implementation detail". All four MUST appear in the normative bullet.

### Motivation

**Member 2 exists to relieve a refusal member 1 makes deliberately, and the refusal is stated
upstream.** v179's clause (e) disqualifies the whole `X | None` shape because "whether a `None`
models a FAILURE or a legitimate ABSENCE is a semantic question no AST can answer, so the syntactic
member refuses the whole shape rather than guessing." Member 2 is the narrow, declared relief for
that refusal. Without the key, clause (e) has no relief at all and the rule convicts every
legitimate absence in the fleet.

**THE SUBJECT IS ALREADY ESTABLISHED IN THIS REPO, FOUR SEPARATE TIMES, AND IT IS EXACTLY ONE
FUNCTION.** `cross_repo/fabro_image_pin_rewrite.py:100 tag_version_component() -> str | None`
returns `None` because a tag HAS no version component — a legitimate absence. Converting it would
force every caller to unwrap a `Failure` for an ordinary answer. That function was in the
STRONGEST convert class of this repo's original triage (a hand-rolled `X | None` failure track) and
was still not a conversion; it is the case that produced this repo's standing method constraint,
"read every function the classification convicted, not only the ones it acquitted."

**THE STRUCTURAL GATE IS A GATE AND NOT A LICENCE, and this repo has the measured counter-example
in hand.** `fleet/fleet_conformance.py fetch_manifest(*, ctx) -> Manifest | None` is structurally
eligible — the annotation qualifies — and it MUST NOT be declarable in practice, because its `None`
models FAILURE and collapses TWO distinct failures into one value ("could not fetch" and "fetched
but unparseable"), distinguished today only by a side effect. The shape qualifies; the semantics do
not. That asymmetry is why bound 1 is stated as a gate on what may be declared AT ALL rather than
as the whole test.

**A DECLARATION NOBODY VERIFIES IS THIS REPO'S SIGNATURE DEFECT**, so bound 3 is the load-bearing
one. The staleness detector on the sibling key `cross_repo_public_api` earned its keep immediately:
it rejected TWO of six first-draft entries, both authored from a CONSUMER's import statement
without reading the DEFINITION. The same authoring error is available here and MUST fail loudly
rather than carry a dead exemption forward. It MUST NOT be softened into a warning.

**BOUND 4 IS THE ANSWER TO "HOW DOES THIS RULE DIE".** v179 states it directly: "Six declarations
in one repo is small; the same carve-out unremarked across six repos is how a rule dies, and the
defense against that is a measured number rather than a cap nobody can calibrate." The count is a
CENTRAL-vantage obligation because a repo-local check cannot see six repos.

**AND ONE RESIDUAL IS UNGUARDED — this proposal states it rather than leaving it to be
discovered.** If a declared function's `None` changes meaning from ABSENCE to FAILURE while keeping
the `X | None` shape, no detector fires: bound 3 catches a shape change, not a semantic one. That is
the honest cost of member 2, it is why the key is gated to one annotation shape and required to
carry a reason a reviewer can check, and the normative bullet MUST say so.

**IT MUST NOT BE A REQUIRED ROLE KEY, for the measured reason `cross_repo_public_api` was not.**
Adding a key to `REQUIRED_ROLE_KEYS` makes an undeclared key a hard ERROR in every governed repo on
its next pin bump, and the auto-merge bump fan-out delivers "consumed" within minutes with nobody
deciding — the failure mode this repo already paid for once (`livespec-dev-tooling-dx8l`). Most
siblings have no content for this key.

### Proposed Changes

§"Role keys" MUST gain a `total_absence_returns` bullet in the role-key inventory, stating all of:

- **Shape.** An array of objects, each `{"file": "<repo-root-relative .py path>", "function":
  "<top-level function name>", "reason": "<why this `None` is an absence and not a failure>"}`.
- **Consumed by `public_api_result_typed`**, which treats each declared function as OUTSIDE the
  Result-return rule, per `livespec` v179 member 2.
- **BOUND 1 — A STRUCTURAL GATE.** The key reaches ONLY functions whose return annotation is of the
  form `X | None` (both `X | None` and `Optional[X]` spellings). A declared entry naming a function
  of any other shape MUST be REJECTED with a hard failure naming the entry — it is not silently
  ignored, and not accepted. A function of another shape cannot be declared into the key at all, so
  the key is not a general-purpose escape hatch.
- **BOUND 2 — A WRITTEN REASON per entry is REQUIRED, not advisory.** An entry whose `reason` is
  absent or empty MUST be rejected by the loader as a schema violation. A bare path is not a
  declaration.
- **BOUND 3 — A STALENESS DETECTOR THAT HARD-FAILS.** `public_api_result_typed` MUST verify that
  every declared entry still resolves to an existing top-level function of that name in that file
  AND that the function still returns `X | None`, and MUST exit non-zero naming the entry when
  either fails. A declaration MUST NOT outlive its subject, and a function refactored out of the
  `X | None` shape MUST drop its declaration LOUDLY rather than carry a dead exemption forward.
  This MUST NOT be a warning.
- **BOUND 4 — COUNTED, SO GROWTH IS VISIBLE.** The per-repo and fleet-wide count of
  `total_absence_returns` entries MUST be reported by a central-vantage conformance row, because a
  repo-local vantage cannot see the fleet. Growth is measured rather than capped.
- **NOT a required role key.** Absence is legal and parses to an empty declaration. It MUST NOT be
  added to `REQUIRED_ROLE_KEYS`, and an undeclared key MUST NOT be a local hard error.
- **RELAXING-ONLY, AND THEREFORE BOUNDED BY ITS GATE RATHER THAN BY ITS ABSENCE.** Unlike
  `cross_repo_public_api`, this key REMOVES functions from the rule's scope, so the tightening-only
  argument is not available to it and MUST NOT be claimed for it. What bounds it instead is bound 1:
  the set of declarable functions is not the consumer's choice but a syntactic property of the code,
  and it is recomputed every run. An empty declaration is the STRICT end of this key, not the
  relaxed one — the opposite polarity from the union role keys, and the bullet MUST say so, because
  a reader who carries the `pure_trees = []` intuition here will read the polarity backwards.
- **The unguarded residual.** The bullet MUST state that a declared function whose `None` shifts
  meaning from ABSENCE to FAILURE while keeping the `X | None` shape fires no detector, so bound 3
  catches a shape change and not a semantic one.

The `livespec-dev-tooling` self-application bullet in §"Consumer inventory" MUST NOT be changed to
list this key among the keys that "MUST be declared EXPLICITLY EMPTY": it is not a required key, and
adding it to that sentence would create exactly the required-key reading this proposal rejects.
