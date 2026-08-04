---
topic: pure-trees-scan-universe-decoupled
author: claude-opus-5
created_at: 2026-08-04T11:58:38Z
---

## Proposal: `public_api_result_typed` no longer consumes `pure_trees`

### Target specification files

- SPECIFICATION/contracts.md

### Summary

`public_api_result_typed` stopped consuming the `pure_trees` role key when its
scan universe was decoupled from that key. `contracts.md` still describes the
old coupling in two places, and both statements are now false about shipped
behavior. This proposal corrects them and records what replaced the gate.

Two sites are affected, and neither is a wording preference — each asserts a
mechanical fact a reader can check and get the wrong answer to today.

### Motivation

The check enforces the ROP railway rule, which `livespec`
`SPECIFICATION/non-functional-requirements.md:114` binds to **every repo
carrying ANY first-party Python**, with **NO "thin repo" exemption** and the
**SOLE exemption** being **ZERO first-party Python**. `pure_trees` selects a
different set — "has this repo carved a pure-module subtree?" — so gating the
scan universe on it bound a criterion the rule never names. The effect was not
cosmetic: a repo declaring `pure_trees` absent exited 0 having read no files at
all, while remaining fully bound by the rule.

The decoupling landed in `46c5dab`. Since then the two `contracts.md` statements
below have described a coupling the code does not have.

**Measured 2026-08-04 against master, so the corrected text is derived rather
than argued:**

- AST code references to `pure_trees` in the shipped check — counting
  `config.pure_trees` attribute reads and the literal `"pure_trees"` key:
  **none**. No attribute reads, no string keys.
- `livespec-dev-tooling` under the shipped check: exit 0, scanning **93** files
  of universe **177** (the difference is the retained `_`-prefixed FILE skip).
  Before the decoupling it scanned **zero**.
- Declared-absent no-op entries on a default `just check` run: **three**, one
  each from `pbt_coverage_pure_modules`, `newtype_domain_primitives` and
  `no_shadow_ledger_body_identical`. `public_api_result_typed` emits none
  because it no longer gates; `check_mutation` emits none because it
  short-circuits on `LIVESPEC_RUN_MUTATION` before reaching its gate.

The two checks that DO still gate on `pure_trees` — `pbt_coverage_pure_modules`
and `check_mutation` — genuinely need it: one's subject IS the pure-layer test
modules, the other mutates the pure logic. The key keeps its meaning; only the
check whose rule bound a different scope stopped consuming it.

### Proposed Changes

**1. The `pure_trees` key description (`contracts.md`, the `pure_trees` bullet
in §"Consumer configuration schema" → §"Role keys").**

Current text states the key is "consumed by `public_api_result_typed`,
`pbt_coverage_pure_modules` and `check_mutation`, each of which gates on it;
`public_api_result_typed` uses it to assert every public callable returns
`Result` / `IOResult`."

Replace the consumer list with the two remaining consumers,
`pbt_coverage_pure_modules` and `check_mutation`, and state that each gates on
it. Remove the clause attributing the `Result` / `IOResult` assertion to this
key. Record, in the same bullet, that `public_api_result_typed` enforces that
assertion over the git-derived first-party set from `resolve_check_universe()`
rather than over `pure_trees`, because the rule it enforces binds first-party
Python rather than a pure-module subtree.

**2. The `livespec-dev-tooling` self-application bullet (`contracts.md`,
§"Per-consumer pyproject declarations").**

Current text groups `public_api_result_typed` with `pbt_coverage_pure_modules`
and `check_mutation` as "all gating on `pure_trees`", says each "no-ops as the
sanctioned opt-out and records that in a structured `info` entry", and
concludes that "a default `just check` run shows four such entries rather than
five."

Move `public_api_result_typed` out of that group. It no longer gates on
`pure_trees` and no longer no-ops for this library — it scans the first-party
universe here, as the three ungated checks in the same bullet already do.
Correct the count from **four** to **three**, keeping the existing explanation
that `check_mutation` is absent from a default run because it short-circuits on
`LIVESPEC_RUN_MUTATION` before reaching its gate.

The bullet's governing observation should be preserved and is strengthened by
this change: the grouping follows from WHICH key each check gates on, not from
membership of any list. `public_api_result_typed` moving groups is that rule
being applied, not an exception to it.

**No replacement key is proposed, deliberately.** An empty universe is already a
legitimate "nothing to check", and `resolve_check_universe()` fails closed — it
owns root resolution and raises rather than returning a spuriously-empty walk. A
new declared key expressing the zero-first-party-Python exemption would
reintroduce the hazard this change closes: a declaration whose emptiness means
"skip me", indistinguishable from "genuinely no code".

### Provenance

Filed from plan thread `plan/pure-trees-role-key-scope`, ledger epic
`livespec-dev-tooling-8zv3`, whose children `8zv3.2` and `8zv3.3` closed with
the decoupling in `46c5dab`.

The drift is a CONSEQUENCE of that change rather than a pre-existing defect: both
statements were true when written and were falsified by the commit that fixed the
check. It surfaced while correcting a stale docstring inside the check module —
the same defect one layer down, where a warning about the removed gate still read
as live.

`SPECIFICATION/history/` carries the superseded wording in `v003`–`v005` and is
correctly frozen; those copies are historical snapshots and are not touched.
