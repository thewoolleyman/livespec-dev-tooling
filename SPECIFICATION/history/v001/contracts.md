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

The partition between shared checks (which ship in this library) and `livespec`-private checks (which stay in livespec) MUST be codified here. This section is the canonical authority; livespec-core's `dev-tooling/checks/` directory is the source of truth for the migration mapping until livespec epic `li-fgqgnk` Phase G.4 completes the move.

- **Shared (migrate to `livespec_dev_tooling/checks/`).** Every check under `livespec/dev-tooling/checks/<slug>.py` whose argv contract is project-agnostic — i.e., the check can run unmodified in any livespec-governed repo. This includes (as of Phase G.4): the AST-shape gates (`assert_never_exhaustiveness`, `keyword_only_args`, `match_keyword_only`, `no_inheritance`, `newtype_domain_primitives`, `all_declared`, `main_guard`, `private_calls`, `global_writes`, `imports_architecture`, `wrapper_shape`), the I/O-discipline gates (`no_raise_outside_io`, `no_except_outside_io`, `no_write_direct`, `supervisor_discipline`, `public_api_result_typed`), the style gates (`lint`, `format`, `complexity`, `claude_md_coverage`, `heading_coverage`, `vendor_manifest`, `no_direct_tool_invocation`, `commit_pairs_source_and_test`), the test-infrastructure gates (`coverage`, `pbt_coverage_pure_modules`, `tools`, `no_lloc_soft_warnings`, `no_todo_registry`), the CI-alignment gates (`branch_protection_alignment`, `master_ci_green`), and the red-green-replay gate (`red_green_replay`).

- **`livespec`-private (stay in livespec).** `schema_dataclass_pairing` (because it asserts properties of `livespec`'s own `livespec/schemas/dataclasses/` layout, which is not a layout any other consumer has) and `copier_template_smoke` (because it asserts properties of `livespec/templates/impl-plugin/` itself, which only `livespec` owns).

The partition MUST be re-evaluated whenever a new check is authored: if the check's argv contract is project-agnostic, it ships here; if it asserts a property of a single consumer's layout, it stays at that consumer.

## Composite Actions wire contract

Composite Actions at `.github/actions/<name>/action.yml` MUST declare their inputs, outputs, and required permissions. The Action's name (and therefore the path consumers reference via `uses:`) is the semver-stable identifier; the underlying step list MAY change between versions.

The library MUST ship at minimum two composite Actions:

- **`setup`**. Inputs: `python-version-file` (default `.python-version`). Performs: checkout (already done by caller), mise install, `uv sync --all-groups`. Outputs: none.
- **`run-check`**. Inputs: `check-name` (required), `working-directory` (default `.`), `extra-args` (default `""`). Performs: `uv run python -m livespec_dev_tooling.checks.<check-name> <extra-args>` from `working-directory`. Outputs: none; exit status propagates.

## Reusable workflows wire contract

Reusable workflows at `.github/workflows/reusable-<name>.yml` MUST declare their inputs, outputs, secrets, and concurrency requirements. The workflow file name (the path consumers reference via `uses:`) is the semver-stable identifier.

The library MUST ship at minimum one reusable workflow:

- **`reusable-check-matrix.yml`**. Inputs: `checks` (a JSON-array string of check slugs to run; default = a documented "standard suite"). Strategy: matrix over the `checks` input; each matrix entry runs the `run-check` composite Action. Outputs: per-check pass/fail.

## Versioning

Releases are managed by `release-please` per the Conventional Commits → semver mapping documented in `livespec/SPECIFICATION/contracts.md` §"Plugin versioning". The `pyproject.toml` `version` field, the `.release-please-manifest.json` entry, and the git tag MUST stay in lockstep; `release-please` is the only tool that writes to these.
