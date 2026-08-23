# `rop-railway-enforcement` research — read this first

**The ledger is authoritative over everything in this directory.** Plan status, the next
action, and every handoff live as comments on epic `livespec-dev-tooling-8o8e`, read
through the plan timeline. These files hold RESEARCH only. When a file and the ledger
disagree, the ledger wins — that rule exists because this thread's stalest claims all came
from trusting a file.

```bash
/usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-8o8e
```

## Read in this order

| # | file | what it settles |
|---|---|---|
| 1 | `state-correction-2026-08-19.md` | **Start here.** The decoupling landed (`46c5dab`), turned five repos red, and was REVERTED (`f4247110`). `8zv3.3` is closed on evidence that was subsequently reverted. Sequencing: adoption BEFORE arming. |
| 2 | `task-vs-question-census-2026-08-20.md` | **Start here for scope.** Measured: 11 tasks / 223 questions fleet-wide. The remaining task-shaped work is **five functions in `livespec-overseer`**, all blocked on the stdlib-vs-railway contract conflict. Corrects `the-nine` in both directions. |
| 3 | `question-decomposition-2026-08-20.md` | The 223 questions in FOUR classes. **101 of them already have a ratified mechanism nobody has used** (`total_absence_returns`, declared ZERO times fleet-wide); only 122 need a genuinely new ruling. Read with note 2. |
| 4 | `clause-attribution-2026-08-20.md` | Which CLAUSE convicts each question, and a simulation of the unused key: **30% of the fleet's offenders are relievable today with no new ruling**, the cascade is 2 not a multiplier, and the one ruling that matters is clause (c). |
| 5 | `the-nine-2026-08-19.md` | The original hand-picked sample. ⚠️ Superseded on scope by note 2: it includes `proc_fd_targets` (raises nothing) and omits `ledger_mutation` (raises). Read as a sample, not the task set. |
| 6 | `first-unit-recheck-2026-08-19.md` | Why counts mislead: ~7% of convictions originate an exception-shaped failure. Withdraws the "driver-codex is cheapest" recommendation. |
| 7 | `underscore-file-skip-remeasure-2026-08-19.md` | The `8zv3.5` question: 214 vs 601, the ratified-text argument, the per-repo concentration. **Deferred to a consensus panel.** ⚠️ Its addendum's verb is corrected by note 14. |
| 7a | `8zv3-5-dossier-2026-08-23.md` | **The decision-ready synthesis for `8zv3.5`** — both cases, the four counter verdicts, the fleet re-derived at 2026-08-23 SHAs (344/950 raw, 208/612 distinct), and a recommendation: accept the RULE, keep the BASIS. Read this before notes 7 and 14. |
| 8 | `shipped-basis-offender-inventory-2026-08-19.md` | The offender LISTS, the 72-file non-product-in-universe class, and overseer's 14 false positives. |
| 9 | `child-disposition-triage-2026-08-19.md` | The eleven archive-blocking children: 4 stay, 7 leave, with reasons. |
| 10 | `local-llm-execution-route.md` | The execution constraint, its measured limits, the pilot, and §8's process failure. |
| 11 | `dead-failure-tracks-2026-08-19.md` | 19 railway functions whose failure track is uninhabited — and the check cannot see them. |
| 12 | `canonical-branch-probe-2026-08-19.md` | `8o8e.28`: the escape is real but costs a duplicated ratified contract. |
| 13 | `8o8e21-patch-staleness-2026-08-19.md` | `8o8e.21`'s Green patch no longer applies, and the module regrew the defect meanwhile. ✅ **Discharged** — landed as beads-fabro #1799/#1801; the regrowth was FOUR functions, not two. |
| 14 | `8zv3-5-counter-case-2026-08-19.md` | The adversarial case AGAINST this thread's own `8zv3.5` finding, by its author. Counters 2, 3 and 4 are live; 1 and 5 fail. |

## Supersessions — do not read these as current

- `legacy-handoff-2026-08-04.md` and `legacy-supervisor-charter-2026-07-28.md` are
  **HISTORY ONLY**, carrying supersession banners. Their MEASUREMENTS and METHODS remain
  good; their ORDERS — "DO NOT RESUME", "DO NOT DRIVE", and the never-idle drive prose —
  are EXPIRED. The 2026-08-04 cost hold was lifted 2026-08-19.
- `local-llm-execution-route.md` §4 item 2 carries an inline correction banner; heed it.
- `shipped-basis-offender-inventory-2026-08-19.md` §"Surprise 2" is corrected later in the
  same file — read to the end before acting on it.
- `first-unit-recheck-2026-08-19.md` **withdraws** a recommendation repeated in several
  earlier ledger handoffs. The ledger's later entries carry the withdrawal.

## ⚠️ Every number here has a date, and they move

Measured drift within a single day, 2026-08-19: overseer's universe **281 → 299** and its
convictions **156 → 162**; beads-fabro **19 → 20**; dev-tooling **3 → 0** as another
session's conversions landed. **Re-derive before acting, and quote every figure with its
timestamp.** A part and a total from different days do not add.

The harness for re-deriving is reproduced inside
`underscore-file-skip-remeasure-2026-08-19.md`. It is **deliberately not committed as a
`.py`** — a file under `plan/` is first-party Python, enters `resolve_check_universe()`,
and would become an offender in its own measurement. The commit gate caught exactly that.

## Artifacts, not notes

- `8o8e21-green.patch` — authored, gate-passed, **never landed**; see note 10 before using.
- `overseer-railway-blocked.patch` — the authored, gate-run `livespec-overseer`
  conversion that **cannot land**: it trips overseer's ratified stdlib-only
  constraint. Evidence for the contract conflict; see the ledger entry of
  2026-08-20. ⛔ Do not apply it until that conflict is ruled.
- `livespec-config-railway-red.patch` — the preserved Red for the `livespec` config work
  (`8o8e.25`). ✅ **VERIFIED 2026-08-23: this file IS the worktree's staged Red, byte for
  byte**, captured read-only from
  `~/.worktrees/livespec/fix-spec-governance-config-railway` and diffed against this patch
  with zero differences over all 162 lines.

  ⚠️ **CORRECTION — this entry used to call that worktree's Red an "authored, UNCOMMITTED
  companion" that "MUST NOT be reaped", and every ledger handoff since has carried the
  warning forward.** It is wrong in its load-bearing part: the content is not uncommitted
  and it is not a companion, it is the same bytes. **Nothing unique is at risk there.**

  ⛔ Still do not reap it — it is not this thread's worktree — but reap-avoidance is now a
  courtesy to its owner, NOT data preservation, and it must stop being quoted as a reason
  `8o8e.25` cannot be worked. Measured at the same time: the branch was **never pushed**,
  has **no PR**, holds **no overseer registry track**, and its staged file was last written
  **2026-08-03**. Treat `.25` as unclaimed unless an owner says otherwise.
- `5cai-fleet-measurement.md`, `qndn-75-triage.md` — earlier measurement records, superseded
  in their figures by the 2026-08-19 notes but retained for method.

## Open, and belonging to the maintainer

1. `8zv3.5` — ratify the names basis (601) or keep the shipped basis (214). Deferred to a
   consensus-panel **dossier**; ratification stays with the maintainer.
2. `8o8e.28` — price the Variant-B trade: removing the conviction duplicates a ratified
   precedence contract across two modules.
3. Disposal of the remaining plan children. **These block archive.** See note 9.
   ⚠️ The range `8o8e.19`–`.29` is NO LONGER the right address: `.20`, `.22`, `.23`,
   `.24`, `.26`, `.27` and `.29` were re-parented to `livespec-dev-tooling-jtrt` /
   `-qx2l`, and `.16` followed them to `jtrt`. **14 children remain undisposed**, and
   most are NOT tidy-away candidates — `.30` and `.31` in particular are this epic's own
   closure PRECONDITIONS held as children, not stale bugs. Re-derive the list from the
   ledger before acting on it.
4. The test-detection remedy for the 72-file class (note 5): multiple prefixes,
   filename detection, or relocation.

## Answered — do NOT re-raise these as maintainer gates

- **Whether an unreadable config reads as `False` or propagates** (was open item 5,
  gating `8o8e.21`). ✅ **ANSWERED: it PROPAGATES**, shipped in
  `livespec-orchestrator-beads-fabro` PR #1799, verified on that repo's `origin/master`
  `c6c4512f`.

  It was decided as a FINDING rather than escalated, per this fleet's rule that a
  question you can answer with a recommendation is not a maintainer question. The
  reasoning: reporting an unparseable `.livespec.jsonc` as "no such factory" **IS** the
  read-vs-write swallow `8o8e.21` exists to eliminate, so folding it into the default
  would have re-committed the defect inside its own fix. Implemented as
  `_dispatcher_block_or_raise`, mirroring the precedent the item had already ruled for
  `resolve_store_config` — zero public signatures moved, zero callers changed.

  ⛔ **This does NOT close `8o8e.21`.** `resolve_credential_wrapper` still lets an
  unparseable config silently turn off the pre-push `check-ledger-conformance-live`
  gate, which the item's own text calls its most consequential half. That half is a
  SHELL change and is untouched.
