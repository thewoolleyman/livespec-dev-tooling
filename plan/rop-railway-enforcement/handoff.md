# rop-railway-enforcement — arm the check that was never armed, then remediate six repos

**Ledger anchor:** epic livespec-dev-tooling-8o8e

**Thread:** `plan/rop-railway-enforcement/` in **livespec-dev-tooling**
(`https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/plan/rop-railway-enforcement/handoff.md`)

Status is READ from the ledger, never from this file. Every live-state claim below expires in
minutes — re-derive before acting.

---

## ▶️ START HERE — one command, then one blocked push

The maintainer RULED (2026-07-27, relayed by the supervisor): **enforce the railway for real,
fleet-wide.** Build the mechanical check so "on the railway" means "actually composes on
Result/IOResult", then bring every non-conforming repo into compliance — including
`livespec-dev-tooling` itself. They chose this over scoping to new code only, and over narrowing
the spec clause to match current reality. Their reasoning: *this is the same disease the rop-sweep
just cured — a central requirement no check actually verifies.*

**Do NOT reach for a severity lever, a per-repo opt-in, or a declared-empty escape.** Every one of
those is a shape the rop-sweep spent days removing. `check-hook-trees-not-io-exempt` exists
because the exemption instinct keeps recurring.

**Your next action is `livespec-dev-tooling-pm4z`** — a two-site fix that is fully diagnosed and
mechanical. Read the item; it names both call sites and the exact predicate to apply. Then the
blocked push below goes through.

```bash
cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-pm4z
```

### THE ONE PIECE OF UNCOMMITTED WORK IN FLIGHT

A worktree exists with an authored, **push-blocked** commit:

| field | value |
|---|---|
| worktree | `~/.worktrees/livespec-dev-tooling/vendor-returns` |
| branch | `vendor-returns` (commit `085694c`) |
| contents | `dry-python/returns` 0.25.0 vendored into `livespec_dev_tooling/_vendor/returns/` (115 `.py` + LICENSE) + `.vendor.jsonc` entry |
| state | committed locally, **push REJECTED** by pre-push `just check` |
| blocker | `check-check-coverage-incremental` — site 1 of `pm4z` |
| after the fix | rebase onto master, `git push -u origin vendor-returns`, open the PR |

It is NOT abandoned and must NOT be reaped. Five OTHER `livespec-dev-tooling` worktrees are
FOREIGN — `git worktree list` before touching anything.

---

## 🔑 THE FINDING THAT REFRAMES THE EPIC

**The enforcing check was never missing. It exists, runs in CI in every repo, reports green in all
of them, and scans ZERO files in ALL NINE.**

`check-public-api-result-typed` is named BY the spec as the enforcer of §"ROP composition"'s
operative sentence — *"Every public function's `return` annotation MUST be `Result[_, _]` or
`IOResult[_, _]` ... Enforced by `check-public-api-result-typed` (AST)"*. Its `main()` gates on the
`pure_trees` role key and then iterates it. `_role_key_gate.role_key_gate_exit_code` returns **0**
for an empty declaration, logging *"role key declared empty — sanctioned opt-out"*.

**Every Python-bearing repo in the fleet declares `pure_trees = []`.** Live-run evidence, not
inference: `uv run python -m livespec_dev_tooling.checks.public_api_result_typed` exits 0 in both
`livespec-dev-tooling` and `livespec`, emitting only that info line — and `livespec` has 68 of 129
modules genuinely on the railway.

This is the **same dodge `i532` just closed**, still alive on the check that carries the clause.
`pure_trees` is a LAYERED-ARCHITECTURE role key (it means `parse/` + `validate/`), so a flat-layout
repo declares it empty *truthfully* — which is exactly why the gap is invisible. It is also
OVERLOADED: two of the three repos comment that their empty declaration is gated on
`livespec-mutreal.1` (mutation staging), so deferring the mutation concern disarmed the railway
check as a side effect nobody chose.

**The fix shape already exists and is already validated**: `config.resolve_check_universe()`
(`config.py:835`), the git-derived, fail-closed entry point the seven migrated `source_trees`
checks and `file_lloc` already use. Migrating `public_api_result_typed` to it is the move `i532`
made, and it keeps `pure_trees` as the genuine architectural marker it is.

Full detail is on `8o8e` as a dated note. Do not re-derive it.

---

## 📊 TRUE BLAST RADIUS — six repos, 245 functions (NOT "four repos")

Measured by simulating the post-migration check exactly (`resolve_check_universe()`, same
`_`-prefixed-file skip, the check's own `_find_offenders`). **The raw count is contaminated and
must be split before any severity decision** — the check does not implement the exemptions the
spec states, and its own docstring says the a–f exemptions are *"NOT yet wired in"*.

| repo | raw | −(a..f) | −(`-> None`) | **TRUE** |
|---|---|---|---|---|
| livespec-overseer | 58 | 4 | 2 | **52** |
| livespec-orchestrator-beads-fabro | 76 | 24 | 4 | **48** |
| livespec-dev-tooling | 61 | 12 | 2 | **47** |
| livespec-runtime | 46 | 3 | 0 | **43** |
| livespec | 55 | 20 | 6 | **29** |
| livespec-orchestrator-git-jsonl | 38 | 12 | 0 | **26** |
| livespec-driver-claude / -codex | 0 | – | – | **0** |
| livespec-console-beads-fabro | 0 | – | – | **0** (zero-Python; sanctioned exemption) |
| **FLEET** | **334** | **75** | **14** | **245** |

**Wiring the spec's own stated exemptions in is FIDELITY, not softening.** The "do not soften"
instruction binds severity levers, per-repo opt-ins, and declared-empty escapes. Shipping a check
that flags 75 supervisor `main()` functions the spec explicitly exempts would be a defect, and
would burn the rollout's credibility on false positives.

Two corrections to the epic's original premise, both now on the item:

1. **Six repos, not four.** The original count was of repos that do not VENDOR `returns`. That is
   a different set from repos with offenders: `livespec` (29) and `livespec-orchestrator-beads-fabro`
   (48) vendor it and are among the worst; `livespec-driver-codex` does not vendor it and has ZERO.
2. **`livespec-driver-claude` and `livespec-driver-codex` are already clean** and are not in the
   remediation set.

Reproduce with the script recorded in `8o8e`'s design notes. Re-measure with the CHANGED check
before arming anything — never against these numbers.

---

## 🧭 THE SEQUENCE — each PR green on its own, no lever anywhere

`livespec-dev-tooling` runs `check-public-api-result-typed` on ITSELF (`justfile:247`). So arming
the check turns its own `just check` red on 47 offenders, and `lefthook` then blocks the very
commit that would fix it. The remediation of dev-tooling is a **precondition** of the hardening,
not a follow-up.

1. ✅ **DONE** — `hh4d`: `check-commit-pairs-source-and-test` excluded `_vendor` (PR #739, merged).
   Promoted the rule to the public `config.is_vendored_path`.
2. ⬅️ **NEXT** — `pm4z`: two remaining `_vendor` sites (`check_coverage_incremental` confirmed,
   `red_green_replay` latent).
3. **Then** — push/merge the `vendor-returns` branch described above.
4. **Then** — convert dev-tooling's 47 public functions onto the railway. Verify against the
   SIMULATED post-migration predicate, never the currently-vacuous check.
5. **Then** — migrate `public_api_result_typed` to `resolve_check_universe()` AND wire the a–f +
   `-> None` exemptions. dev-tooling is at zero by then, so it lands green.
6. **Then** — siblings, one repo per PR, ascending: git-jsonl (26), livespec (29), runtime (43),
   orchestrator-beads-fabro (48), overseer (52).

Step 5 is the fleet-visible moment: on release, `bump-pin` fans the new dev-tooling to every
sibling, so all five go red on their next pin bump. That is the intended consequence of enforcing
for real — but it makes steps 5–6 a coordinated cross-repo epic with per-repo children, not
independent PRs.

**Implementation runs factory-side** — the Dispatcher drains `ready` items, or an operator runs
the `drive` operation (`impl:<id>`). Do not hand-code these conversions in a planning session.

---

## 🕳️ THE PATTERN THIS THREAD KEEPS FINDING

Four instances in one session of ONE shape — **machinery that is correct for consumers and inert
or wrong for the repo that owns it**:

1. `check-public-api-result-typed` — scans zero files in all nine repos (`8o8e`).
2. `check-plan-thread-anchor-declared` — armed ONLY in the one repo with zero plan threads
   (`livespec-dev-tooling-pk2x`); 18 of 20 fleet handoffs would fail it.
3. `vendor_update` — the "only blessed re-vendor path" hardcodes `.claude-plugin/scripts/_vendor/`
   and cannot target dev-tooling's own `_vendor/` tree (`livespec-dev-tooling-w25v`).
4. `_vendor` exclusion applied by `filter_first_party_py`, ruff and pyright but NOT by three
   staged-diff checks (`hh4d` fixed, `pm4z` open).

When you find the next one, file it rather than fixing it inline — a same-shaped hole found while
fixing another is the cheapest it will ever be to close, and the pattern is the finding.

---

## ⚠️ TRAPS PAID FOR IN THIS SESSION

- **A fresh worktree fails `check-primary-checkout-commit-refuse-hook-installed`** with
  `failure_mode: worktree_pack_absent`. Run `just install-worktree-pack` in the new worktree
  BEFORE the first commit. It cost two failed commit attempts here.
- **`just check` passing does NOT mean a commit will land.** The staged-diff checks
  (`commit-pairs`, `red-green-replay`) run only at commit/push time over the STAGED set. The
  vendoring passed 64/64 in the working tree and was still rejected at commit, then again at push.
- **A grep for "which checks lack a vendor exclusion" returns a 19-module SUPERSET** and is not a
  work list: most derive their universe transitively via `resolve_check_universe`. The tight bound
  is empirical — with the vendored tree present, 63 of 64 targets passed.
- **`pure_trees = []` is documented and honest in every repo.** Do not read the comments as
  admissions of an oversight; two explicitly say "NOT an oversight". The defect is the category
  error (an architectural role key used as a check universe), not anyone's declaration.

## 📋 OPEN ITEMS FILED BY THIS THREAD

`pm4z` (P1, next) · `hh4d` (P1, DONE) · `w25v` (P2) · `8o8e` (P1 epic, this thread's anchor) ·
`pk2x` (P1 epic, livespec-dev-tooling — plan-anchor enforcement; Q1 answered on the item, and the
disposition is that arming it fleet-wide means ADOPTING the Archive-on-epic-close conformance
member, which the five-slot rule says requires all five slots filled).
