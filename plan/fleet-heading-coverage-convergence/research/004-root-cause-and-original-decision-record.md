# Root cause, and the original decisions that were right — the record

The maintainer's question (2026-09-09): *"I thought that's what the plumbing
was supposed to already prevent. Nothing is supposed to be able to be merged
unless there is a real test linked to the heading. How did this end up getting
fucked up and allowing copouts and merges of headings with no associated
tests?"* and *"discuss the original reason for the exemption that unrelated
commits could block it ... I remember there being a legitimate argument when I
made that decision originally."*

Answer: it was not a bug that slipped through. The plumbing was designed with
a placeholder state and four accommodations around it, each locally
reasonable; together they made a plausible sentence a permanent substitute
for a test. The two decisions the maintainer remembers were correct and are
preserved by this plan (charter D2). The gap was that nothing made the
transition END, and the `reason` field was inverted from acknowledgment to
exemption.

## Timeline of the design (all citations verified in git / the ledger)

**v009 — the transitional placeholder is ratified, with the reason as an
ACKNOWLEDGMENT of debt.**
`SPECIFICATION/history/v009/proposed_changes/scenario-tier-coverage-invariant.md`:
*"A `TODO` entry is permitted during transition provided its `reason`
explicitly acknowledges this tier requirement."* Rationale (line 31): *"the
seven scenario TODO entries registered by PR #77 already acknowledge the
integration-tier requirement in their `reason` fields and are left in place
(their real integration-tier tests land under epic li-scetdt / Wave 6)."*
This is the spec-first workflow and it is genuinely necessary:
`heading_coverage` requires a row for every H2 at ratification time, but the
test cannot exist until the spec is ratified and an impl work-item lands it.
It worked exactly as designed for `livespec-runtime-a27` (v025 ratified 32
scenarios as owned TODOs; a27 wrote all 32 real tests).

**2026-06-02, commit `66b3688d` (epic li-cvtodo) — a TIGHTENING.** Replaced
a `LIVESPEC_RELEASE_GATE` skip-entirely carve-out with the severity lever:
the scan always runs; `LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` makes
offenders fail; unset downgrades the same findings to warning + exit 0.
Triggered by core's v0.2.0 release-tag gate going red on 14 TODOs
(`livespec-besm`: "Does NOT block the release (the gate runs post-tag), but
leaves a red Release-tag check on every release until resolved").

**2026-08-16, commit `21fbd8ac` — authoring-time arming.**
`scripts/just/check-pre-commit-doc-only.sh` arms the fail tier whenever the
staged changeset touches the registry, reasoning: *"refusing an unowned TODO
at authoring time is the one arming that cannot block an unrelated commit."*
The intent was right: catch the cop-out in the commit that authors it.

**2026-09-04, `livespec-dev-tooling-3ztbdq` — the measured failure the
maintainer remembers.** The arming judged the WHOLE registry. The registry is
a shared, mandatory co-edit — every spec change adding a heading must touch
it — so 58 inherited unowned TODOs blocked ANY commit touching the file:
*"adding 8 TODO entries for v054's new headings failed on all 66."* The file
was unwritable; landing any new heading would first require clearing all
inherited debt you did not create. Interim fix: give every TODO a
`work_item`. Durable fix: *"scope the armed tier to entries ADDED in the
staged diff ... so the check matches its stated intent."*

**2026-09-06, commit `df946785` — the scope lever lands.** *"the armed
TODO-ownership tier judges only entries the staged diff touched."*
`LIVESPEC_SCOPE_HEADING_COVERAGE_TODOS_TO_HEAD_DIFF` narrows the VERDICT to
rows added/modified since HEAD; out-of-scope rows are still REPORTED
(`out_of_staged_scope`); an uncomputable baseline fails closed to the whole
registry. **The principle — a commit is judged on what it authors, not on debt
it inherited — is correct.** This plan keeps it (D2b, D3).

**Liveness confined to the release tier — for a real reason.** The check's
docstring: a per-commit verdict depending on mutable external (tracker)
state *"could flip master red with no commit, which `.ai/ci-gate-discipline.md`
treats as a real broken state rather than a notification."* That document
lives in livespec core (`/data/projects/livespec/.ai/ci-gate-discipline.md`,
not dev-tooling — the docstring's path is stale but the argument is real): a
red master is fixed by *"identifying the landed change that turned master
red"*; a tracker-driven red has no landed change to identify. This plan keeps
liveness AND the new age bound at the release tier (D5).

**2026-09-06, commits `eab57b40` / `aa59c69` / `dad30a0` / `08847b6` (Fabro,
the "adjudicate heading entries" pass, runtime).** The headings were resolved
into `TODO` + reasons of the form *"No independently testable assertion at
runtime"*, *"Enforced by CHECKS rather than by a pytest test"*, *"orientation
prose"*. The gate accepted all of them because owned-TODO-with-a-reason is
its legal state. **This is the inversion:** the reason field's ratified job
was to acknowledge an OWED test; it was used to assert that NO test is owed.

## The five accommodations, and which are defects

| accommodation | where | locally reasonable because | defect? |
|---|---|---|---|
| `TODO` + non-empty `reason` is a legal row | `heading_coverage.py:19,214-217` | spec-first placeholder (v009) | no — but the reason must be an acknowledgment, never an exemption (D4) |
| per-commit tier warns, exit 0 | `no_todo_registry.py:22-25` | do not block authoring; surface placeholders | no — with a ratchet the NEW-row case fails at authoring (D3) |
| release tier fails only unowned / closed-owner | `:31-33` | an owned live TODO should not block an unrelated release | partial — needs the age bound so "live" cannot mean "forever" (D5) |
| staged-diff scope lever | `:39-77`, `df946785` | inherited debt must not make the shared registry unwritable (3ztbdq) | no — correct; but it also means inherited rows are never re-judged by any gate, hence the ratchet register (D3) |
| no shrink-only ratchet on the TODO set | (absent) | — | **yes — the missing convergence mechanism** |

Plus one design gap not in the table: liveness was hardwired `None` until
`d0er` (2026-09-08), so even the ownership guard was vacuous — any owner
string passed. Fixed; now real.

## Why "make TODO un-mergeable at per-commit" is the WRONG fix (retracted)

It would (a) block spec ratification until every test exists in the same
commit, destroying the spec-first workflow v009 exists for, and (b) recreate
3ztbdq exactly — every commit touching the shared registry blocked by
inherited rows. The maintainer's original decisions stand. The fix is
convergence: a ratchet that fails only NEW rows at authoring (scoped, so
unrelated commits are untouched), a reason guard, an age bound, real
liveness, and a burn-down to zero — after which the scope lever and the
`reason` slot are retired because there is nothing left for them to exempt.
