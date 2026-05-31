# livespec-dev-tooling — contracts

This file enumerates the wire-level and CLI-level interfaces the library exposes. Every contract here is semver-stable: a breaking change MUST land via a MAJOR version bump per `constraints.md` §"Semver discipline".

## CLI surface

Every check module under `livespec_dev_tooling/checks/<slug>.py` MUST be invocable as `python -m livespec_dev_tooling.checks.<slug>`. The invocation form is the semver-stable contract; consumers MUST NOT call internal helper modules directly.

Each check MUST:

- Accept zero positional arguments by default. A check that needs configuration MUST read it from the current working directory (`pyproject.toml`, `.livespec.jsonc`, etc.), NOT from positional argv.
- Accept `--help` / `-h` and exit `0` with usage text written to stdout.
- Exit `0` on pass and a documented non-zero code on fail. The non-zero exit MUST be accompanied by structured findings emitted on stderr describing what failed and where.
- Perform no network I/O. Reading the local filesystem and invoking project-local subprocesses (git, ruff, pyright, pytest) is permitted; reaching out to a remote service is forbidden per `constraints.md` §"No network I/O".

## Exit-code table

| Code | Meaning |
|---|---|
| `0` | check passed |
| `1` | internal bug (uncaught exception) |
| `2` | usage error (bad CLI invocation) |
| `3` | precondition error (the project state needed for the check is not met) |
| `4` | check failed (structured findings on stderr) |

The `4`-and-up range is reserved for check-specific failure modes; each check that defines a new code MUST document it in the check's own module docstring AND in this table.

## Shared check inventory

The partition between shared checks (which ship in this library) and `livespec`-private checks (which stay in livespec) MUST be codified here. This section is the canonical authority; livespec-core's `dev-tooling/checks/` directory is the source of truth for the migration mapping until the shared structural checks complete migration from livespec-core.

- **Shared (migrate to `livespec_dev_tooling/checks/`).** Every check under `livespec/dev-tooling/checks/<slug>.py` whose argv contract is project-agnostic — i.e., the check can run unmodified in any livespec-governed repo. This includes (as of Phase G.4): the AST-shape gates (`assert_never_exhaustiveness`, `keyword_only_args`, `match_keyword_only`, `no_inheritance`, `newtype_domain_primitives`, `all_declared`, `main_guard`, `private_calls`, `global_writes`, `rop_pipeline_shape`, `wrapper_shape`), the I/O-discipline gates (`no_raise_outside_io`, `no_except_outside_io`, `no_write_direct`, `supervisor_discipline`, `public_api_result_typed`), the style gates (`claude_md_coverage`, `comment_line_anchors`, `file_lloc`, `heading_coverage`, `vendor_manifest`, `no_direct_tool_invocation`, `commit_pairs_source_and_test`), the test-infrastructure gates (`check_coverage_incremental`, `check_mutation`, `check_tools`, `per_file_coverage`, `pbt_coverage_pure_modules`, `tests_mirror_pairing`, `no_lloc_soft_warnings`, `no_todo_registry`), the CI-alignment gates (`branch_protection_alignment`, `master_ci_green`, `no_stale_revise_branches`, `primary_checkout_commit_refuse_hook_installed`), and the red-green-replay gate (`red_green_replay`).

  The `lint`, `format`, and `complexity` concerns are NOT shipped as dedicated check modules — they are handled via direct `ruff` invocation through `just lint` / `just format` recipes in each consumer's `justfile`. They appear in the conceptual check coverage but have no `python -m livespec_dev_tooling.checks.<slug>` invocation form.

- **`livespec`-private (stay in livespec).** `schema_dataclass_pairing` (because it asserts properties of `livespec`'s own `livespec/schemas/dataclasses/` layout, which is not a layout any other consumer has) and `copier_template_smoke` (because it asserts properties of `livespec/templates/impl-plugin/` itself, which only `livespec` owns).

The partition MUST be re-evaluated whenever a new check is authored: if the check's argv contract is project-agnostic, it ships here; if it asserts a property of a single consumer's layout, it stays at that consumer.

- **Configurability is the partition criterion.** A check is shared if and only if its layout-dependent inputs are configurable via the §"Consumer configuration schema" role keys (such that the check runs unmodified against any consumer's declared layout). A check that asserts a property of a single consumer's layout — properties that cannot be expressed as role keys — stays consumer-private. Two of the original v0.1.0 carve-outs (`schema_dataclass_pairing`, `copier_template_smoke`) qualify under this criterion: the former asserts livespec-core's specific dataclass-naming convention, the latter asserts livespec-core's copier template structure. The partition itself MUST be re-evaluated whenever a new check is authored OR a role key is added to the schema (the addition MAY make a previously-private check shareable).

### `branch_protection_alignment` check

Invocation: `python -m livespec_dev_tooling.checks.branch_protection_alignment`. The check has two responsibilities: a PROTECTION-PRESENT gate and (when protection exists) an ALIGNMENT gate.

The check shells out to `gh api` to read master's branch protection. It distinguishes three outcomes by the GitHub API response, and the distinction is load-bearing because a 404 from the branch-protection endpoint is ambiguous — GitHub returns 404 (not 403) both when a branch is genuinely unprotected AND when the calling token lacks the admin scope required to READ protection (this is deliberate, to avoid leaking repo/branch existence). The disambiguator is the response body's `message` field:

1. **API succeeds with a contexts list** → run the ALIGNMENT gate (below).
2. **API returns the canonical `Branch not protected` 404** → the answer is DEFINITIVELY absent. GitHub emits this exact message only for an admin-scoped token reading a genuinely unprotected branch. The check FAILS (exit `4`) with one structured `fail` finding (`failure_mode` `protection_absent`): master is unprotected and required-check branch protection MUST be enabled. An unprotected master lets PRs auto-merge before CI finishes and lets a red PR land. The finding cites `livespec/SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)".
3. **`gh` unavailable / unauthenticated, OR the API errors for any OTHER reason** (notably a permission/visibility 404 under a token without admin scope — e.g., a generic `Not Found` or `Resource not accessible by integration`), OR the origin remote is not a github.com URL, OR the success payload has an unexpected shape → the check CANNOT distinguish "absent" from "can't-read", so it exits `0` with a structured warning (graceful skip). This keeps local pre-commit runs unblocked and prevents CI false-fails under a token that cannot read protection. The key invariant: the check fails ONLY on a definitive "absent" answer, never on a mere "couldn't read it".

When `.github/workflows/ci.yml` is absent, the check exits `0` (graceful absence-handling): consumers that have not configured GitHub Actions CI have no required-checks list to align against.

ALIGNMENT gate (outcome 1 only). Two-direction comparison between master's required-checks list and `ci.yml`'s `matrix.target` job names:

- A required check with no matching `ci.yml` job → ERROR; the check FAILS (exit `4`) with one `fail` finding per offending check (`failure_mode` `required_check_missing_from_ci`). This is the v039-D1-style drift: GitHub blocks merges because the required check never reports.
- A `ci.yml` job NOT in the required list → WARNING only (exit `0` contribution); some jobs are intentionally not required (e.g., experimental workflows).

Exit codes: `0` on protection-present-and-aligned OR any graceful skip; `1` on the legacy precondition failure (ci.yml present but `matrix.target` empty or unparseable); `4` on either fail branch (`protection_absent` or `required_check_missing_from_ci`).

CI-token caveat: the default GitHub Actions `GITHUB_TOKEN` lacks the admin scope needed to READ branch protection, so in a stock Actions job this check always lands on the outcome-3 graceful-skip path (it receives an ambiguous `Not Found`, never the canonical `Branch not protected`) and does NOT enforce. The check is therefore wired into the `just check` aggregate / pre-push — where a maintainer's admin-scoped `gh` token CAN read protection and the fail-on-absent branch actually fires — and is intentionally NOT a required CI matrix entry, which would always-skip and be pointless. A consumer whose CI provides an admin-scoped token (e.g., a PAT secret) MAY additionally wire the check into its CI matrix.

### `no_stale_revise_branches` check

Invocation: `python -m livespec_dev_tooling.checks.no_stale_revise_branches`. Exit `0` on no stale branches, exit `4` with structured stderr findings on any stale branch.

Algorithm:

1. Read the canonical branch name from `.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch` config key (or any other configured impl plugin's equivalent key). Default: `git symbolic-ref --short refs/remotes/origin/HEAD`, with hard-coded fallback `master`.
2. Enumerate local refs: `git for-each-ref --format='%(refname:short)' refs/heads/spec/`.
3. For each branch in the enumeration:
    - Run `git rev-list --left-right --count origin/<canonical>...<branch>`.
    - Parse the output as `behind\tahead`.
    - If `ahead > 0`: emit a finding with severity `fail`.
4. Exit `0` on zero findings, `4` on one or more.

Each finding carries:

- `check_id`: `no_stale_revise_branches`
- `status`: `fail`
- `message`: `branch '<name>' is <ahead> commit(s) ahead of origin/<canonical>; last commit <short-sha> "<subject>"`
- `path`: empty (the finding is git-topology, not file-system)
- `line`: 0

The check is INVOKED by livespec's `/livespec:revise` SKILL.md as a pre-step refusal (per the coordinating epic's Layer 1). Consumers MAY also wire it into doctor's static phase via the impl plugin's contract; that wiring is the impl plugin's choice, not this check's mandate.

Override flag: `--allow-stale-branches` (optional). Exits `0` even when stale branches are present, but emits the findings as `info` rather than `fail`. The override is for cases where the user has intentionally orphaned a branch (e.g., experimental scratch work the user knows about) and wants the rest of their workflow unblocked. Per the coordinating epic, the calling SKILL.md is responsible for surfacing acknowledgement narration when the override is used; this check itself only honors the flag.

### `primary_checkout_commit_refuse_hook_installed` check

Invocation: `python -m livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed`. Exit `0` on pass OR skipped, exit `4` with structured stderr findings on fail.

The check is a port of the cross-boundary invariant declared at `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary invariants" → §"`primary-checkout-commit-refuse-hook-installed`": every livespec-governed primary checkout MUST install a `.git/hooks/pre-commit` AND a `.git/hooks/pre-push` hook whose body refuses to run when invoked at the primary checkout. The hook is a no-op at secondary worktrees (whose `git rev-parse --show-toplevel` returns the worktree's own path, not the primary's). The check reads the two hook files against the cwd's git common dir (`git rev-parse --git-common-dir`), which by git's design resolves to the primary's `.git/hooks/` even when invoked from a secondary worktree.

This mechanism supersedes the v091–v094 `core.bare = true` bare-flag mechanism (the check `primary_checkout_bare_flag_set` in earlier releases). Per `livespec/SPECIFICATION/non-functional-requirements.md` §"Primary-checkout commit-refuse hook", the bare-flag mechanism caused stale-on-disk-read failures at primaries that the hook mechanism does not.

Inputs are project-agnostic — no `[tool.livespec_dev_tooling]` role keys are consumed. The check is layout-independent and qualifies under §"Configurability is the partition criterion" without any role-key wiring.

The canonical hook body is recognized via a tolerant fingerprint — the check verifies each hook file contains all three of the following substrings (substring presence, not exact equality, so portable-shell rewrites such as alternate quoting or extra whitespace are accepted):

- the marker comment `# livespec commit-refuse hook`,
- an invocation of `git rev-parse --show-toplevel` (the at-primary detection), AND
- an `exit 1` branch (the refuse-at-primary path).

Algorithm:

1. If `git` is not on PATH → exit `0` with a warning (graceful skip; local-dev tolerance).
2. If cwd is not a git repository at all (`git rev-parse --git-dir` ≠ exit `0`) → exit `0` with an info log (skipped). This is the genuinely-not-a-repo case; the check is a no-op rather than a false positive.
3. Otherwise (cwd IS a git repository) — if `core.bare = true` is set (`git config --get core.bare` resolves to `true`) → exit `4` with one structured `fail` finding (`failure_mode` `core_bare_set`) on stderr. This catches the eliminated legacy bare-flag state (the v091–v094 `core.bare = true` mechanism this hook mechanism superseded): a bare repo is a git repository that is NOT a work tree, so step 4's work-tree skip would otherwise pass it silently. This branch realizes the MAY in `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary invariants" → §"`primary-checkout-commit-refuse-hook-installed`" — "The doctor invariant MAY additionally surface a `fail` when `core.bare = true` is set on the primary, to catch the legacy-state case during the transition." The canonical upstream invariant stays a MAY; this sibling's impl chooses to realize it.
4. Otherwise — if cwd is not inside a git working tree (`git rev-parse --is-inside-work-tree` ≠ `true`; e.g. cwd is inside the `.git` directory of a non-bare repo) → exit `0` with an info log (skipped).
5. Otherwise, resolve the git common dir and verify BOTH `<common-dir>/hooks/pre-commit` and `<common-dir>/hooks/pre-push`:
    - each exists as a regular file, AND is executable for the current user (`os.access(path, os.X_OK)`), AND contains the canonical fingerprint → exit `0` (pass).
    - else → exit `4` with one structured `fail` finding per offending hook on stderr.

For the hook-installation modes, the check MUST NOT distinguish between "missing", "non-executable", and "non-canonical body" (the empty-file case is a non-canonical body) at the contract level — all three fire equally and all three are corrected by the same bootstrap invocation. The corrective action is to run the repo's documented bootstrap step (per `livespec/SPECIFICATION/non-functional-requirements.md` §"Commit-refuse hook bootstrap procedure"), which idempotently installs the canonical commit-refuse hook at both `.git/hooks/pre-commit` and `.git/hooks/pre-push`. The narration MAY name the specific failure mode for diagnostic clarity, but the structural `fail` finding is identical across the three hook-installation modes. The `core_bare_set` failure mode (step 3) is a distinct fail branch with its own corrective action (unset the flag and repopulate the working tree).

Each `fail` finding carries:

- `check_id`: `primary_checkout_commit_refuse_hook_installed`
- `status`: `fail`
- `hook`: the offending hook name (`pre-commit` or `pre-push`); empty (`""`) for the `core_bare_set` fail branch, which is not tied to a specific hook
- `failure_mode`: one of `missing`, `not_executable`, `non_canonical_body` (hook-installation modes), OR `core_bare_set` (the legacy bare-flag regression at step 3)
- `hooks_dir`: the absolute path to the inspected `<common-dir>/hooks/` directory; empty (`""`) for the `core_bare_set` fail branch, which fails before resolving the common dir
- `hint`: for the hook-installation modes, `run the repo's documented bootstrap step (see livespec/SPECIFICATION/non-functional-requirements.md §"Commit-refuse hook bootstrap procedure") to idempotently install the canonical commit-refuse hook at both \`.git/hooks/pre-commit\` and \`.git/hooks/pre-push\``; for the `core_bare_set` branch, a hint directing the user to `git config --unset core.bare && git reset --hard origin/master` to repopulate the working tree, then run the bootstrap step
- `path`: empty
- `line`: 0

(The `skipped` paths at steps 1, 2, and 4 emit a `warning`/`info` log carrying `check_id` plus a `hint`/`cwd` field respectively; only the `fail` paths carry the `status` field.)

Consumers MAY wire the check into `just check` aggregates and/or CI matrices. Per the migration phase, each sibling's wiring is its own follow-up and MAY be staged so the wiring lands after that sibling's primary has had the bootstrap step run.

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

### Carve-out: project-wide invariants outside the role-key inventory

Some checks have layout-dependent inputs that are project-wide invariants rather than check-specific role keys (e.g., the canonical branch name `master` / `main`). Such checks read directly from `.livespec.jsonc` rather than the `[tool.livespec_dev_tooling]` role-key inventory, to avoid duplicate config. The list of carve-out keys is currently small:

- `canonical_branch` — read from `.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch` (or equivalent impl-plugin block's key, per the impl plugin's spec).

Future carve-outs require explicit propose-change documentation; the default for new layout-dependent inputs is the role-key inventory.

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

## Composite Actions wire contract

Composite Actions at `.github/actions/<name>/action.yml` MUST declare their inputs, outputs, and required permissions. The Action's name (and therefore the path consumers reference via `uses:`) is the semver-stable identifier; the underlying step list MAY change between versions.

The library MUST ship at minimum two composite Actions:

- **`setup`**. Inputs: `python-version-file` (default `.python-version`). Performs: checkout (already done by caller), mise install, `uv sync --all-groups`. Outputs: none.
- **`run-check`**. Inputs: `check-name` (required), `working-directory` (default `.`), `extra-args` (default `""`). Performs: `uv run python -m livespec_dev_tooling.checks.<check-name> <extra-args>` from `working-directory`. Outputs: none; exit status propagates.

## Reusable workflows wire contract

Reusable workflows at `.github/workflows/reusable-<name>.yml` MUST declare their inputs, outputs, secrets, and concurrency requirements. The workflow file name (the path consumers reference via `uses:`) is the semver-stable identifier.

The library MUST ship at minimum one reusable workflow:

- **`reusable-check-matrix.yml`**. Inputs: `checks` (a JSON-array string of check slugs to run; default = a documented "standard suite"). Strategy: matrix over the `checks` input; each matrix entry runs the `run-check` composite Action. Outputs: per-check pass/fail.

## Cross-repo coordination automation surface

This section codifies the reusable GitHub workflow surface that implements livespec's pin-and-bump mechanism (per `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump") uniformly across every livespec-governed sibling repository. The contract here is the canonical implementation specification; livespec's spec declares the policy, this section owns the implementation surface. Per the DRY discipline, every consumer's per-repo coordination footprint is three thin shim workflows that delegate to the reusable workflows defined here; no coordination logic is duplicated across consumers.

### Sibling discovery

Every livespec-governed sibling repository MUST carry the `livespec-sibling` GitHub topic on its repository metadata. The coordination workflows discover siblings via `gh search repos --owner <org> --topic livespec-sibling --json name` at dispatch time. A repository missing the topic is silently excluded from dispatch; this is the supported mechanism for opting out (e.g., during sibling repo bootstrap before it is ready to receive bumps).

The topic-based discovery mechanism MUST be the sole source of truth for the sibling set. A static registry file (e.g., a `siblings.yml` in this library) is FORBIDDEN — the discovery is autodiscovery by design, so adding a new sibling requires no edits to this library's source.

### Reusable workflow inventory

The library MUST ship the following reusable workflows under `.github/workflows/`, each with a `workflow_call` trigger and the inputs/outputs declared below. Each workflow's path is the semver-stable identifier consumers reference via `uses:`.

#### `reusable-release-dispatch.yml`

Fan-out dispatcher invoked by each sibling's own `release-dispatch.yml` shim on `on: release: types: [published]`.

Inputs:
- `source_repo` (string, required) — the publishing repository's short name (e.g., `livespec-runtime`).
- `tag` (string, required) — the published release tag (e.g., `v0.3.0`).
- `release_url` (string, required) — the GitHub release page URL, used in downstream PR descriptions.

Secrets: `APP_ID`, `APP_PRIVATE_KEY` (inherited via `secrets: inherit`).

Behavior: discovers siblings per §"Sibling discovery", excludes `source_repo` from the dispatch matrix, fires a `repository_dispatch` event to each remaining sibling carrying the payload contract per §"`repository_dispatch` payload contract". A 404 from any sibling (e.g., App not installed) surfaces as a workflow annotation and does NOT fail the dispatch loop (soft-fail per §"Soft-fail semantics").

#### `reusable-bump-pin-from-dispatch.yml`

Per-consumer handler invoked by each sibling's own `bump-pin-from-dispatch.yml` shim on `on: repository_dispatch: types: [sibling-released]`.

Inputs:
- `source_repo` (string, required) — extracted from `client_payload.source_repo`.
- `tag` (string, required) — extracted from `client_payload.tag`.
- `release_url` (string, optional) — extracted from `client_payload.release_url`; included in the PR body for traceability.

Behavior: clones the consumer repository, runs the pin-autodiscovery walk per §"Pin autodiscovery rules", edits every matching pin to `tag`, runs `just check`, commits with the `chore:`-prefixed message per §"PR commit-message convention", opens an auto-merge PR via the GitHub App per §"GitHub App auth model".

When autodiscovery surfaces zero matching pins (the consumer does not depend on `source_repo`), the workflow exits `0` with a workflow annotation explaining the no-op.

When the consumer's `.vendor.jsonc` carries an entry for the normalized form of `source_repo`, the workflow ADDITIONALLY invokes the consumer's `just vendor-update <lib>` recipe before running `just check`, so re-vendoring lands atomically in the same commit as the manifest pin update.

#### `reusable-pin-freshness.yml`

Periodic safety-net workflow invoked by each sibling's own `pin-freshness.yml` shim on `on: schedule: cron: ...`.

Inputs:
- `staleness_threshold_releases` (integer, optional, default `1`) — the number of intermediate releases beyond which a pin is considered stale.

Behavior: runs the pin-autodiscovery walk per §"Pin autodiscovery rules", queries each discovered source repository's latest release tag via `gh release view --json tagName`, and opens a bump PR per `(source_repo, current_pin, latest_tag)` triple where the latest tag is at least `staleness_threshold_releases` ahead of the current pin. Reuses the bump-PR-opening machinery from `reusable-bump-pin-from-dispatch.yml`.

The freshness workflow is the safety net for missed dispatches, releases that occurred before this surface was wired in, and any future class of dispatch failure that does not auto-recover.

### Pin autodiscovery rules

The pin-autodiscovery walk inspects the consumer repository for every supported pin format and yields a normalized `(pin_format, file_path, pin_key, current_value)` record per discovered pin. The walk MUST cover the following formats:

- **`.livespec.jsonc` `compat.pinned`** — every top-level key in `.livespec.jsonc` whose value contains a `compat` object with `pinned` and `livespec` fields. The top-level key's name is the pin's consumer-self-identifier; the pin's source repo is always `livespec` (a `compat.pinned` field always pins the consumer to a livespec release tag).
- **`pyproject.toml` `[tool.uv.sources]`** — every entry in `[tool.uv.sources]` whose `git` field matches the source repository's GitHub URL. The `tag` field is the pin's current value.
- **`.vendor.jsonc`** — every entry in `.vendor.jsonc`'s `libraries` array whose `name` matches the normalized form of the source repository's Python package name (hyphen-to-underscore for Python package convention). The `upstream_ref` field is the pin's current value.
- **`.copier-answers.yml` `_commit`** — the singular `_commit` field, present in projects generated via `copier copy` / `copier update`. The implicit source repository is the one referenced by `_src_path`; the field's value is a git ref (commit SHA or tag).

The walk MUST be tolerant of missing files — a consumer without a `.vendor.jsonc` simply yields no `.vendor.jsonc`-format records. The walk MUST also be tolerant of pin formats it does not recognize; an unrecognized format produces no record and a workflow annotation noting the unrecognized file for human inspection.

Source-repository-name normalization for `.vendor.jsonc` matching: replace every `-` in the source repo's short name with `_` (e.g., `livespec-runtime` matches `livespec_runtime`). Other pin formats use the source repo's short name verbatim.

### `repository_dispatch` payload contract

Every `repository_dispatch` event fired by the coordination surface MUST carry the following shape:

```json
{
  "event_type": "sibling-released",
  "client_payload": {
    "source_repo": "<short-name>",
    "tag": "<vX.Y.Z>",
    "release_url": "<GitHub release page URL>"
  }
}
```

The `event_type` value is fixed at the literal `"sibling-released"`. The `client_payload` shape is the semver-stable contract; adding new fields is a MINOR bump, removing or renaming existing fields is a MAJOR bump.

### GitHub App auth model

The coordination surface MUST authenticate via a GitHub App installation token, NOT via `GITHUB_TOKEN`. The App MUST be installed on every sibling repository and MUST hold the following permissions:

- `contents: write` — to commit the bump and create branches.
- `pull-requests: write` — to open the bump PR.
- `metadata: read` — to read repository metadata for sibling discovery.

The token is minted at runtime via `actions/create-github-app-token@v1` with the App's `APP_ID` and `APP_PRIVATE_KEY` secrets passed via `secrets: inherit` from each consumer shim. The App's private key has no calendar expiration, so token expiry does NOT silently break the surface.

The rationale for App-token over `GITHUB_TOKEN` mirrors the existing `auto-update-branches.yml` and `auto-enable-merge.yml` choices in livespec: pushes authored by `GITHUB_TOKEN` do not trigger downstream CI workflows (GitHub's workflow-recursion ceiling), which would leave bump PRs permanently `BLOCKED` with no CI re-runs against the updated head SHA.

### Soft-fail semantics

A 404 response from a target sibling during dispatch (App not installed on that sibling, or repository missing) MUST surface as a workflow annotation and MUST NOT fail the dispatch loop. Other 4xx and 5xx responses MUST fail the dispatch job for that sibling but MUST NOT cascade to other siblings (each sibling occupies its own matrix entry with `fail-fast: false`).

### PR commit-message convention

Bump-pin PRs MUST use the Conventional Commits `chore:` prefix on the PR title and the commit subject. The `chore:` prefix is explicitly excluded from triggering a release-please version bump per the Conventional Commits → semver mapping at `livespec/SPECIFICATION/contracts.md` §"Plugin versioning"; this prevents an automatic-bump-PR cycle where a sibling's release triggers a bump PR in this library which triggers another release of this library which triggers another round of bump PRs.

The PR title template is `chore(deps): bump <source_repo> pin to <tag>`. The PR body MUST include the `release_url` from the dispatch payload for traceability.

### Pin-freshness threshold defaults

The `staleness_threshold_releases` input to `reusable-pin-freshness.yml` defaults to `1` — any pin one or more releases behind the latest tag triggers a bump PR. A consumer MAY override via the input on its `pin-freshness.yml` shim if its cadence demands higher tolerance for drift.

The cron cadence is consumer-owned; the dev-tooling reusable workflow accepts whatever schedule the shim declares. The recommended cadence is daily (`0 13 * * *`) — frequent enough to catch missed dispatches within one business day, infrequent enough to avoid noise.

### Fallback to known-good pin

When a bump PR's `just check` fails on the new pin, the bump PR MUST remain open with the check failure marked. The consumer's last green pin remains the active pin on `master` until the failure is resolved.

Resolution paths, in order of preference:

1. **Auto-rollback (future).** A planned future workflow `reusable-pin-rollback.yml` MAY revert the pin to the most recent commit on `master` whose `just check` last passed, on detection of N consecutive failing bump attempts. This future surface is OUT OF SCOPE for v1 and is named here only to reserve the design space; a subsequent propose-change cycle defines its contract.
2. **Manual pin to known-good.** A human contributor edits the pin file directly to a known-good tag, commits with the `chore:` prefix per §"PR commit-message convention", and merges. This is the v1 fallback for any failure the planned auto-rollback would have handled.

The `bump-pin` workflow MUST NOT silently force-push past a failing check. The auto-merge label is the consumer's standard auto-merge label (configurable per consumer via repo settings); the workflow only attaches the label, it does not bypass branch-protection gates.

### Self-hosting

The library is itself a sibling consumer of its own coordination automation surface. The library's own `.github/workflows/` MUST include the three consumer shims (`release-dispatch.yml`, `bump-pin-from-dispatch.yml`, `pin-freshness.yml`) and the repository MUST carry the `livespec-sibling` topic. The shims delegate to the reusable workflows at the library's own currently-pinned release tag; consequently the library pin-and-bumps itself when livespec releases.

The self-hosting bootstrap is a one-time manual step: a human contributor authors the three consumer shims with their `uses:` lines pinned to a hand-chosen bootstrap tag (typically the first tag of this library that ships all three reusable workflows under `.github/workflows/`), tags the bootstrap release, and verifies that the first dispatch from a sibling release reaches this library and opens a bump-PR. Thereafter the system perpetuates via its own dispatches and the manual step is never repeated.

### Semver coverage extension

The semver-stable surface declared in `constraints.md` §"Semver discipline" is hereby extended to cover the following new elements introduced by this section:

- Each reusable workflow's path AND its declared inputs / outputs / secrets contract.
- The `repository_dispatch` payload contract (event type + `client_payload` shape).
- The sibling discovery mechanism (the `livespec-sibling` topic name).
- The pin autodiscovery rules' format coverage (adding a new pin format is a MINOR bump; removing or breaking compatibility of an existing format is a MAJOR bump).

Pure implementation changes that preserve every element above MAY land via PATCH bump per the existing discipline.

## Versioning

Releases are managed by `release-please` per the Conventional Commits → semver mapping documented in `livespec/SPECIFICATION/contracts.md` §"Plugin versioning". The `pyproject.toml` `version` field, the `.release-please-manifest.json` entry, and the git tag MUST stay in lockstep; `release-please` is the only tool that writes to these.
