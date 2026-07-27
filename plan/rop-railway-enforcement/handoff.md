# rop-railway-enforcement — arm the check that was never armed, then remediate six repos

**Ledger anchor:** epic livespec-dev-tooling-8o8e

**Thread:** `plan/rop-railway-enforcement/` in **livespec-dev-tooling**
(`https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/plan/rop-railway-enforcement/handoff.md`)

Status is READ from the ledger, never from this file. Every live-state claim below expires in
minutes — re-derive before acting.

---

## ▶️ START HERE — this thread is BLOCKED on a schema fix, and may not close without it

The maintainer RULED (2026-07-27): **enforce the railway for real, fleet-wide.** Build the
mechanical check so "on the railway" means "actually composes on Result/IOResult", then bring every
non-conforming repo into compliance — including `livespec-dev-tooling` itself. Their reasoning:
*this is the same disease the rop-sweep just cured — a central requirement no check actually
verifies.*

**Do NOT reach for a severity lever, a per-repo opt-in, or a declared-empty escape.** Every one of
those is a shape the rop-sweep spent days removing. `check-hook-trees-not-io-exempt` exists because
the exemption instinct keeps recurring.

**Your next action is `livespec-dev-tooling-8o8e.1`, and its first deliverable is a CLASSIFICATION,
not a code change.** Read the item first — the full ruling is there, and the ledger is authoritative
over this file:

```bash
cd /data/projects/livespec-dev-tooling && /usr/local/bin/with-livespec-env.sh -- bd show livespec-dev-tooling-8o8e.1
```

### 🛑 CLOSURE PRECONDITION — read before planning anything else

**Neither `8o8e` nor THIS PLAN THREAD may close until `8o8e.1` is fixed FLEET-WIDE and VERIFIED**
(maintainer-declared 2026-07-28). "Verified" means per-repo evidence that the ambiguous spelling is
rejected and each repo declares the correct variant — **not** a green check in one repo. This is a
blocking precondition on closure, not a follow-up.

### 🛑 A SUPERSEDED AUTHORIZATION — do NOT implement the weaker fix

An earlier supervisor authorization said the `pure_trees` fix "cannot be reject-empty, it must be
that emptiness stops implying scan-nothing". **The maintainer superseded that.** It removes THIS
INSTANCE while leaving the ambiguity REPRESENTABLE, so the next key or the next reader re-creates
the bug. The ruling is a TYPE-SYSTEM fix: a flat-layout repo declares a **different type**, not an
empty array, encoded as a discriminated union parsed into distinct Python types at the config
boundary. A bare `[]` becomes a hard load-time ERROR naming both blessed spellings.

**State the guarantee precisely — overclaiming it is its own defect.** TOML has no sum types, so
nothing stops a person TYPING `[]` into the file. What the design buys is: the ambiguity is
**unrepresentable after parsing**, and ambiguous input **fails loud at load** instead of succeeding
silently as "scan nothing". Say that; do not say "impossible to express".

`check-newtype-domain-primitives` and `check-assert-never-exhaustiveness` already exist in this
fleet and make it cheap: once the union is a real type, pyright strict + `assert_never` force EVERY
consumer to handle both variants explicitly.

### ⛔ DO NOT COMMIT TO A REMEDIATION SHAPE BEFORE THAT CLASSIFICATION LANDS

This epic's remediation of six repos / 245 functions runs THROUGH the role-key loader `8o8e.1`
changes. Taking arming decisions now means taking them against a schema about to move underneath
them. Classify first, then design.

`8o8e.1` is also a **required-key schema change**, which this fleet treats as a cross-repo EPIC:
it must backfill all eight Python-bearing repos in the SAME epic, harden-first, and **no loader
that rejects the ambiguous spelling lands until every consumer has migrated**.

### ✅ NOTHING IS IN FLIGHT

Every worktree and branch this thread created is reaped; `livespec-dev-tooling` is clean on
`master`. Five OTHER `livespec-dev-tooling` worktrees are FOREIGN — run `git worktree list` before
touching anything, and reap none of them.

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

**⚠️ THESE NUMBERS ARE NOW KNOWN STALE — and stale in the direction that UNDERSTATES the work.**
PR #748 implemented the exemptions LITERALLY, including their path scoping: the spec grants the
`main()` exemption to a LOCATION (`commands/*.py`, `doctor/run_static.py`), not to a name, and
`build_parser` only under `commands/**.py`. A flat-layout repo declaring no commands tree therefore
gets NO `main()` exemption at all. The `−(a..f)` column above subtracted 75 `main()`/`build_parser()`
hits fleet-wide as though the exemption were unscoped, so the TRUE counts are **higher** than the
245 shown.

Do not plan against this table. Re-measure with the CHANGED check — and only after `8o8e.1` lands,
since the role-key loader those measurements run through is about to move. Reproduce with the
script recorded in `8o8e`'s design notes.

---

## 🧭 THE SEQUENCE — each PR green on its own, no lever anywhere

`livespec-dev-tooling` runs `check-public-api-result-typed` on ITSELF (`justfile:247`). So arming
the check turns its own `just check` red on 47 offenders, and `lefthook` then blocks the very
commit that would fix it. The remediation of dev-tooling is a **precondition** of the hardening,
not a follow-up.

1. ✅ **DONE** — `hh4d`: `check-commit-pairs-source-and-test` excluded `_vendor` (PR #739).
   Promoted the rule to the public `config.is_vendored_path`.
2. ✅ **DONE** — `pm4z`: the two remaining `_vendor` sites (PR #743) plus the adjacent
   empty-after-filter edge they exposed (PR #746). CLOSED.
3. ✅ **DONE** — `dry-python/returns` 0.25.0 vendored into `livespec_dev_tooling/_vendor/`
   (PR #746). The enforcement suite can now compose on the railway at all.
4. ✅ **DONE** — the spec's stated exemptions wired into `public_api_result_typed` (PR #748).
   Behavior today is unchanged, because the check is still `pure_trees`-scoped and scans zero
   files — this is the harden-first prerequisite, landed green.
5. ⬅️ **NEXT — `8o8e.1`, classification FIRST.** Enumerate EVERY role key and classify which
   genuinely carry two meanings versus one. Report before touching loaders. Fix the CLASS, not the
   instance. Then the discriminated-union design, then the cross-repo migration.
6. **Then** — arm `public_api_result_typed` on the git-derived universe, and RE-MEASURE. The
   counts below are now KNOWN STALE (see the warning under the blast-radius table).
7. **Then** — remediate repo by repo, each landing green on its own.

### 📌 ALSO ADOPTED, AND SHARING THIS DESIGN — Archive-on-epic-close (`pk2x`)

The maintainer RULED (2026-07-28) to **ADOPT** the Archive-on-epic-close conformance member now:
fill the unfilled Mechanism, Installer and Exemption slots, WITH the explicit declared opt-out the
Conformance Pattern requires. Two binding constraints, both on `pk2x`:

- **A repo that has NOT SPOKEN is NOT exempt — it is non-conforming and must say so in its own
  config.** That is the entire difference between this adoption and the status quo, and it is the
  part that will be tempting to soften during rollout.
- **Harden-first**: land the Mechanism and its correct severity, measure the true blast radius
  across all eight repos, THEN remediate.

**The Exemption slot is the trap.** Design it as a DECLARATION a repo actively writes with a stated
reason — never a default, an absence, or an empty value that reads as consent. *Every dodge this
sweep found was an emptiness that meant yes.*

**Sequencing chosen: `8o8e.1` first, then `pk2x`'s Exemption slot, designed to match.** They are the
same disease — an emptiness or absence that silently means consent — and `8o8e.1`'s discriminated
union establishes the declaration idiom (`not-applicable` as an ACTIVE spelling with a reason)
that `pk2x`'s Exemption slot should reuse rather than reinvent. Doing `pk2x` first would mean
designing that idiom twice, and the second design would have to migrate the first.

Note also: `pk2x`'s **18-of-20 figure must be RE-DERIVED after the regex fix** — the current count
is contaminated by bold-wrapped-id false positives, and a decision taken against a contaminated
count is taken against a wrong number.

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

| item | state | what |
|---|---|---|
| `8o8e` | OPEN, epic | This thread's anchor. **Cannot close until `8o8e.1` is fleet-wide fixed AND verified.** |
| `8o8e.1` | **OPEN, P1 — NEXT** | Role-key schema type-safety. Classification first, then the union, then cross-repo migration. |
| `pk2x` | OPEN, P1 | Archive-on-epic-close — **ADOPT** ruling recorded. Sequenced after `8o8e.1`. |
| `i04f` | OPEN, P2 (livespec) | Spec states the Result-return rule twice with incompatible exemption sets. Needs ratification. |
| `w25v` | OPEN, P2 | `vendor_update` hardcodes the plugin layout; cannot vendor into this repo's own tree. |
| `j5i9` | OPEN, P1 (livespec) | The cross-cutting FINDING: the repo that enforces the fleet is systematically the least enforced. |
| `hh4d`, `pm4z` | CLOSED | The `_vendor` exclusion sweep. |

Ledger status is authoritative over this table — read it, do not trust this file.
