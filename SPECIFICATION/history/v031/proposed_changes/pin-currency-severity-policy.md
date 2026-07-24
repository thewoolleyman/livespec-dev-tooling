---
topic: pin-currency-severity-policy
author: claude-opus-4-8-fleet-pin-propagation
created_at: 2026-07-24T09:13:40Z
---

## Proposal: Pin-currency severity policy

### Target specification files

- SPECIFICATION/contracts.md
- tests/heading-coverage.json

### Summary

Document, as contract, the fleet pin-currency obligation rows and their two-tier severity policy, whose upper tier is CONTEXT-SCOPED: a PERSISTING gap (a pin stale AND whose bump PR for the latest release is already open) escalates to an error finding only where a per-member remedy exists — the release fan-out preflight, whose per-member verdicts the dispatch-matrix filter consumes to exclude exactly the offending sibling — and is reported at warning severity in every other evaluating context, each of which can only pass or fail as a whole. Plain staleness stays a warning everywhere, a can't-read never escalates, and the diagnostic message is identical across contexts so scoping lowers severity without ever suppressing the finding. The same change also amends §"`reusable-release-dispatch.yml`" so the preflight is documented as the per-member FILTER it now is rather than the whole-job GATE it used to be — without that amendment this proposal would contradict the very section it cites as its authority. Together these close the gap between the shipped enforcement (livespec-dev-tooling PR #590, merged as 17ab424 and 4855a92) and a contracts.md that still describes both the staleness leg's severity and the preflight's semantics in their superseded form. A COMPANION propose-change in the livespec core repo, filed under the same epic, amends the one sibling spec (`non-functional-requirements.md` §"Fleet membership contract") that still asserts the whole-job-gate semantics, so the fleet is consistent after both ratify.

### Motivation

livespec core work-item livespec-dh9r. The fleet measured propagation health by open-bump-PR count, which cannot distinguish a healthy fan-out from a dead one — both read zero. Pin currency is the correct measure, and a central pin-currency row already existed but was wired to nothing at warning severity, so it stated the truth about a stalled member during the v0.20.0 fan-out stall and nothing surfaced it. Slice 3 gives that observation teeth.

The escalation is context-scoped rather than global because of WHERE the check is evaluated. `check-fleet-conformance` is wired into several contexts (this repo's `just check` aggregate, its per-PR CI job, the scheduled central sweep `fleet-conformance.yml`, and the release fan-out preflight), and of these ONLY THE PREFLIGHT can act on a finding per member: it alone passes `--emit-member-verdicts`, and its per-member verdicts are what the livespec-f73t filter consumes to exclude one member while dispatch proceeds to the rest. Every other context can only pass or fail as a whole, so in every other context — the per-PR CI job and the scheduled sweep alike — a persisting gap is reported at warning severity.

What forced the scoping is the blast radius of the alternative. Measured on 2026-07-24, livespec-dev-tooling is the only member repo running this check in CI (zero occurrences of fleet-conformance in the other eight members' ci.yml). Promoted globally, any single member's persisting gap would therefore red this repo's entire PR surface — including the PRs that would repair the gap — while the offending member is typically owned by a different track. That is the enforcement-before-adoption deadlock .ai/ci-gate-discipline.md forbids resolving with a lever or a severity downgrade, so the resolution is to scope by context instead.

This is not hypothetical: it fired on the change's first live run, where PR #590's own CI produced ten persisting-gap error findings and blocked the PR that introduced them.

### Proposed Changes

THREE EDITS to SPECIFICATION/contracts.md, plus one co-edit. Every FIND below was re-grepped against origin/master on 2026-07-24 and occurs EXACTLY ONCE; re-verify before executing, since the vantage-model stream edits this file actively.

=== EDIT 1 — replacement (line 343) ===

FIND:

has its pin freshness monitored centrally — at *warning* severity — by the `dev-tooling-pin` row's staleness leg rather than auto-bumped.

REPLACE WITH:

has its pin freshness monitored centrally by the `dev-tooling-pin` row's staleness leg rather than auto-bumped, at the severity the §"Pin-currency severity policy" section defines.

Rationale: the clause hardcodes a severity that is now defined by policy and varies by evaluating context, so it must defer rather than restate. The unchanged tail ("This is a defined possibility with NO current fleet member: ...") stays coherent.

=== EDIT 2 — new `## ` section ===

PLACEMENT (exact, by quoted heading boundary — do NOT paraphrase this anchor): insert the new section immediately BEFORE the existing `## Cross-repo coordination automation surface` heading, i.e. directly after the end of the `## Consumer compat block — pin-and-bump policy` section that contains the EDIT 1 sentence. Both headings are live H2s in contracts.md. Inserting anywhere mid-section would split that section and orphan its following H3s.

## Pin-currency severity policy

Central pin-currency evaluation draws its pin-format definitions from the `cross_repo.pin_autodiscovery` inventory (§"Pin autodiscovery rules") and evaluates FOUR of the formats that inventory declares: the `pyproject.toml` `[tool.uv.sources]` dev-tooling pin (`dev-tooling-pin` row), `.livespec.jsonc` `compat.pinned` (`compat-pin-currency`), GitHub Actions `uses:` refs (`uses-pin-currency`), and the Fabro sandbox image tag (`fabro-pin-currency`). The inventory declares further formats (e.g. `.vendor.jsonc` `upstream_ref`, the codex-acp Dockerfile `ARG`) that carry no currency obligation row; the inventory, not this list, is the source of truth for the format DEFINITIONS, and which of them a currency row evaluates is the obligation-row registry's concern. The three `compat-pin-currency` / `uses-pin-currency` / `fabro-pin-currency` rows discover their pins via that inventory walk and compare prefix-agnostically (`pin_staleness.denotes_same_release`, so `python-v0.53.2` and `v0.53.2` denote the same release); the `dev-tooling-pin` row's staleness leg instead reads the `[tool.uv.sources]` tag directly and compares it to the latest release tag verbatim (exact string inequality), a divergence to keep in mind when reasoning about a prefixed dev-tooling pin.

Severity is a two-tier policy, and the upper tier is CONTEXT-SCOPED:

- **Plain staleness is a WARNING.** A pin behind the latest release with no open bump PR for that release is normal operation — the minutes-long window between a release and its bump PR merging. Warning severity moves no exit code and never gates the release fan-out.
- **A PERSISTING gap is an ERROR only where a per-member remedy exists.** A pin that is stale AND whose bump PR for the latest release is already open means the self-heal mechanism fired and could not land; the open PR is the durable, stateless record of that failure. That finding escalates to error ONLY when it is evaluated in a context that can act on it PER MEMBER — the release fan-out preflight, whose per-member verdicts the dispatch-matrix filter consumes to exclude exactly the offending sibling from that release's dispatch. In every other evaluating context — the per-PR CI job and the scheduled central sweep alike, each of which can only pass or fail as a whole — the same condition is reported at WARNING severity.
- **The diagnostic does not change with the context.** Both severities emit the identical message, naming the member, the pin format, and the open bump PR number. Scoping lowers the severity; it never suppresses, abbreviates, or silences the finding.
- **A can't-read never escalates.** An unreadable PR list, release list, or tree keeps the row at its lower severity or skips it (a can't-read is not a violation).

The scoping is a property of the EVALUATING CONTEXT, not a configurable severity. There is no lever, environment variable, or per-member exemption that changes a persisting gap's severity within a given context.

An error finding for a member in the release's dispatch sibling set excludes that member from the dispatch matrix via the fan-out preflight's per-member filter (the §"`reusable-release-dispatch.yml`" contract) — it never halts dispatch to conformant members.

=== EDIT 3 — re-contract the preflight to the shipped FILTER semantics (FOUR replacements: 3a/3b/3d in §"`reusable-release-dispatch.yml`", 3c in §"Fleet surface — central conformance and reconcile"). ALL FOUR are required; a ratifier that stops after two lands exactly the line-366/388 contradictions this proposal exists to fix. ===

WHY THIS EDIT IS REQUIRED, not optional: the live section still documents the preflight as a whole-job GATE, and EDIT 2 cites that section as the authority for per-member exclusion. Ratifying EDIT 2 without EDIT 3 would land a direct intra-document contradiction, with the cited authority asserting the opposite of the citing text. A whole-file grep of live contracts.md for member-verdicts / per-member filter vocabulary returns ZERO hits, so the filter that shipped in PR #580 has never been contracted at all.

EDIT 3a — FIND:

Fleet-conformance preflight (BLOCKING):

REPLACE WITH:

Fleet-conformance preflight (per-member FILTER; BLOCKING only on structural failure):

EDIT 3b — FIND:

the dispatch matrix `needs` this job, so a red fleet fails the release fast and loudly instead of silently skipping an unwired member.

REPLACE WITH:

the job emits per-member verdicts and the dispatch matrix is FILTERED by them. The exit-4 path drives that filter only when the verdict artifact is well-formed and names at least one non-conformant member; each non-conformant member that is in the dispatch SIBLING SET is then excluded from the fan-out loudly — annotated by member name and failing conformance rows — while dispatch proceeds to every conformant sibling. A STRUCTURAL failure reds the whole release, exactly as the pre-filter gate did: the conformance check exiting with any code other than `0` or `4` (the exit-`1` precondition failure); an exit 4 whose verdict artifact is missing, empty, or malformed; an exit 4 whose artifact names NO non-conformant member at all — a finding attributable to no fleet member, the discovery sweep's unregistered fleet-shaped repo or a blind row; and the filter step's rejection of a discovered sibling with no verdict entry (manifest/verdict drift). So the no-silent-skip guarantee holds for the dispatch sibling set: a non-conformant sibling is never silently skipped — it is excluded with a naming annotation, or the whole release reds. One class is neither: when the artifact names a non-conformant member that is NOT a dispatch sibling (the publishing repository, structurally excluded from its own fan-out), or a no-member finding co-occurs with a non-conformant member, the guard takes its exit-0 path and that finding is surfaced by the scheduled central sweep and livespec-dev-tooling's per-PR CI rather than by this dispatch.

EDIT 3c — the SAME relabelling, at the second and last place the spec describes the preflight. Without this the file would carry EDIT 3a's qualified label at one line and an unqualified whole-job-gate descriptor at another.

FIND:

and the release fan-out's blocking preflight

REPLACE WITH:

and the release fan-out's preflight (the per-member filter, blocking only on structural failure, per §"`reusable-release-dispatch.yml`")

(Verified 2026-07-24: occurs exactly once on origin/master, at line 366. A whole-spec-tree grep for "preflight" returns two matching LINES — contracts.md 366 and 390 — and three string occurrences, the third being the `fleet-preflight` JOB NAME on line 390, which the edits correctly leave alone. No hits in spec.md, constraints.md, scenarios.md, or non-functional-requirements.md. So EDIT 3a and EDIT 3c cover both English descriptions of this surface in this repo's governed spec.)

EDIT 3d — the Behavior paragraph of this SAME section still describes the dispatch as firing to every non-source member, which is the whole-job-gate behavior EDIT 3 supersedes: under the filter, a non-conformant member is excluded, so dispatch does NOT fire to every remaining member.

FIND:

fires a `repository_dispatch` event to each remaining member carrying the payload contract

REPLACE WITH:

fires a `repository_dispatch` event to each remaining member that the fleet-conformance preflight's per-member filter did not exclude (below), carrying the payload contract

(Verified 2026-07-24: occurs exactly once on origin/master, at line 388, within this section's Behavior paragraph.)

=== CO-EDIT (required, same revise payload) ===

tests/heading-coverage.json — add an entry for the new `## Pin-currency severity policy` heading, so the coverage map stays in lockstep and pre-commit's check-heading-coverage passes. Shape (matching the existing 42 entries):

{"spec_root": "SPECIFICATION", "spec_file": "contracts.md", "heading": "## Pin-currency severity policy", "test": "TODO", "reason": "Seeded with the livespec-dh9r Slice-3 severity-policy section. Replace TODO with the real test ID via a governed propose-change/revise loop's resulting_files[] mechanism."}

In resulting_files[] this path is spelled ../tests/heading-coverage.json when --spec-target is the main SPECIFICATION tree.

=== DRIFT SWEEP (re-derived 2026-07-24; recorded so a reviewer need not redo it) ===

- Line 343 is the only sentence hardcoding the staleness leg's severity — replaced by EDIT 1.
- Line 390's preflight paragraph contradicted the filter semantics — repaired by EDIT 3. NOTE: this was MISSED by the first sweep, which grepped for severity vocabulary rather than for the preflight's own description, and was caught by the independent review. Recorded because the miss is instructive: a proposal that CITES a section as authority must read that section, not merely reference it.
- Line 366 was assessed IN FULL — the whole bullet, not one sentence of it. Its severity clause ("warning-severity findings such as pin staleness log but do not fail") is ACCURATE under this policy and deliberately unamended, since plain staleness warns everywhere and a persisting gap warns in every non-preflight context. Its wired-contexts enumeration is likewise accurate and unamended. But the SAME bullet also calls the surface "the release fan-out's blocking preflight", an unqualified whole-job-gate descriptor — amended by EDIT 3c. NOTE the process failure this repaired: the FIRST sweep endorsed line 366 after reading only its severity sentence, which is the identical too-narrow-endorsement pattern that produced the EDIT 3 miss recorded above. Reading a line for the one property you are changing is not reading the line. A whole-spec-tree grep for "preflight" now confirms only two occurrences exist (contracts.md 366 and 390), both amended here.
- Line 371 (`local_reconcile`) concerns a different, local-vantage row partition; unrelated and unamended.
- No spec file asserts a persisting gap is unconditionally an error ("persisting" returns zero hits across spec.md, contracts.md, constraints.md, scenarios.md, non-functional-requirements.md), so this addition contradicts nothing it must also repair.
- `## Pin-currency severity policy` does not already exist (zero hits), so EDIT 2 is a clean addition.
- Cross-repo: a broad sweep for the SUPERSEDED whole-job-gate semantics ("blocking preflight", "fails the release fast and loudly", "unwired member fails ... instead of being silently skipped") across every cloned fleet repo's LIVE governed spec plus AGENTS.md and .ai/*.md found ONE sibling contradiction — livespec core's `SPECIFICATION/non-functional-requirements.md` §"Fleet membership contract" ("Fleet-conformance enforcement" paragraph), which still describes the preflight as a BLOCKING gate that fails the whole release on one unwired member. This is amended in lockstep by a COMPANION propose-change filed in the `livespec` repo under the same epic; that companion rewrites the paragraph to the filter semantics (per-member exclusion with a naming annotation; structural failures still fail the release). With that companion, no sibling is left contradicting this. NOTE the process lesson, twice-learned in this proposal: a cross-repo sweep scoped to the property being CHANGED (here, severity vocabulary) is not a sweep — the contradiction lived in gate-vs-filter language that contains no severity words at all. The sweep must grep the superseded BEHAVIOR, not the changed attribute.

=== CODE ALIGNMENT — EDIT 3b's structural-failure clause ===

EDIT 3b asserts that an exit-4 whose findings attach to NO member (the discovery sweep, a blind row) fails the release rather than being demoted to a log line. This is backed by the reusable-release-dispatch.yml guard landed as livespec-dev-tooling PR #604 (work-item livespec-dev-tooling-jeqp): the conformance step converts exit 4 to exit 0 only when `jq -e 'any(.[]; .conformant == false)'` finds a non-conformant member in the artifact, so an all-conformant (or empty / malformed) artifact with exit 4 falls through to a red exit. That guard was a maintainer-decided fix (2026-07-24) to a regression the f73t filter introduced, and it is on master (merge commit verified) before this contract text ratifies (enforcement-before-adoption, `.ai/ci-gate-discipline.md`). The guard closes the PURE case (an exit-4 with an all-conformant artifact fails the release). It does NOT close a residual class the re-review surfaced, deferred on jeqp for a complete non-sibling accounting: the guard's jq keys on ANY non-conformant member in the full-manifest artifact (the publisher included, since run_member_rows is manifest-wide), while the filter step excludes only non-conformant SIBLINGS. So a conformance finding that is not a non-conformant sibling — a non-conformant PUBLISHING repository (excluded from its own fan-out; its verdict is surplus to the filter), or a no-member finding CO-OCCURRING with any non-conformant member — passes the guard's exit-0 path and is not release-blocking on this dispatch. EDIT 3b's normative text is scoped to the dispatch sibling set precisely so it stays true across this class; the escaping findings are surfaced by the scheduled central fleet-conformance.yml sweep and livespec-dev-tooling's own per-PR CI (the two contexts that will SURFACE such a finding — NOT the escaping member's own CI, which for a non-dev-tooling member does not run check-fleet-conformance at all).

=== VERIFICATION EVIDENCE (live; cite rather than re-derive) ===

Both directions of the scoping were observed in production against the SAME live gap — livespec-overseer's `compat-pin-currency` persisting gap:

- WARNING direction: run 30059932539 (per-PR CI) is SUCCESS while STILL REPORTING that gap at "level": "warning", alongside "fleet conformance passed", members 9, blind_rows 0. The green is attributable to the scoping, not to the gap disappearing.
- ERROR direction: run 30060186985 (the v0.54.3 fan-out, first to execute the scoped escalation) annotated "EXCLUDED from release dispatch: livespec-overseer — failing conformance rows: compat-pin-currency" and dispatched to all SEVEN conformant siblings with livespec-overseer absent from the matrix.
- Earlier, the filter's benign path: run 30028730379 (v0.53.2 fan-out), verdict artifact emitted and consumed, excluded=0, 8/8 dispatched.

These are POINT-IN-TIME observations. As of the 2026-07-24 run 30059932539, livespec-overseer remained non-conformant and was still reported; that repo is owned by another track and will eventually be repaired, after which these runs cannot be re-derived from live state. Cite them by run id.

=== ORDERING CONSTRAINT — DISCHARGED, recorded as history ===

Landing this severity promotion before the per-member preflight filter was deployed AND exercised would have recreated the v0.20.0 fleet-wide stall, in which one member's persisting gap halted all propagation. The filter shipped in livespec-dev-tooling PR #580 and was observed working in a real fan-out before the escalation merged, so the ordering .ai/ci-gate-discipline.md codifies was honored. Stated here as the reason for the sequence, not as an open precondition.
