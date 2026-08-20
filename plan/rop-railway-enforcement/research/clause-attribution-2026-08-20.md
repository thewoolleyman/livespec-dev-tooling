# Which clause actually convicts each question — and what the unused key would buy

`question-decomposition-2026-08-20.md` bucketed the 223 questions by SHAPE. This
attributes them to the CLAUSE that disqualifies each from the
`no_expected_failure_mode` exemption, and then SIMULATES the one relief that
already exists. Measured 2026-08-20, shipped basis.

Shape is what a reader sees; clause is what the check decides on. They are not
the same question, and the policy has to be written against the second.

## Attribution

| disqualifying clause | overseer | beads-fabro | livespec | runtime | git-jsonl | codex | **fleet** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **(c)** calls an I/O boundary | 54 | 9 | 9 | 3 | 1 | 2 | **78** |
| **(d)** propagation — a callee is disqualified | 52 | 8 | 5 | 7 | 1 | 1 | **74** |
| **(e)** `X \| None` return | 64 | 0 | 0 | 3 | 2 | 0 | **69** |
| **(a)/(b)** local `raise` or non-relieved `try` | 2 | 0 | 0 | 0 | 0 | 0 | **2** |
| total | 172 | 17 | 14 | 13 | 4 | 3 | **223** |

**78 + 74 + 69 + 2 = 223.**

### Two independent cross-checks, both clean

- Clause **(e)** attributes **69** — the SAME number the structural `X | None`
  detector in the decomposition note found, by a completely different route
  (annotation shape vs. the check's own clause). Two methods, one number.
- Clause **(a)/(b)** attributes **2** — the same 2 the limb-(iii) probe found
  (`proc_fd_targets`, doubled by the mirror). Those are the only two convictions
  in the whole fleet that turn on a local `try`.

⚠️ **ZERO convictions come from clause (d)'s UNSEEN-callee branch.** Every one of
the 74 propagates from a callee that is itself genuinely disqualified, not from
doubt about a callee the analysis never saw. The propagation is doing real work,
not manufacturing phantoms — which is what the equivalent analysis got wrong
before (`19 phantom consumptions inside _import_resolution`).

## ⛔ THE SIMULATION: declaring the unused key buys 30%, and the cascade is ~nil

`total_absence_returns` is declared ZERO times fleet-wide. Simulating it at its
MAXIMUM — every top-level `X | None` function in each universe declared, which
is the structural gate's full declarable set — gives the upper bound:

| repo | offenders before | after | relieved |
|---|---:|---:|---:|
| `livespec-overseer` | 182 | **116** | **66** |
| `livespec-runtime` | 13 | 10 | 3 |
| `livespec-orchestrator-git-jsonl` | 4 | 2 | 2 |
| `livespec-orchestrator-beads-fabro` | 18 | 18 | **0** |
| `livespec` | 14 | 14 | **0** |
| `livespec-driver-codex` | 3 | 3 | **0** |
| **fleet** | **234** | **163** | **71** |

▶️ **30% of the whole shipped-basis offender set is relievable today, with a
ratified key, and no new ruling.** 66 of the 71 are overseer.

⚠️ **AND THE CASCADE IS 2, NOT A MULTIPLIER.** 71 relieved against 69 attributed
to clause (e) means relieving the roots freed exactly TWO downstream functions
through clause (d). **So relieving the 69 does NOT unlock the 74.** The three
classes are near-independent, and the 74 propagate from clause-(c) callees rather
than from `X | None` ones. Anyone hoping the fixpoint would collapse the bucket
should stop hoping: it will not.

⚠️ **DECLARE THE CONVICTED ONES, NOT THE DECLARABLE ONES.** The structural gate
permits far more than is useful — 583 declarable functions in overseer, 352 in
beads-fabro, **1,138 fleet-wide** — while only **69** are actually convicted.
Each declaration costs a written reason and carries hard-fail staleness bounds,
so declaring the full set would be 1,069 pointless reasons and a large
maintenance surface. **The useful declaration set is the 69.**

⚠️ Note beads-fabro, livespec and driver-codex are relieved by **zero** despite
having 352 / 112 / 33 declarable functions between them: none of their
convictions is an `X | None`. This key is an overseer-shaped lever.

## ▶️ WHAT IS LEFT AFTER THE FREE 30%

163 convictions, of which 11 are tasks (five real functions, all blocked) and
152 are questions dominated by **clause (c)** — public functions that CALL an
I/O boundary and have no expected failure of their own — plus the 74 that
propagate from them.

**So the ruling that matters is a single one:** what does the Result-return rule
require of a PUBLIC function that performs I/O but has NO expected failure mode?
Answer that and clause (d) follows it automatically. It is the same question
`8o8e.28` asks about totality-by-contract, asked about totality-by-I/O.

## The harnesses

Both ship as fenced blocks rather than `.py`, for the reason the README gives.
The attribution rebuilds exactly what `_no_expected_failure_mode` builds
internally — `suffix_index(sources=...)`, `ModuleFacts(rel=, tree=, index=)`,
`calls_of(...)` — and buckets each convicted non-task function by the first
clause that disqualifies it, in the order (e), (a)/(b), (c), then (d) by
elimination. The simulation re-runs `_find_offenders` with a synthesised
`total_absence_returns` covering every declarable function and diffs the counts.

⚠️ Every figure here has a date. Re-derive before acting.
