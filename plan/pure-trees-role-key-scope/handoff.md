# pure-trees-role-key-scope

> **Ledger anchor:** epic `livespec-dev-tooling-8zv3` (P1). The ledger is authoritative
> over this file. Re-derive every number and every repo state before quoting it.
>
> ```bash
> cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-8zv3
> ```
>
> **Created 2026-08-04** by splitting the `pure_trees` concern out of
> `plan/rop-railway-enforcement`, which was carrying three tangled concerns and is
> now ON HOLD. This thread exists so the ROP track can become small, cohesive and
> achievable without churn.

## The one-sentence problem

`pure_trees` is a **shared role key with FIVE real code consumers**, and
`public_api_result_typed` is the ONE whose rule binds a different scope than the key
selects — so it gates itself off and scans **zero files in all nine repos**.

> ⛔ **CORRECTED 2026-08-04: FIVE, NOT SEVEN.** The original "seven" came from
> `grep -rln pure_trees` — a FILENAME-level grep that counts any file *mentioning* the
> string, docstrings and comments included. Re-derived with an AST pass counting only real
> code references. **A proxy for consumption was reported as consumption**, which is the
> same shape as a check reporting on files it never inspects — committed by this thread's
> own author. **Re-derive from the AST, not from a grep.**

## What is measured, and what is inferred

**MEASURED 2026-08-04** (re-run these; do not trust the transcription):

| repo | shipped-check result |
|---|---|
| `livespec-dev-tooling` | exit 0, ZERO files scanned, `role_key_spelling=not_applicable` |
| `livespec` (ledger: 15 offenders) | exit 0, ZERO files scanned, `unarmed_until=livespec-mutreal.1`, level **warning** |

```bash
cd /data/projects/livespec && mise exec -- uv run python -m livespec_dev_tooling.checks.public_api_result_typed; echo "EXIT=$?"
```

All nine `pure_trees` declarations, read from each repo's `pyproject.toml`:

| spelling | repos |
|---|---|
| `not_applicable` | `livespec-dev-tooling`, `livespec-runtime`, `livespec-driver-claude`, `livespec-driver-codex` |
| `unarmed_until = "livespec-mutreal.1"` | `livespec`, `livespec-overseer`, `livespec-orchestrator-git-jsonl` |
| `unarmed_until = "bd-ib-6qb2mc"` | `livespec-orchestrator-beads-fabro` |
| zero first-party Python | `livespec-console-beads-fabro` — the sole sanctioned exemption |

**THE CLASSIFICATION IS DONE** (`8zv3.1`, first deliverable, read-only). AST code-refs =
`config.pure_trees` attribute reads plus the literal `"pure_trees"` key:

| consumer | code-refs | verdict |
|---|---:|---|
| `check_mutation` | 4 | **GENUINE NEED** — mutates pure logic (`parse/`+`validate/`). Gates off legitimately. |
| `pbt_coverage_pure_modules` | 4 | **GENUINE NEED** — its subject IS pure-layer test modules. |
| `public_api_result_typed` | 4 | **⛔ SCOPE MISMATCH** — the only one. |
| `partition_completeness` | 2 | **NOT A SCOPE GATE** — enumerates `pure_trees` as one partition member among roles. |
| `source_trees_scoped_to_consumer` | 2 | **NOT A SCOPE GATE** — validates every role path exists. |
| `_import_resolution` | **0** | **NOT A CONSUMER** — prose only |
| `_single_meaning_variants` | **0** | **NOT A CONSUMER** — prose only (uses `pure_trees = []` as an analogy) |
| `fleet/_rows_public_api_conformance` | **0** | **NOT A CONSUMER** — prose only |

▶️ **THIS MATERIALLY DE-RISKS THE CHANGE: it is a ONE-CONSUMER edit, not a seven-check
refactor.** `check_mutation` and `pbt_coverage_pure_modules` **MUST KEEP** gating on
`pure_trees` — that is what the key is FOR, and changing them would be the real softening.

⚠️ **The class question was still worth asking even though the answer was "one"** — asking it
is what proved the other four correct rather than assumed. A class sweep returning one
instance is a RESULT, not a miss.

**INFERRED — attack this first, it is the load-bearing claim.** `pure_trees` asks
*"has this repo carved its pure-module subtree?"*, which is genuinely load-bearing for
mutation testing and PBT coverage. The ROP railway rule binds **first-party public
API** — a different set. If that is right, the ROP check's gate key does not match its
rule's scope, and the fix is to stop gating on `pure_trees` at all.

## ⛔ The two consequences that make this urgent rather than tidy

1. **Four repos are structurally unconvictable.** The `not_applicable` repos have no
   pure subtree at all, so while the scan universe stays `pure_trees`-scoped the check
   can never convict there — yet the ledger records real offenders in exactly those
   repos (`livespec-dev-tooling` 1, `livespec-runtime` 11, `livespec-driver-codex` 1).
2. **The measurement basis diverges from the enforcement basis.** Every per-repo count
   on `8o8e.7`–`8o8e.13` is taken with `_find_offenders` over `resolve_check_universe()`.
   The shipped check's SCAN universe is `pure_trees`. **Today's remediation numbers
   measure a criterion that never runs.**

## The proposed change

`checks/public_api_result_typed.py::main()`:

- drop the `pure_trees` role-absence gate (`role_absence_exit_code`, ~461-469)
- drop the `pure_trees` resolution and `ensure_declared_paths_contain_python` (~470-478)
- have `_scan` walk `universe` from `resolve_check_universe()` — already called at ~479

**This is FIDELITY, not softening.** It makes the check strictly stricter: four
structurally-unconvictable repos become scanned. It does not hit the "never remove,
weaken or skip a check" boundary. It also un-shadows the declaration staleness gates,
which the module's own docstring notes sit *behind* the `pure_trees` gate and are
therefore unverified in all nine repos today.

## ✅ The ordering trap — MEASURED, AND IT DOES NOT FIRE

`livespec-dev-tooling` runs this check on **itself** (`justfile:206`, `:730`), so arming it
would turn its own `just check` red and `lefthook` would then block the very commit that
fixes it. That is why remediating this repo is a PRECONDITION, not a follow-up.

**But it costs nothing here.** Simulating the decoupled scan against master (read-only,
`_scan` replicated with `resolve_check_universe()` as the walked set):

| basis | offenders |
|---|---:|
| universe size | **177 files** |
| WITH the `_`-prefixed FILE skip (**shipped `_scan`**, line 387) | **0** |
| WITHOUT the `_`-file skip (the epic's per-repo measurement basis) | **1** |

The single offender is `livespec_dev_tooling/fleet/_public_api_graph.py:244
cross_member_consumption`. **So dev-tooling is already clean under shipped semantics and
`8zv3.2` collapses to a verification step.**

⚠️ **THAT IS CONDITIONAL AND THE CONDITION IS THE POINT: it holds only while the
`_`-prefixed FILE skip stays.** Do not let the decoupling silently drop it — dropping it is
a separate, independently-argued change that re-introduces this offender and a much wider
fleet blind spot the ROP handoff already records as *wider than the ratified rule* (v178
clause 0 disqualifies `_`-prefixed NAMES, not FILES).

⚠️ **AND EVERY PER-REPO NUMBER NOW HAS TWO BASES** — shipped semantics vs the epic's
measurement basis differ on the `_`-file skip as well as the universe. dev-tooling is **0**
on one and **1** on the other. **Say which basis you mean, every time**; `8o8e.17` exists
because a part and a total from different bases were added.

✅ Independently corroborated: the rop worker measured this repo at universe 176 / raw 1,
naming the same function. Two derivations, same offender.

Per-repo remediate → arm still governs the FLEET fan-out (`8zv3.4`) — one coordinated
cross-repo effort, not eight independent PRs. **The decoupling is small; its consequence
is not.**

## ⚠️ A remedy that cannot fail is not a remedy

Whatever lands must be positive-controlled: after the change, show the check
**CONVICTING** on a repo where it previously scanned zero files, and show the count
matching that repo's independently-measured figure. **Exit status 0 is not evidence** —
that is the parent epic's founding lesson, and this thread inherits it.

## What this thread does NOT do

It does **not** drive `livespec-mutreal.1` or `bd-ib-6qb2mc`. Those remain valid for the
checks that genuinely need a pure-layer carve. This thread **removes the ROP check's
dependency on them**; it does not resolve them. Do not re-prioritise either item on this
thread's account — that would manufacture urgency from a coupling about to be deleted.

## Per-repo carve status — tracked here, owned elsewhere

`bd-ib-6qb2mc` (`livespec-orchestrator-beads-fabro`, P2, **human-gated**) is tracked as a
dependency of this thread rather than given its own plan thread, because **that repo
cannot currently land any PR**: open PRs fail `check-shell-quality` (the
`fleet-shell-quality-enforcement` peer lane) and master CI is red per `8o8e.22`. Opening a
doomed PR there would burn scarce runner minutes. Create a local thread there when the
repo can accept work again.

📜 **Worth recording: `bd-ib-6qb2mc` is the same defect class as the epic it was blocking.**
*"`pure_trees` is empty, so `check-pbt-coverage-pure-modules` scans ZERO files"* is exactly
*"the ROP check scans zero files in all nine repos"*, one key apart. **A role key that
resolves to nothing silently disarms whatever consumes it.** That shared shape is why this
thread asked the CLASS question across every real consumer rather than patching one — and the
answer came back ONE, which is a result rather than a miss.

## Relationship to other threads

- **`plan/rop-railway-enforcement`** — ON HOLD. `8zv3` **blocks** `8o8e` (dependency wired
  in the ledger). The ROP track resumes once the scan universe is decoupled.
- **`plan/mutation-testing-keystone`** — the `livespec-mutreal.1` blocker, temporarily
  housed in this repo. Independent of this thread after the decoupling.

## Open questions — TWO OF THREE ARE NOW ANSWERED

1. ✅ **ANSWERED: NO role gate is needed.** Of the **twenty** checks consuming
   `resolve_check_universe()`, **exactly one is role-gated — this check itself.** The other
   nineteen scan the first-party universe ungated. **So decoupling does not invent a
   pattern; it makes the outlier conform.** There is therefore **no new required key and no
   cross-repo schema epic** — the largest planned risk, retired.

   The spec's sole exemption (ZERO first-party Python) needs no expression: an empty
   universe is a documented legitimate "nothing to check", so `livespec-console-beads-fabro`
   passes with nothing declared.

   ⛔ **DO NOT "HELPFULLY" ADD A REPLACEMENT GATE.** A new declared key to express the
   zero-Python exemption would reintroduce the exact hazard this epic closes — a
   declaration whose emptiness means "skip me", indistinguishable from "genuinely no code".
   `resolve_check_universe()` already separates those: it OWNS root resolution (every
   `GIT_*` var stripped) and raises `GitToplevelError` / `GitLsFilesError` rather than
   returning a spuriously-empty walk. **Adding a gate back trades a fail-closed primitive
   for a fail-open declaration.**

2. ✅ **ANSWERED by the classification above: exactly one consumer is mismatched.**
   `check_mutation` and `pbt_coverage_pure_modules` genuinely need the key;
   `partition_completeness` and `source_trees_scoped_to_consumer` use it structurally
   without being scoped by it. **The class question was still worth asking — asking it is
   what proved the other four correct rather than assumed.**

3. ⬜ **STILL OPEN.** `check-shell-quality` and `check-doctor-static` currently freeze two
   of the nine repos (`livespec-orchestrator-beads-fabro`, `livespec`). Arming anything
   fleet-wide needs those clear first. **Verify landability per repo before pushing** —
   runner minutes are a first-class constraint.

4. ⬜ **NOW MEASURED AND FILED AS `8zv3.5` — it is 64% of the entire remediation.** The
   `_`-prefixed FILE skip is recorded as wider than the ratified rule (v178 clause 0
   disqualifies `_`-prefixed NAMES, not FILES) and is what keeps dev-tooling at 0.
   **`8zv3.5` BLOCKS `8zv3.4`**: the fan-out cannot be costed until it is settled.

## 📏 Fleet numbers — measured 2026-08-04, read-only, both bases

| repo | universe | **WITH** `_`-skip (shipped) | **WITHOUT** (epic basis) | skip's radius |
|---|---:|---:|---:|---:|
| `livespec-overseer` | 214 | **115** | **249** | **134** |
| `livespec-orchestrator-beads-fabro` | 186 | **17** | **157** | **140** |
| `livespec` | 145 | 12 | 20 | 8 |
| `livespec-runtime` | 31 | 12 | 12 | 0 |
| `livespec-orchestrator-git-jsonl` | 49 | 4 | 6 | 2 |
| `livespec-dev-tooling` | 177 | 0 | 1 | 1 |
| `livespec-driver-codex` | 7 | 0 | 1 | 1 |
| `livespec-driver-claude` | 7 | 0 | 0 | 0 |
| **TOTAL** | | **160** | **446** | **286** |

`160 = 115+17+12+12+4+0+0+0`. `446 = 249+157+20+12+6+1+1+0`. Arithmetic shipped with the
total, per `8o8e.17`.

⛔ **THE EPIC'S COST IS DOMINATED BY A DECISION THAT IS NOT PART OF IT.** Decouple with the
skip retained → the armed check convicts **~160**. Drop the skip too → **~446**. Budget,
sequencing and blast radius all move **~2.8x** on that one question. `8zv3.3` proceeds under
the **stated assumption that the skip is retained**.

✅ **The no-skip column corroborates independent measurements**: `livespec` **20** matches the
rop worker's harness-controlled 20 exactly; `livespec-dev-tooling` **1** matches its raw 1 on
the same function; `beads-fabro` **157** matches `8o8e.8`'s own-pin figure. **So every
recorded `8o8e.7`–`.13` figure is the NO-SKIP basis.**

⚠️⚠️ **THESE ARE NOT THE ARMED NUMBERS.** The repos are on **different dev-tooling pins** —
six at **1.17.1**, two at **1.18.7** — so each was evaluated by its own pinned criterion.
Operationally honest (it is what each CI would do today), but six different-versioned criteria
in one table, and **once the decoupling releases and `bump-pin` fans out, every repo is
re-evaluated by the NEW criterion. Re-measure per repo after the pin lands.** That pin spread
is also the fleet's known pin-currency defect showing up again: rows that fire correctly on
every stale member and gate nothing.

⚠️ Trees move fast — `livespec-overseer` measured universe **214** against `8o8e.7`'s recorded
**172**. **Quote the SHA.** Measured at: dev-tooling `3a9ed20`, livespec `d2501bc9`, overseer
`3bdb29a`, beads-fabro `f792496d`, git-jsonl `07a450c`, driver-codex `37472ae`;
`livespec-runtime` and `livespec-driver-claude` one commit behind master, both missing commits
verified to touch **zero** `.py`.

> ⚠️ **Every answer above is the supervisor's read-only analysis, recorded with its
> reproduction command. None has been independently verified. Re-derive before relying on
> it** — this thread's own rule, and the epic exists because a number nobody re-derived was
> believed for days.
