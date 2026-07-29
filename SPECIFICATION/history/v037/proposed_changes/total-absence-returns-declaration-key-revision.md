---
proposal: total-absence-returns-declaration-key.md
decision: accept
revised_at: 2026-07-30T09:55:00Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

ACCEPTED as filed, under the maintainer ruling of 2026-07-29 delegating the accept/reject decision
at revise to the `rop-railway-enforcement` thread (the same delegation recorded in the v034, v035 and
v036 revisions). The proposal was not re-litigated.

**The key is ratified because the upstream rule NAMES it.** `livespec` v179 member 2 does not
describe a mechanism and leave the carrier open; it says "the `total_absence_returns` role key of its
`[tool.livespec_dev_tooling]` block". This revision adds the schema bullet that upstream text already
depends on. Ratifying it is fidelity, not a widening.

**THE POLARITY PARAGRAPH IS THE PART OF THIS BULLET MOST LIKELY TO BE "TIDIED", AND IT IS THE PART
THAT MATTERS.** Its sibling key `cross_repo_public_api` is TIGHTENING-ONLY, and the phrase appears
three times in that bullet. This key is the opposite: it REMOVES functions from the rule's scope. The
tempting move — carrying the reassuring "tightening-only" language across to a second declaration key
because the two are otherwise parallel — would be a false statement of exactly the kind this repo
spent an epic removing. So the ratified text says the argument is NOT available here, names what
bounds the key instead (bound 1, a syntactic property of the code recomputed every run rather than
the consumer's choice), and states that **an empty declaration is the STRICT end of this key**. A
reader arriving from §"Declared-absent spellings for the union role keys" carries the opposite
intuition — there, empty was the ambiguous, blinding value — and would read this key's polarity
backwards without being told.

**BOUND 1 IS RATIFIED AS A HARD REJECTION RATHER THAN A SILENT SKIP, and the difference is the whole
gate.** An implementation that quietly ignored a declared entry whose function is not `X | None`
would satisfy the letter of "the key reaches ONLY functions annotated `X | None`" while making a
mis-declaration invisible — a declaration that appears to be doing something and is not, which is
this epic's own subject. The ratified wording is "MUST be REJECTED with a hard failure naming that
entry, neither silently ignored nor accepted". Both wrong readings are foreclosed by name because
each is individually plausible.

**BOUND 3 IS RATIFIED AS "MUST NOT be a warning", in those words, because the softening is the
predictable next edit.** A staleness detector that warns is a staleness detector that is ignored. The
evidence is one key over and one day old: `cross_repo_public_api`'s detector rejected TWO of six
first-draft entries, both authored from a CONSUMER's import statement without reading the DEFINITION.
Had it warned, both would have shipped. The same authoring error is available here in the same shape,
so the hard failure is carried over deliberately rather than by symmetry.

**THE UNGUARDED RESIDUAL IS RATIFIED INTO THE NORMATIVE BULLET, not left in this rationale.** A
declared function whose `None` shifts from ABSENCE to FAILURE while keeping its shape fires no
detector. v179 states that residual upstream and calls it "the honest cost of member 2"; a schema
bullet that mechanized the three checkable bounds and omitted the uncheckable one would read as
complete coverage. Where a reader will actually look is the bullet, so that is where the limit is
stated — the same reasoning that put `cross_repo_public_api`'s completeness limit in its bullet
rather than in its rationale.

**THE COUNTER-EXAMPLE IS RECORDED IN THE PROPOSAL RATHER THAN THE BULLET, and that placement is
deliberate.** `fleet_conformance.fetch_manifest -> Manifest | None` is structurally ELIGIBLE for this
key and MUST NOT be declared into it: its `None` models failure, and collapses two distinct failures
("could not fetch", "fetched but unparseable") into one value distinguished only by a side effect.
That is the sharpest available illustration that the shape can qualify while the semantics do not —
but it is an argument about one function in one repo, and normative schema text that named it would
go stale the moment the function is converted. The bullet carries the GATE; the proposal carries the
worked example.

**NOT a required role key, for the measured reason and not for symmetry.** Adding a key to
`REQUIRED_ROLE_KEYS` makes an undeclared key a hard error in every governed repo on its next pin
bump, and the auto-merge bump fan-out delivers "consumed" within minutes with nobody deciding — the
failure mode this repo already paid for once (`livespec-dev-tooling-dx8l`, a sibling master turned RED
by a change correct in isolation). This repo's own declaration has exactly ONE entry; most siblings
have none.

**No `scenarios.md` entry is added, and that is a decision rather than an omission** — the same
decision, for the same reason, as v036. This revision changes the SCHEMA: it adds one role-key
bullet. Its observable behaviors (a reason required at load, a hard-failing structural gate, a
hard-failing staleness detector) are mechanized in the implementation that follows and asserted at
unit tier there. A `scenarios.md` heading in this repo carries an INTEGRATION-tier (`tests.consumer`)
obligation this revision does not discharge — five existing scenario headings already carry
`test: "TODO"` for exactly that reason — so adding a sixth would enlarge a known gap rather than close
one.

**Out-of-target, recorded so it is not lost.** Bound 4's central-vantage count and
`cross_repo_public_api`'s completeness obligation are now BOTH owed to the same unbuilt surface
(`livespec-dev-tooling-5cai`). Two ratified keys one revision apart each defer a bound to a row that
does not exist yet. That is legitimate sequencing — the local halves are enforceable on their own and
strictly better than nothing — but it means the central row is now load-bearing for two ratified
clauses rather than one, and it should not be treated as an enhancement.

## Resulting Changes

- contracts.md
