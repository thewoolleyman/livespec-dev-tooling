---
proposal: cross-repo-public-api-declaration-key.md
decision: accept
revised_at: 2026-07-29T11:20:00Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

ACCEPTED as filed, under the maintainer ruling of 2026-07-29 delegating the accept/reject decision
at revise to the `rop-railway-enforcement` thread (the same delegation recorded in the v034 and v035
revisions). The proposal was not re-litigated.

**The key is ratified because the vantage is genuinely split, and that split is itself ratified
upstream.** `livespec` v178 states both halves: the repo-local check is hermetic and pre-commit; a
central-vantage conformance row re-measures the fleet's actual consumption graph. A criterion that
claims fleet-wide scope while being enforced only locally would assert a guarantee nothing computes.
This key is the interface between the halves — nothing more, and deliberately nothing less.

**TIGHTENING-ONLY was the clause worth arguing over, and it is ratified verbatim rather than
softened.** The obvious objection to a consumer-declared public surface is that a repo could declare
NOTHING and watch its whole public surface fall out of scope with the check green — `pure_trees = []`
wearing a new name, one level up in the schema. The ratified text answers it structurally rather than
by assurance: the repo-local forms of consumption (an import across a module boundary inside this
repo; a process entry point) are recomputed from the code on every run and are unaffected by this
key, so an absent declaration cannot silence a single name the local oracle already sees. What an
absent declaration CAN do is fail to add a name only a sibling sees. That residual is stated in the
ratified bullet rather than left for a reader to discover, and it is exactly what the central row
exists to catch.

**NOT a required role key, and the reason is a measured hazard rather than convenience.** Adding a
key to `REQUIRED_ROLE_KEYS` makes an undeclared key a hard error in every governed repo on its next
pin bump, and the auto-merge bump fan-out delivers "consumed" within minutes with nobody deciding —
the failure mode this repo already paid for once (`livespec-dev-tooling-dx8l`, a sibling master
turned RED by a change that was correct in isolation). Seven of the eight siblings have no content
for this key today. A required key would therefore redden eight masters to demand ceremony.

**The two bounds on an entry are the ones this repo has learned it needs.** A REQUIRED written reason
per entry, because an unexplained declaration is indistinguishable from an inherited one — the same
reasoning that gives `unarmed_until` a ledger id rather than free silence. And a HARD-FAILING
staleness detector, because a declaration that outlives its subject is the defect class this rule set
exists to remove. `livespec` v179 bounds `total_absence_returns` the same two ways; the parallel is
deliberate and the wording follows it.

**What the bullet says about its OWN limit is load-bearing, not a caveat.** The local check cannot
tell whether the declared set OMITS a name a sibling consumes, so a green local run does not mean the
declared surface is complete. Stating that inside the normative bullet — rather than in a rationale a
consumer never reads — is what keeps this key from becoming another green signal that means nothing.

**No `scenarios.md` entry is added, and that is a decision rather than an omission.** This revision
changes the SCHEMA: it adds one role-key bullet. Its observable behaviors (a reason required at load,
a hard-failing staleness detector, tightening-only scope) are mechanized in the implementation that
follows and are asserted at unit tier there. A `scenarios.md` heading in this repo carries an
INTEGRATION-tier (`tests.consumer`) obligation that this revision does not discharge — five existing
scenario headings already carry `test: "TODO"` for exactly that reason — so adding a sixth would
enlarge a known gap rather than close one. The scenario and its consumer-tier test are owed and are
filed on the ledger rather than deferred silently.

**Out-of-target, recorded so it is not lost.** Measuring this repo's real cross-repo consumed surface
to author its own declaration surfaced one case the criterion does not cleanly cover:
`livespec-orchestrator-beads-fabro`'s `.claude-plugin/hooks/codex_yolo_gate.py` imports
`livespec_dev_tooling.fleet._context.resolve_owner` — a PUBLIC name inside a package-PRIVATE module,
reached across a repo boundary. `public_api_result_typed` skips `_`-prefixed FILES wholesale, so the
name is invisible to it, while v178 clause 0 disqualifies only a `_`-prefixed NAME. That is either a
consumer reaching into a private module or a gap in the check's file-level skip, and it is filed
rather than resolved here.

## Resulting Changes

- contracts.md
