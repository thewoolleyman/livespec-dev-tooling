# pure-trees-role-key-scope

> **Ledger epic:** `livespec-dev-tooling-8zv3` (P1). The ledger is authoritative
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

`pure_trees` is a **shared role key consumed by seven checks**, and because the ROP
railway check gates on it, that check inherits the carve-status of a subtree it does
not need — leaving it scanning **zero files in all nine repos**.

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

**The seven consumers** (`grep -rln pure_trees livespec_dev_tooling/`): `check_mutation`,
`pbt_coverage_pure_modules`, `public_api_result_typed`, `partition_completeness`,
`source_trees_scoped_to_consumer`, `_import_resolution`, `_single_meaning_variants`,
plus `fleet/_rows_public_api_conformance`.

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

## ⛔ Sequencing is not optional — the ordering trap

`livespec-dev-tooling` runs this check on **itself** (`justfile:206`, `:730`). Arming it
turns its own `just check` red, and `lefthook` then blocks the very commit that would
fix it. **Remediating dev-tooling is a PRECONDITION of arming, not a follow-up.** Then
per-repo remediate → arm. One coordinated cross-repo fan-out, not eight independent PRs.

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
thread treats `pure_trees` as a CLASS problem across its seven consumers rather than
patching one.

## Relationship to other threads

- **`plan/rop-railway-enforcement`** — ON HOLD. `8zv3` **blocks** `8o8e` (dependency wired
  in the ledger). The ROP track resumes once the scan universe is decoupled.
- **`plan/mutation-testing-keystone`** — the `livespec-mutreal.1` blocker, temporarily
  housed in this repo. Independent of this thread after the decoupling.

## Open questions for whoever picks this up

1. Does the ROP check need **any** role gate after decoupling, or does it simply always
   scan the first-party universe? If it needs one, that is a new role key and therefore a
   required-key schema change — a cross-repo epic with harden-first discipline.
2. Do the other six consumers each genuinely need `pure_trees`, or is more than one of
   them a scope mismatch too? **The class question is the valuable one.**
3. `check-shell-quality` and `check-doctor-static` currently freeze two of the nine repos.
   Arming anything fleet-wide needs those clear first.
