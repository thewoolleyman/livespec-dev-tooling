# rop-sweep-library-checks — make scope-hardcoded checks config-driven + add a drift-guardrail

**Archived:** 2026-07-17. This thread is complete and was moved from
`plan/rop-sweep-library-checks/` to `plan/archive/rop-sweep-library-checks/`
per the plan-thread lifecycle rule that closed threads do not remain in the
active `plan/<topic>/` set.

**Closure evidence:** implemented and merged through PR
[#420](https://github.com/thewoolleyman/livespec-dev-tooling/pull/420).
The PR rebase-merged at `2026-07-16T09:55:27Z`; merge commit
`3de4223dc105203d5dd05b6b985ca7e400bdc180` is on `master`.

**Ledger note:** this drafted plan did not carry a ledger epic anchor. That was a
lifecycle miss in the original thread setup; do not treat this file as a status
source. The implementation status is the merged PR above and the active plan
inventory excludes this archived directory.

---

**Part of the `rop-sweep-*` coordinated set (do these ASAP, together).** Sibling
plans, findable fleet-wide via `plan/rop-sweep-*`:
- **`rop-sweep-consumer-cleanup`** (in `livespec-orchestrator-beads-fabro`) — the
  drifted consumer's catch-up; **its Phase 3 depends on this plan landing.**
- **`rop-sweep-fleet-policy`** (in `livespec` core) — fleet enforcement audit, the
  Ruff `BLE` policy, and the scaffold-template fix.

Authored 2026-07-16 from a read-only audit. This was the
`livespec-dev-tooling` (shared enforcement library) slice: fixes that benefit
**every** consumer, not just the one that surfaced them.

---

## Why this is a fleet-wide (library) concern, not a consumer concern

A consumer scopes most checks by declaring source-tree paths in its own
`pyproject.toml` `[tool.livespec_dev_tooling]` block — `no_inheritance` and the
rest read `config.source_trees` / `config.resolve_check_universe()`. But **six
checks hardcode `.claude-plugin/scripts/livespec` (core's package name) as a
module-level constant**, so no consumer's config can re-scope them. For any
consumer whose package is not literally named `livespec`, these six walk a
nonexistent tree and enforce nothing — and no per-repo fix is possible. This is
invisible in core (its package *is* `livespec`) and even in a
correctly-configured consumer like `git-jsonl` (its config is right, but these
six ignore config). The fix must live here, in the library.

Separately, the whole drift class — a consumer copying core's layout at scaffold
time and never re-pointing `source_trees` at its own package — has **no guardrail
today**. `livespec-orchestrator-beads-fabro` drifted exactly this way and nothing
caught it. A new library check closes that gap for the fleet.

---

## Part A — make the six scope-hardcoded checks config-driven

Each of these bakes the scope as a constant instead of reading `config`:

| Check | Hardcoded constant (this repo) | Current effect off-`livespec` |
| --- | --- | --- |
| `supervisor_discipline.py:46` | `_LIVESPEC_TREE = .claude-plugin/scripts/livespec` | DORMANT |
| `main_guard.py:50` | `_LIVESPEC_TREE` | WARN-only classifier never matches |
| `rop_pipeline_shape.py:44` | `_LIVESPEC_TREE` | WARN-only classifier never matches |
| `tests_mirror_pairing.py:45` | `_SOURCE_TREES_TO_TESTS` dict (keyed on `…/livespec`) + `:50` `_BOOTSTRAP_REL` | misses the consumer's real package |
| `pbt_coverage_pure_modules.py:41` | `_PURE_TEST_TREES = (tests/livespec/parse, …/validate)` | DORMANT + N/A |
| `check_mutation.py:1,5,42` | prose + `paths_to_mutate` = `livespec/parse` + `validate` | DORMANT + N/A |

**The template already exists in-repo.** `no_inheritance.py` (and its siblings)
read scope via `config.resolve_check_universe()` + `is_under_any_tree(...,
config.source_trees)` (see `no_inheritance.py:16,25,55`). The fix is to make each
of the six resolve its scope the same way:

- **`supervisor_discipline`, `main_guard`, `rop_pipeline_shape`** — replace the
  `_LIVESPEC_TREE` constant with the git-universe + `config.source_trees`
  classifier the other checks use. These have a direct analog in every consumer
  (a `commands/` supervisor layer, a `main()` guard, ROP pipelines), so they
  become live-and-correct in every repo.
- **`tests_mirror_pairing`** — drive the source→tests map from
  `config.source_tree_prefixes` + `config.tests_tree_prefix` (+ `mirror_pairings`)
  instead of the hardcoded `_SOURCE_TREES_TO_TESTS` dict.
- **`pbt_coverage_pure_modules`, `check_mutation`** — these target a pure
  `parse`/`validate` layer that not every consumer has. Give them a
  `config.pure_trees`-driven scope AND the graceful "role key absent/empty →
  structured no-op → exit 0" guard the config-driven checks already use, so a
  consumer without a pure layer is a clean N/A rather than a dead hardcode.

**Rollout: two-tier, phased — do not flip every consumer at once.** Adopt the
existing phase-0-WARN → phase-2-ERROR pattern (`no_inheritance` is the reference:
hard `error` for files under the resolved source trees, `warning` for files only
in the git universe). On the version bump, consumers first see WARN, fix, then a
later minor flips ERROR. This prevents the pin bump from turning every consumer
red simultaneously.

---

## Part B — add a drift-guardrail check (highest-value fleet addition)

**New check: `source_trees_scoped_to_consumer` (name TBD).** Assert that every
path a consumer declares in `source_trees` / `io_trees` / `commands_trees` /
`pure_trees` / `covered_trees` / `source_tree_prefixes` actually **exists in the
repo** and resides under the consumer's own package — i.e. is not a stale
`.claude-plugin/scripts/livespec` inherited from core when the consumer's package
is named otherwise.

- **Detection:** for each declared tree path, fail if the directory does not exist
  (git-tracked), or if it names core's `livespec` package while the repo's actual
  `.claude-plugin/scripts/<pkg>/` is a different `<pkg>`. Core (package =
  `livespec`) passes; a correctly re-pointed consumer passes; a drifted consumer
  (this is exactly `beads-fabro`) fails loudly.
- **Why it matters:** this is the check that would have prevented the entire
  `rop-sweep-consumer-cleanup` situation. A present-but-dead config key currently
  defeats every other check's "role key absent → no-op" guard silently; this check
  turns that silent dormancy into a loud failure.
- **Model:** a repo-root-scoped structural check (like `wrapper_shape` /
  `vendor_manifest`), reading `load_config` + `resolve_repo_root`; structured
  `structlog` JSON to stderr; paired test under `tests/livespec_dev_tooling/checks/`
  (mirror-pairing invariant).

---

## Rollout / coordination

1. Land Part A (config-driven, phase-0-WARN) + Part B (the guardrail) behind a
   minor version bump.
2. Announce to consumers; each bumps its `livespec-dev-tooling` pin. The guardrail
   immediately flags any drifted consumer (WARN first).
3. `rop-sweep-consumer-cleanup` Phase 3 consumes this: after `beads-fabro` bumps
   the pin, the six checks read its (re-pointed) config and enforce correctly.
4. A later minor flips Part A's WARN → ERROR fleet-wide once consumers are clean.

## Decisions for the implementing session

1. **`pbt_coverage`/`check_mutation` scope:** config-drive via `pure_trees` with a
   graceful no-op (recommended) vs leave hardcoded (rejected — perpetuates the
   dormancy).
2. **Guardrail strictness:** fail on *nonexistent path* only (minimum) vs also
   fail on *foreign-package path* (recommended — catches the `livespec`-in-a-
   non-`livespec`-repo drift directly).
3. **Phase-0 vs immediate ERROR:** phased WARN→ERROR (recommended, matches
   `no_inheritance`) vs hard flip (rejected — breaks every consumer on the bump).

## Evidence / references (file:line — this repo)

- Hardcoded constants: `livespec_dev_tooling/checks/supervisor_discipline.py:46`,
  `main_guard.py:50`, `rop_pipeline_shape.py:44`, `tests_mirror_pairing.py:45,50`,
  `pbt_coverage_pure_modules.py:41`, `check_mutation.py:1,5,42`.
- Config-driven template to copy: `livespec_dev_tooling/checks/no_inheritance.py:16,25,55`
  (`resolve_check_universe` + `is_under_any_tree` + `config.source_trees`).
- Config surface: `livespec_dev_tooling/config.py` (`load_config`,
  `resolve_check_universe`, `resolve_repo_root`, the role-key dataclass).
- Consumer symptom that motivates this: `rop-sweep-consumer-cleanup` in
  `livespec-orchestrator-beads-fabro`.
