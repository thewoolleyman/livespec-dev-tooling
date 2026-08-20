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
| 3 | `the-nine-2026-08-19.md` | The original hand-picked sample. ⚠️ Superseded on scope by note 2: it includes `proc_fd_targets` (raises nothing) and omits `ledger_mutation` (raises). Read as a sample, not the task set. |
| 4 | `first-unit-recheck-2026-08-19.md` | Why counts mislead: ~7% of convictions originate an exception-shaped failure. Withdraws the "driver-codex is cheapest" recommendation. |
| 5 | `underscore-file-skip-remeasure-2026-08-19.md` | The `8zv3.5` question: 214 vs 601, the ratified-text argument, the per-repo concentration. **Deferred to a consensus panel.** |
| 6 | `shipped-basis-offender-inventory-2026-08-19.md` | The offender LISTS, the 72-file non-product-in-universe class, and overseer's 14 false positives. |
| 7 | `child-disposition-triage-2026-08-19.md` | The eleven archive-blocking children: 4 stay, 7 leave, with reasons. |
| 8 | `local-llm-execution-route.md` | The execution constraint, its measured limits, the pilot, and §8's process failure. |
| 9 | `dead-failure-tracks-2026-08-19.md` | 19 railway functions whose failure track is uninhabited — and the check cannot see them. |
| 10 | `canonical-branch-probe-2026-08-19.md` | `8o8e.28`: the escape is real but costs a duplicated ratified contract. |
| 11 | `8o8e21-patch-staleness-2026-08-19.md` | `8o8e.21`'s Green patch no longer applies, and the module regrew the defect meanwhile. |

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
- `livespec-config-railway-red.patch` — the preserved Red for the `livespec` config work.
  ⛔ The worktree `~/.worktrees/livespec/fix-spec-governance-config-railway` holds an
  authored, UNCOMMITTED companion Red and **MUST NOT be reaped.**
- `5cai-fleet-measurement.md`, `qndn-75-triage.md` — earlier measurement records, superseded
  in their figures by the 2026-08-19 notes but retained for method.

## Open, and belonging to the maintainer

1. `8zv3.5` — ratify the names basis (601) or keep the shipped basis (214). Deferred to a
   consensus-panel **dossier**; ratification stays with the maintainer.
2. `8o8e.28` — price the Variant-B trade: removing the conviction duplicates a ratified
   precedence contract across two modules.
3. `8o8e.19`–`.29` — disposal. **These block archive.** See note 6.
4. The test-detection remedy for the 72-file class (note 5): multiple prefixes,
   filename detection, or relocation.
5. Whether an unreadable config reads as `False` or propagates — gates `8o8e.21` (note 10).
