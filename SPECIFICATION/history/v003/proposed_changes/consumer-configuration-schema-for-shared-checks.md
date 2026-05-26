---
topic: consumer-configuration-schema-for-shared-checks
author: claude-opus-4-7
created_at: 2026-05-25T19:55:00Z
---

## Proposal: consumer-configuration-schema-for-shared-checks

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

Declare a per-consumer configuration schema at `pyproject.toml` `[tool.livespec_dev_tooling]` that every shared check MUST read at startup to learn the consumer's source-tree layout. The schema is the single source of truth for layout-dependent paths (replacing the historical hardcoded `_LIVESPEC_TREE = Path(".claude-plugin") / "scripts" / "livespec"`-style constants that match livespec-core's layout only). Each consumer (livespec-core, livespec-dev-tooling self-application, livespec-impl-plaintext, future siblings) publishes its own block; checks fall back to livespec-core's historical defaults when no block is present so the v0.x line stays backward-compatible.

Codifies the design sketched in work-item `li-asybpo` (filed 2026-05-21) — the path-portability refactor that unblocks (a) restoring `[tool.coverage.report].fail_under = 100` and the three previously-skipped layout-coupled tests, (b) this library's own self-application of every shared check per `constraints.md` §"Self-application", and (c) every livespec-impl-* consumer running the shared checks against its own non-livespec-core layout. Acceptance criterion #3 of li-asybpo landed via `livespec-dev-tooling` PR #11 (commit `d63be8d`, released as v0.2.1); the remaining criteria #1, #2, #4, #5 all hinge on this schema.

### Motivation

Phase G.4 of livespec epic `li-fgqgnk` migrated 34 shared checks AS-IS from `livespec/dev-tooling/checks/` to `livespec_dev_tooling/checks/`. Their hardcoded path constants — `_LIVESPEC_TREE`, `_IO_TREE`, `_COMMANDS_TREE`, `_DATACLASSES_TREE`, `_DOCTOR_RUN_STATIC`, `_PURE_TREES`, `_COVERED_TREES`, `_SOURCE_TREE_PREFIXES`, `_TARGET_DIRS` — match livespec-core's `.claude-plugin/scripts/livespec/` layout exactly. Every other consumer (livespec-dev-tooling's own flat `livespec_dev_tooling/` package layout, livespec-impl-plaintext's plugin-shaped layout, future siblings with arbitrary layouts) gets silent-no-op behavior from any check whose default tree doesn't exist in that consumer's layout. Silent-no-op is the worst failure mode for an enforcement gate: the consumer's `just check` passes green while the gate is asserting nothing.

The work-item's design sketch prescribes the high-level direction: each consumer's `pyproject.toml` declares its layout under `[tool.livespec_dev_tooling]`; every shared check reads it at startup with fallback to livespec-core defaults. This proposal codifies that design into a precise schema, an explicit role-key inventory, and the loader contract.

The contract MUST land before the per-check refactor. Three things hinge on the schema being settled before any check is rewritten: the role-key naming (so 34 PRs land against a stable target), the fallback semantics (so livespec-core's `just check` stays bit-identical to its pre-G.6 baseline per acceptance criterion #5), and the partition between "consumer-configurable via the schema" (most checks) vs "consumer-private" (re-classified back to livespec-core via the existing `Shared check inventory` carve-out criterion). Without the contract, each check's PR would re-litigate these decisions and the migration would fork.

### Proposed Changes

Add a new H2 §"Consumer configuration schema" to `contracts.md` between the existing §"Shared check inventory" (lines 28-36) and §"Composite Actions wire contract" (line 38). The new section codifies the schema, the role-key inventory, the loader contract, and the per-consumer declaration discipline.

#### New section to add to `contracts.md`

```markdown
## Consumer configuration schema

Every shared check that depends on the consumer's source-tree layout MUST read its layout-dependent paths from a `[tool.livespec_dev_tooling]` block in the consuming repo's `pyproject.toml`. The schema is the single source of truth for layout configuration; checks MUST NOT hardcode consumer-specific path constants. Missing keys MUST fall back to livespec-core's historical defaults (codified in §"Default layout fallback" below) so v0.x is backward-compatible — livespec-core's `pyproject.toml` MAY omit the block entirely and keep its bit-identical pre-G.6 behavior.

### Schema location

The schema MUST live at `[tool.livespec_dev_tooling]` in the consumer's root `pyproject.toml`. The library MUST NOT support alternate file locations (no `.livespec.jsonc` fallback, no env-var override). A single, well-known location simplifies the loader and matches the convention every other Python tool (`ruff`, `pyright`, `pytest`, `coverage`) uses for project configuration.

### Role keys

The schema declares roles, not paths-per-check. A role is a layered semantic about the consumer's source tree (e.g., "the I/O layer where `try/except` is wholesale allowed"); each role maps to one or more paths relative to the consumer's repo root. Checks consume roles, not individual paths.

The role-key inventory:

- **`source_trees`** — array of strings. Repo-root-relative paths each shape-checking check walks for `.py` files. Required for every check in the AST-shape family (`assert_never_exhaustiveness`, `keyword_only_args`, `match_keyword_only`, `no_inheritance`, `all_declared`, `main_guard`, `private_calls`, `global_writes`), the style family (`comment_line_anchors`, `no_lloc_soft_warnings`, `claude_md_coverage`), and the test-infrastructure family (`pbt_coverage_pure_modules`, `no_todo_registry`).

- **`io_trees`** — array of strings. Subset of `source_trees` where `try/except` is wholesale permitted (the "I/O layer" of the ROP architecture per `livespec/SPECIFICATION/non-functional-requirements.md` §"ROP discipline"). Consumed by `no_except_outside_io`, `no_raise_outside_io`, `public_api_result_typed`, `no_write_direct`. Default empty array — for consumers with a flat (non-layered) Python package, no `try/except` is wholesale exempt; the supervisor-bug-catcher exemption (via `supervisor_entry_files`) still applies.

- **`commands_trees`** — array of strings. Subset of `source_trees` whose direct-child `main()` `try/except` block is exempt (the "command supervisor" layer per the ROP architecture). Consumed by `no_except_outside_io`, `no_write_direct`. Default empty array.

- **`supervisor_entry_files`** — array of strings. Repo-root-relative `.py` files whose `main()` direct-child `try/except` is exempt — narrower than `commands_trees` (file-level, not directory-level). Consumed by `no_except_outside_io`. Default empty array.

- **`dataclasses_tree`** — string or null. Repo-root-relative path to the dataclass-definition tree the `newtype_domain_primitives` check walks. When null, the check no-ops on this consumer (it's a layered-domain-modeling property that not every consumer has). Default null.

- **`pure_trees`** — array of strings. Subset of `source_trees` containing the pure ROP-railway-typed layer; consumed by `public_api_result_typed` to assert every public callable returns `Result` / `IOResult`. Default empty array.

- **`covered_trees`** — array of strings. Subset of `source_trees` to which `no_write_direct` and `no_lloc_soft_warnings` ceiling-rules apply. Default empty array.

- **`source_tree_prefixes`** — array of strings, each ending in `/`. Used by `commit_pairs_source_and_test` to recognize a staged file as "source" (vs "test"). The trailing `/` is significant — the check matches via `str.startswith(prefix)`. Default `["livespec_dev_tooling/", "dev-tooling/"]` (the livespec-core layout); consumers MAY add or replace.

- **`tests_tree_prefix`** — string ending in `/`. Used by `commit_pairs_source_and_test` to recognize a staged file as "test". Default `"tests/"`.

- **`target_dirs`** — array of strings. Used by `comment_line_anchors` to scope its walk; behaves like a `source_trees` analogue for that check specifically (the check has a different exclusion rule for `_vendor`). Default `["livespec_dev_tooling/", "dev-tooling/"]`.

- **`mirror_pairings`** — array of objects each shaped `{"source_tree": "<path>", "test_tree": "<path>"}`. Used by `check_coverage_incremental` to resolve a source `.py` file to its paired test `.py` file. Default carries livespec-core's two historical mirrors: `livespec/` → `tests/livespec/` and `dev-tooling/checks/` → `tests/dev-tooling/checks/`.

- **`repo`** — object shaped `{"owner": "<gh-owner>", "name": "<gh-repo>"}` or null. Used by `branch_protection_alignment` to query the consumer's GitHub branch protection. When null, the check resolves owner/repo from `git remote get-url origin` (the graceful-skip behavior shipped in PR #11). Default null.

Role keys absent from the schema mean "the check no-ops on this consumer" for that role. The check itself MUST log a structured `info`-level event (`{"check_id": "<slug>", "role": "<key>", "event": "role key absent — check no-ops", "level": "info"}`) so the consumer's `just check` output makes the no-op explicit; no-op MUST NOT degrade silently to pass.

### Default layout fallback

When `pyproject.toml` carries no `[tool.livespec_dev_tooling]` block at all (the livespec-core case until livespec-core opts in), every role key falls back to the historical livespec-core defaults baked into the loader:

```toml
[tool.livespec_dev_tooling]
source_trees       = [".claude-plugin/scripts/livespec"]
io_trees           = [".claude-plugin/scripts/livespec/io"]
commands_trees     = [".claude-plugin/scripts/livespec/commands"]
supervisor_entry_files = [".claude-plugin/scripts/livespec/doctor/run_static.py"]
dataclasses_tree   = ".claude-plugin/scripts/livespec/schemas/dataclasses"
pure_trees         = [".claude-plugin/scripts/livespec"]
covered_trees      = [".claude-plugin/scripts/livespec"]
source_tree_prefixes = ["livespec_dev_tooling/", "dev-tooling/"]
tests_tree_prefix    = "tests/"
target_dirs        = ["livespec_dev_tooling/", "dev-tooling/"]
mirror_pairings    = [
  { source_tree = ".claude-plugin/scripts/livespec",       test_tree = "tests/livespec" },
  { source_tree = "livespec_dev_tooling/checks",            test_tree = "tests/livespec_dev_tooling/checks" },
]
repo               = nil  # resolved via `git remote get-url origin`
```

The fallback set MUST stay bit-identical to livespec-core's pre-G.6 behavior; any change is a major-version bump per `constraints.md` §"Semver discipline".

### Configuration loader

The loader MUST live at `livespec_dev_tooling/config.py` and expose a single public callable:

```python
def load_config(*, repo_root: Path) -> Config:
    """Read `<repo_root>/pyproject.toml` and merge with built-in defaults.

    Reads the `[tool.livespec_dev_tooling]` table via stdlib `tomllib`
    (Python 3.11+) or the vendored `tomli` (Python 3.10 fallback).
    Returns a typed `Config` dataclass with one field per role key.
    Raises `ConfigParseError` (an IO-layer exception, caught by the
    supervisor) on malformed TOML or schema-violating values.
    """
```

`Config` MUST be a frozen, keyword-only dataclass (per `livespec/SPECIFICATION/non-functional-requirements.md` §"Keyword-only Python") with one field per role key, defaulting to the historical fallback values. Every check MUST call `load_config(repo_root=Path.cwd())` in its `main()` before walking the filesystem; no module-level path constants remain.

The Python 3.10 floor (per `constraints.md` §"Runtime") forces the `tomli` fallback. `tomli` MUST be vendored under `livespec_dev_tooling/_vendor/tomli` and listed in `.vendor.jsonc` per `livespec/SPECIFICATION/contracts.md` §"Vendor manifest". The loader MUST select `tomllib` when available and `tomli` otherwise; both libraries expose an identical `loads(text: str) -> dict` API.

### Per-consumer pyproject declarations

Each livespec-governed consumer MUST publish its own `[tool.livespec_dev_tooling]` block in `pyproject.toml`. The block is consumer-private content — the library does not lint or constrain its values; correctness is the consumer's responsibility, surfaced via that consumer's own `just check` self-application.

Three first-party consumers as of v0.2.x:

- **`livespec-core`** — MAY omit the block entirely (the fallback matches its historical layout). If the block is added, every key MUST be bit-identical to the fallback values above.
- **`livespec-dev-tooling`** (self-application) — MUST publish `source_trees = ["livespec_dev_tooling"]`, `target_dirs = ["livespec_dev_tooling"]`, `source_tree_prefixes = ["livespec_dev_tooling/"]`, `mirror_pairings = [{ source_tree = "livespec_dev_tooling", test_tree = "tests/livespec_dev_tooling" }]`. The other role keys (`io_trees`, `commands_trees`, `supervisor_entry_files`, `dataclasses_tree`, `pure_trees`, `covered_trees`) default to empty/null since the library has a flat package layout without the ROP-layered architecture livespec-core has. The corresponding checks (`no_except_outside_io`, `no_raise_outside_io`, `public_api_result_typed`, `no_write_direct`, `newtype_domain_primitives`) no-op against this library; their structured `info` log entries document the no-op.
- **`livespec-impl-plaintext`** — MUST publish its own block once Phase G.7 wiring lands. The exact values are the picking-up agent's call at that phase; the schema accommodates whatever layout that consumer adopts.

Future siblings (any repo carrying the `livespec-sibling` GitHub topic that depends on this library) MUST publish their own block; omitting the block falls back to livespec-core's defaults, which will silent-no-op against any non-livespec-core layout (the trade-off the v0.x backward-compat guarantee accepts).
```

#### Modify §"Shared check inventory" (existing section)

Append a new bullet at the end of the existing §"Shared check inventory" (after line 36) noting the partition criterion now includes configurability:

```markdown
- **Configurability is the partition criterion.** A check is shared if and only if its layout-dependent inputs are configurable via the §"Consumer configuration schema" role keys (such that the check runs unmodified against any consumer's declared layout). A check that asserts a property of a single consumer's layout — properties that cannot be expressed as role keys — stays consumer-private. Two of the original v0.1.0 carve-outs (`schema_dataclass_pairing`, `copier_template_smoke`) qualify under this criterion: the former asserts livespec-core's specific dataclass-naming convention, the latter asserts livespec-core's copier template structure. The partition itself MUST be re-evaluated whenever a new check is authored OR a role key is added to the schema (the addition MAY make a previously-private check shareable).
```

#### Modify §"CLI shape" (existing section in `constraints.md`)

Sharpen the existing constraint (line 36) from "Checks that need configuration MUST read from `pyproject.toml`, `.livespec.jsonc`, or other project-local files in the working directory" to "Checks that need configuration MUST read from `pyproject.toml`'s `[tool.livespec_dev_tooling]` block per `contracts.md` §"Consumer configuration schema"". The alternate locations (`.livespec.jsonc`, "other project-local files") were placeholder phrasing before the schema settled; the schema's single-source-of-truth discipline forbids them.

### Implementation tracking

This propose-change documents the SPEC changes only. The IMPLEMENTATION work tracks separately as the remaining acceptance criteria of `li-asybpo`:

1. **Author the loader.** New `livespec_dev_tooling/config.py` + paired tests + vendor `tomli` under `_vendor/`. Tag a release.
2. **Refactor checks one family at a time** (style, AST, I/O, CI-alignment, red-green-replay). Each family is one PR. Per-check refactor: replace the module-level constant block with `cfg = load_config(repo_root=Path.cwd())` in `main()`, replace constant references with `cfg.<role_key>`, log the no-op `info` event when a role key is empty.
3. **Wire the per-consumer pyproject declarations**: livespec-core's `pyproject.toml` (no-op since fallback matches), livespec-dev-tooling's `pyproject.toml` (per the §"Per-consumer pyproject declarations" subsection above), livespec-impl-plaintext's `pyproject.toml` (deferred to Phase G.7 follow-up).
4. **Wire livespec-dev-tooling's `justfile` `check` aggregate** to invoke every migrated structural check (per `constraints.md` §"Self-application"). The previously-skipped tests un-skip naturally as the checks self-apply.

Acceptance criterion #3 of li-asybpo (un-skip 3 tests + restore `fail_under = 100`) landed via PR #11 (commit `d63be8d`); the remaining 1, 2, 4, 5 hinge on the schema landing first.
