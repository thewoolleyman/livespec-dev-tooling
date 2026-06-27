# livespec-dev-tooling — contracts

This file enumerates the wire-level and CLI-level interfaces the library exposes. Every contract here is semver-stable: a breaking change MUST land via a MAJOR version bump per §"Semver discipline".

## CLI surface

Every check module under `livespec_dev_tooling/checks/<slug>.py` MUST be invocable as `python -m livespec_dev_tooling.checks.<slug>`. The invocation form is the semver-stable contract; consumers MUST NOT call internal helper modules directly.

Each check MUST:

- Accept zero positional arguments by default. A check that needs configuration MUST read it from the current working directory (`pyproject.toml`, `.livespec.jsonc`, etc.), NOT from positional argv.
- Accept `--help` / `-h` and exit `0` with usage text written to stdout.
- Exit `0` on pass and a documented non-zero code on fail. The non-zero exit MUST be accompanied by structured findings emitted on stderr describing what failed and where.
- Perform no network I/O. Reading the local filesystem and invoking project-local subprocesses (git, ruff, pyright, pytest) is permitted; reaching out to a remote service is forbidden per `constraints.md` §"No network I/O".

Beyond the check modules, the library exposes one operational CLI module under the same semver-stable invocation contract: the commit-refuse hook installer `python -m livespec_dev_tooling.install_commit_refuse_hooks`. It idempotently writes the canonical structural commit-refuse hook body to the primary checkout's shared `.git/hooks/pre-commit`, `pre-push`, AND `commit-msg` (resolved via `git rev-parse --git-common-dir`, so the install is worktree-safe — it lands in the primary's shared hooks directory even when invoked from a secondary worktree), makes each executable, and exits `0` on success. The module is the SINGLE source of truth for the canonical body (its module-level `CANONICAL_HOOK_BODY` string constant — wheel-carried because only the `livespec_dev_tooling/` package is packaged), so there is no second on-disk copy to drift. Consumers invoke it through the `just install-commit-refuse-hooks` recipe (also driven by `just bootstrap`).

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

- **Shared (migrate to `livespec_dev_tooling/checks/`).** Every check under `livespec/dev-tooling/checks/<slug>.py` whose argv contract is project-agnostic — i.e., the check can run unmodified in any livespec-governed repo. This includes (as of Phase G.4): the AST-shape gates (`assert_never_exhaustiveness`, `keyword_only_args`, `match_keyword_only`, `no_inheritance`, `newtype_domain_primitives`, `all_declared`, `main_guard`, `private_calls`, `global_writes`, `rop_pipeline_shape`, `wrapper_shape`), the I/O-discipline gates (`no_raise_outside_io`, `no_except_outside_io`, `no_write_direct`, `supervisor_discipline`, `public_api_result_typed`), the style gates (`claude_md_coverage`, `comment_line_anchors`, `file_lloc`, `heading_coverage`, `vendor_manifest`, `no_direct_tool_invocation`, `commit_pairs_source_and_test`), the test-infrastructure gates (`check_coverage_incremental`, `check_mutation`, `check_tools`, `per_file_coverage`, `pbt_coverage_pure_modules`, `tests_mirror_pairing`, `no_lloc_soft_warnings`, `no_todo_registry`), the CI-alignment gates (`branch_protection_alignment`, `master_ci_green`, `primary_checkout_commit_refuse_hook_installed`), and the red-green-replay gate (`red_green_replay`).

- **Revise-workflow checks (`livespec_dev_tooling/workflow_checks/`).** Shared, project-agnostic checks invoked by a specific workflow step — the `/livespec:revise` pre-step — rather than by the per-commit `just check` aggregate. They live under `livespec_dev_tooling/workflow_checks/` (NOT `livespec_dev_tooling/checks/`), so the canonical-set derivation (which walks `checks/*.py` per the wiring-completeness invariant) auto-excludes them, and they are therefore NOT subject to the wiring-completeness invariant and NOT members of the canonical aggregate. `no_stale_revise_branches` is the first such check; its load-bearing enforcement is the mandatory `/livespec:revise` pre-step, which fails hard on any stale branch.

  The `lint`, `format`, and `complexity` concerns are NOT shipped as dedicated check modules — they are handled via direct `ruff` invocation through `just lint` / `just format` recipes in each consumer's `justfile`. They appear in the conceptual check coverage but have no `python -m livespec_dev_tooling.checks.<slug>` invocation form.

- **`livespec`-private (stay in livespec).** `schema_dataclass_pairing` (because it asserts properties of `livespec`'s own `livespec/schemas/dataclasses/` layout, which is not a layout any other consumer has) and `copier_template_smoke` (because it asserts properties of `livespec/templates/impl-plugin/` itself, which only `livespec` owns).

The partition MUST be re-evaluated whenever a new check is authored: if the check's argv contract is project-agnostic, it ships here; if it asserts a property of a single consumer's layout, it stays at that consumer.

- **Configurability is the partition criterion.** A check is shared if and only if its layout-dependent inputs are configurable via the §"Consumer configuration schema" role keys (such that the check runs unmodified against any consumer's declared layout). A check that asserts a property of a single consumer's layout — properties that cannot be expressed as role keys — stays consumer-private. Two of the original v0.1.0 carve-outs (`schema_dataclass_pairing`, `copier_template_smoke`) qualify under this criterion: the former asserts livespec-core's specific dataclass-naming convention, the latter asserts livespec-core's copier template structure. The partition itself MUST be re-evaluated whenever a new check is authored OR a role key is added to the schema (the addition MAY make a previously-private check shareable).

**The `baseline` profile.** `canonical_checks.baseline_check_slugs()` returns the `baseline` profile — a deliberately static, curated SUBSET of the canonical check set naming the checks a governed repo wires to claim the universal worktree-discipline conformance floor (the `baseline` profile of `livespec/SPECIFICATION/non-functional-requirements.md` §"Conformance Pattern"). Unlike the canonical set (filesystem-derived from `checks/<slug>.py`), the baseline profile is a hand-maintained registry — a curated product decision NOT mechanically derivable from the checks directory, per the project convention "static enumeration only for typed dispatch". Every entry MUST also be a real canonical check slug (the accessor asserts this). The profile carries one Verifier per Conformance-Pattern concern with a shared baseline check: `check-plugin-resolution` (Cross-harness plugin-resolution, concern #2) and `check-primary-checkout-commit-refuse-hook-installed` (Worktree-discipline, concern #1).

### `branch_protection_alignment` check

Invocation: `python -m livespec_dev_tooling.checks.branch_protection_alignment`. The check has two responsibilities: a PROTECTION-PRESENT gate and (when protection exists) an ALIGNMENT gate.

The check shells out to `gh api` to read master's branch protection. It distinguishes three outcomes by the GitHub API response, and the distinction is load-bearing because a 404 from the branch-protection endpoint is ambiguous — GitHub returns 404 (not 403) both when a branch is genuinely unprotected AND when the calling token lacks the admin scope required to READ protection (this is deliberate, to avoid leaking repo/branch existence). The disambiguator is the response body's `message` field:

1. **API succeeds with a contexts list** → run the ALIGNMENT gate (below).
2. **API returns the canonical `Branch not protected` 404** → the answer is DEFINITIVELY absent. GitHub emits this exact message only for an admin-scoped token reading a genuinely unprotected branch. The check FAILS (exit `4`) with one structured `fail` finding (`failure_mode` `protection_absent`): master is unprotected and required-check branch protection MUST be enabled. An unprotected master lets PRs auto-merge before CI finishes and lets a red PR land. The finding cites `livespec/SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)".
3. **`gh` unavailable / unauthenticated, OR the API errors for any OTHER reason** (notably a permission/visibility 404 under a token without admin scope — e.g., a generic `Not Found` or `Resource not accessible by integration`), OR the origin remote is not a github.com URL, OR the success payload has an unexpected shape → the check CANNOT distinguish "absent" from "can't-read", so it exits `0` with a structured warning (graceful skip). This keeps local pre-commit runs unblocked and prevents CI false-fails under a token that cannot read protection. The key invariant: the check fails ONLY on a definitive "absent" answer, never on a mere "couldn't read it".

When `.github/workflows/ci.yml` is absent, the check exits `0` (graceful absence-handling): consumers that have not configured GitHub Actions CI have no required-checks list to align against.

ALIGNMENT gate (outcome 1 only). Two-direction comparison between master's required-checks list and `ci.yml`'s `matrix.target` job names, plus a `strict`-off assertion:

- `required_status_checks.strict` is TRUE → ERROR; the check FAILS (exit `4`) with one `fail` finding (`failure_mode` `strict_enabled`). Strict (require-branches-up-to-date) MUST be OFF: per `livespec/SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)", `strict` makes GitHub keep a behind PR current by merging `master` into its branch, injecting a `Merge branch 'master'` commit that violates `required_linear_history` and buries the per-commit Red-Green-Replay TDD trailers. Since `master` accepts only rebase-merges, `strict` adds no correctness guarantee.
- A required check with no matching `ci.yml` job → ERROR; the check FAILS (exit `4`) with one `fail` finding per offending check (`failure_mode` `required_check_missing_from_ci`). This is the v039-D1-style drift: GitHub blocks merges because the required check never reports.
- A `ci.yml` job NOT in the required list → WARNING only (exit `0` contribution); some jobs are intentionally not required (e.g., experimental workflows).

Exit codes: `0` on protection-present-and-aligned OR any graceful skip; `1` on the legacy precondition failure (ci.yml present but `matrix.target` empty or unparseable); `4` on any fail branch (`protection_absent`, `strict_enabled`, or `required_check_missing_from_ci`).

CI-token caveat: the default GitHub Actions `GITHUB_TOKEN` lacks the admin scope needed to READ branch protection, so in a stock Actions job this check always lands on the outcome-3 graceful-skip path (it receives an ambiguous `Not Found`, never the canonical `Branch not protected`) and does NOT enforce. The check is therefore wired into the `just check` aggregate / pre-push — where a maintainer's admin-scoped `gh` token CAN read protection and the fail-on-absent branch actually fires — and is intentionally NOT a required CI matrix entry, which would always-skip and be pointless. A consumer whose CI provides an admin-scoped token (e.g., a PAT secret) MAY additionally wire the check into its CI matrix.

### `no_stale_revise_branches` check

This is a **revise-workflow check** (per §"Shared check inventory"), NOT a canonical per-commit aggregate check: it lives under `livespec_dev_tooling/workflow_checks/` and is invoked by the `/livespec:revise` pre-step, never wired into the `just check` aggregate.

Invocation: `python -m livespec_dev_tooling.workflow_checks.no_stale_revise_branches`. Exit `0` on no stale branches, exit `4` with structured stderr findings on any stale branch.

Algorithm:

1. Read the canonical branch name from `.livespec.jsonc`'s `livespec-impl-git-jsonl.canonical_branch` config key (or any other configured impl plugin's equivalent key). Default: `git symbolic-ref --short refs/remotes/origin/HEAD`, with hard-coded fallback `master`.
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

The check is INVOKED by livespec's `/livespec:revise` SKILL.md as a pre-step refusal (per the coordinating epic's Layer 1), which is the sole caller and the load-bearing enforcement point. Consumers MAY also wire it into doctor's static phase via the impl plugin's contract; that wiring is the impl plugin's choice, not this check's mandate.

There is no downgrade flag. The check always fails hard (exit `4`) on any stale branch; the `--allow-stale-branches` downgrade flag (which previously demoted the findings to `info` and exited `0`) is REMOVED. The revise pre-step is the only invocation, and there is no longer any per-commit-aggregate invocation that needed a downgrade lever — the carve-out is eliminated rather than retained as an escape hatch.

### `primary_checkout_commit_refuse_hook_installed` check

Invocation: `python -m livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed`. Exit `0` on pass OR skipped, exit `4` with structured stderr findings on fail.

The check is a port of the cross-boundary invariant declared at `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary invariants" → §"`primary-checkout-commit-refuse-hook-installed`": every livespec-governed primary checkout MUST install a `.git/hooks/pre-commit` AND a `.git/hooks/pre-push` hook whose body refuses to run when invoked at the primary checkout. The hook is a no-op at secondary worktrees: the current canonical body detects the primary STRUCTURALLY (refuse when `git rev-parse --git-dir` equals `git rev-parse --git-common-dir`; a worktree's git-dir differs), so it is armed on install with no `livespec.primaryPath` arming step to miss; the legacy body detected the primary by comparing `git rev-parse --show-toplevel` to `livespec.primaryPath`. Both detection mechanisms are recognized during the fleet migration. The check reads the two hook files against the cwd's git common dir (`git rev-parse --git-common-dir`), which by git's design resolves to the primary's `.git/hooks/` even when invoked from a secondary worktree.

This mechanism supersedes the v091–v094 `core.bare = true` bare-flag mechanism (the check `primary_checkout_bare_flag_set` in earlier releases). Per `livespec/SPECIFICATION/non-functional-requirements.md` §"Primary-checkout commit-refuse hook", the bare-flag mechanism caused stale-on-disk-read failures at primaries that the hook mechanism does not.

Inputs are project-agnostic — no `[tool.livespec_dev_tooling]` role keys are consumed. The check is layout-independent and qualifies under §"Configurability is the partition criterion" without any role-key wiring.

The documented bootstrap step that corrects a failing hook is the library's own installer, `just install-commit-refuse-hooks` → `python -m livespec_dev_tooling.install_commit_refuse_hooks` (see §"CLI surface"): it writes the structural body — armed on install, no `livespec.primaryPath` arming step to miss — to all three hooks, with `git config livespec.sandboxExempt=true` the single declared exemption (a Fabro sandbox's prepare step sets it so the sandbox's structurally-primary clone can still commit during Red-Green-Replay). This is the Worktree-discipline concern of the Conformance Pattern realized as five slots: Mechanism (the structural body), Installer (the `just` recipe), Verifier (this check), and Exemption (the `sandboxExempt` marker).

The canonical hook body is recognized via a tolerant fingerprint — the check verifies each hook file contains the marker comment, the `exit 1` branch, and at least one of the two recognized primary-detection invocations (substring presence, not exact equality, so portable-shell rewrites such as alternate quoting or extra whitespace are accepted, as is the migration between detection mechanisms):

- the marker comment `# livespec commit-refuse hook`,
- a primary-detection invocation that is EITHER `git rev-parse --git-common-dir` (the structural mechanism, current canonical body) OR `git rev-parse --show-toplevel` (the legacy mechanism), AND
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

### `plugin_resolution` check

Invocation: `python -m livespec_dev_tooling.checks.plugin_resolution`. Exit `0` on pass OR skipped, exit `4` with structured stderr findings on fail.

This is the **Verifier** slot of the Conformance Pattern's **Cross-harness plugin-resolution** concern (concern #2), per `livespec/SPECIFICATION/non-functional-requirements.md` §"Conformance Pattern". Per §"Sibling spec ownership" the specific Verifier inventory lives here, in dev-tooling's own spec; the Pattern's five-slot anatomy is owned by core. The five slots for concern #2: **Contract** — a governed repo's documented command/skill surface MUST resolve *and run* from a fresh session of each *declared* harness; **Mechanism** — real per-harness install records plus marketplace registration; **Installer** — the documented per-harness install procedure; **Verifier** — this check; **Exemption** — an unsupported harness declared explicitly. It catches the ob-4ts breakage class: a plugin adoption that shipped "done" while the `/livespec:*` slash commands did not resolve, because the acceptance tolerated a raw `bd` fallback. A fail-closed Verifier makes that un-shippable.

The check reads the optional `harnesses` declaration from the repo's local `.livespec.jsonc` — a project-config concern (sibling to `template` / `spec_root` / `implementation`), NOT the source-tree-layout schema of `pyproject.toml` `[tool.livespec_dev_tooling]` (§"Schema location" confines that schema to layout role keys). The declaration is an object keyed by harness name; each entry has a `status` of `supported` (with a `canonical_command`) or `exempt` (with a `reason`):

```jsonc
"harnesses": {
  "codex":  { "status": "supported", "canonical_command": "livespec:next" },
  "claude": { "status": "exempt", "reason": "<why this harness is unsupported here>" }
}
```

The check has two layers.

**Always-on declaration-integrity gate** (runs in every `just check`, deterministic, no subprocess). Parse `harnesses`:

- Absent `.livespec.jsonc`, unreadable `.livespec.jsonc` (deferred to the dedicated config-integrity tooling), or a non-object top-level document → exit `0` (skipped; an info log) — a non-governed directory has no harness surface to resolve.
- A `.livespec.jsonc` that exists but declares no `harnesses` key → exit `4` (`failure_mode` `absent_declaration`). The `harnesses` declaration is REQUIRED for every governed repo: the fleet-wide flip of livespec-zs22.7.7 M6 (every governed repo now declares it), enforced here at commit time and reported at error severity by the companion fleet-time `baseline-harnesses` obligation row.
- Present `harnesses` → validate fail-closed: each key MUST be a known harness (`claude`/`codex`); each entry MUST be an object with `status` ∈ {`supported`, `exempt`}; a `supported` entry MUST carry a non-empty `canonical_command`; an `exempt` entry MUST carry a non-empty `reason`. A malformed/unknown/garbled declaration → exit `4` (`failure_mode` `malformed_declaration`). This declaration-integrity gate is what makes the check meaningfully always-invoked per the "carve-outs are a severity lever; always wired + always invoked" discipline.

**Live resolution smoke** (opt-in, env-gated by the SAME `LIVESPEC_E2E_HARNESS` dialect the cli_e2e harness uses — NOT a new env var). In `mock` (the default `just check` value) the live layer does NOT run, so the aggregate stays deterministic and subprocess-free; in `real` each `supported` harness is routed to ITS OWN runner so a codex command is never issued through the claude binary. `claude` runs the genuine cli_e2e smoke (the `CliRunner` seam, whose `RealCliRunner` shells the `claude` binary); `codex` delegates to its repo-local resolution smoke (`check-codex-skill-picker`) rather than mis-routing through claude — the dev-tooling cross-harness live layer is the framework, and a harness whose genuine live smoke is repo-local is routed to a delegated runner that SKIPs. For each declared harness the decision logic — which folds in work-item livespec-mjnv's skip-vs-fail distinction — is:

- `status: exempt` → PASS (the declared Exemption slot; no smoke run).
- `supported` but delegated to a repo-local smoke (codex → `check-codex-skill-picker`) → **SKIP** (the genuine live proof is the delegated check, not this layer).
- `supported` + the harness binary unavailable in this environment → **SKIP**, NOT fail (mjnv: "can't run here" ≠ "command failed"; the smoke runs where the binary is present, e.g. CI).
- `supported` + available + the canonical command resolves and returns (exit `0` through the command surface) → PASS.
- `supported` + available + the canonical command does NOT resolve, OR only a raw-CLI fallback would succeed → **FAIL** (the ob-4ts class). The Verifier ONLY ever invokes the slash-/name-selected command surface (`/livespec:next` on claude; the name-selected `livespec:next` on codex); it NEVER substitutes a raw-CLI (`bd`) success for a command-surface success. The per-harness smoke is pluggable behind an injectable seam (`ResolutionRunner`), so adding a harness is fill-in-the-blank.

Exit `4` if any `supported`+available harness fails to resolve; otherwise exit `0`.

Inputs are project-agnostic — no `[tool.livespec_dev_tooling]` role keys are consumed. The check qualifies under §"Configurability is the partition criterion" without any role-key wiring; its sole input is the local `.livespec.jsonc` `harnesses` declaration.

## Consumer configuration schema

Every shared check that depends on the consumer's source-tree layout MUST read its layout-dependent paths from a `[tool.livespec_dev_tooling]` block in the consuming repo's `pyproject.toml`. The schema is the single source of truth for layout configuration; checks MUST NOT hardcode consumer-specific path constants. Missing keys MUST fall back to livespec-core's historical defaults (codified in §"Default layout fallback" below) so v0.x is backward-compatible — livespec-core's `pyproject.toml` MAY omit the block entirely and keep its bit-identical pre-G.6 behavior.

### Schema location

The schema MUST live at `[tool.livespec_dev_tooling]` in the consumer's root `pyproject.toml`. The library MUST NOT support alternate file locations (no `.livespec.jsonc` fallback, no env-var override). A single, well-known location simplifies the loader and matches the convention every other Python tool (`ruff`, `pyright`, `pytest`, `coverage`) uses for project configuration.

### Role keys

The schema declares roles, not paths-per-check. A role is a layered semantic about the consumer's source tree (e.g., "the I/O layer where `try/except` is wholesale allowed"); each role maps to one or more paths relative to the consumer's repo root. Checks consume roles, not individual paths.

The role-key inventory:

- **`source_trees`** — array of strings. Repo-root-relative paths each shape-checking check walks for `.py` files. Required for every check in the AST-shape class (`assert_never_exhaustiveness`, `keyword_only_args`, `match_keyword_only`, `no_inheritance`, `all_declared`, `main_guard`, `private_calls`, `global_writes`), the style class (`comment_line_anchors`, `no_lloc_soft_warnings`, `claude_md_coverage`), and the test-infrastructure class (`pbt_coverage_pure_modules`, `no_todo_registry`).

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

- `canonical_branch` — read from `.livespec.jsonc`'s `livespec-impl-git-jsonl.canonical_branch` (or equivalent impl-plugin block's key, per the impl plugin's spec).

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

The fallback set MUST stay bit-identical to livespec-core's pre-G.6 behavior; any change is a major-version bump per §"Semver discipline".

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
- **`livespec-impl-git-jsonl`** — MUST publish its own block once Phase G.7 wiring lands. The exact values are the picking-up agent's call at that phase; the schema accommodates whatever layout that consumer adopts.

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

## Consumer compat block — pin-and-bump policy

This section owns the release-level coordination policy between `livespec` and every livespec-governed sibling consumer (`livespec-impl-*` plugins, this library, `livespec-runtime`, and any future sibling). Not every fleet member is a pin-and-bump *consumer*, however: §"Bump-pin policy" carves out *non-pin-consuming* members — fleet members that carry a `livespec-dev-tooling` pin for their own toolchain but ship none of the three shim workflows and so take no part in this release/bump web. It was relocated here from `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" at livespec v103/v104; livespec's section is now a pointer at this one. §"Cross-repo coordination automation surface" below owns the automation that implements this policy.

### `compat` block schema

Every consumer MUST declare a top-level section in its `.livespec.jsonc` keyed by the consumer's own plugin / library name (e.g., `livespec-impl-beads`, `livespec-dev-tooling`, `livespec-runtime`), carrying a `compat` block with two REQUIRED fields:

- `livespec` — a semver range describing the supported `livespec` versions (e.g., `">=2.0.0,<3.0.0"`).
- `pinned` — the specific `livespec` release tag the consumer currently runs against (e.g., `"v2.3.0"`).

`.livespec.jsonc` MUST NOT carry secrets; the `compat` block contains only non-sensitive version metadata. This is the same block shape the pin-autodiscovery walk recognizes per §"Pin autodiscovery rules" (the `.livespec.jsonc` `compat.pinned` format).

### Bump-pin policy

- **Every consumer pins.** Each consumer's automation and autonomous workflows MUST run against the pinned `livespec` release, NEVER against HEAD. Running against HEAD bypasses the audited coordination mechanism and is an out-of-contract operation.
- **Releases fire bump-pin PRs.** When `livespec` ships a new release tag, a bump-pin pull request MUST be opened automatically in every consumer per §"Cross-repo coordination automation surface". The bump-pin PR's acceptance criterion is that the consumer continues to pass its post-bump invariant suite — the consumer's OWN `just check` aggregate, gated by its branch-protection required status checks on the bump PR (not by the bump workflow itself), per §"`reusable-bump-pin-from-dispatch.yml`" and §"Fallback to known-good pin".
- **Breaking changes land additively.** Breaking contract changes in `livespec` MUST be landed additively: the old contract surface stays valid for one or more releases; every consumer migrates at its own cadence; only after the active consumers' releases adopting the new surface ship MAY the old surface be removed in a subsequent `livespec` release (the `N` / `N-1` support-window pattern).
- **Pin-and-bump consumers vs. non-pin-consuming members.** The bullets above bind every pin-and-bump *consumer* — a fleet member that carries the three shim workflows (§"Cross-repo coordination automation surface") and so participates in the automated release/bump web. A fleet member MAY instead be a *non-pin-consuming member*: it carries a `livespec-dev-tooling` pin for its own developer toolchain (asserted by the `dev-tooling-pin` fleet-conformance obligation row) but ships none of the three shims, is sent no bump-pin PR, and has its pin freshness monitored centrally — at *warning* severity — by the `dev-tooling-pin` row's staleness leg rather than auto-bumped. The Control-Plane console (`livespec-console-beads-fabro`, the `console` repo class) is the first such member: it consumes `livespec-dev-tooling` for its `just check` toolchain yet ships no command/skill surface and no coordination shims.

### Enforcement status

livespec core's doctor no longer enforces any of this: the `contract-version-compatibility` invariant was DROPPED from core's catalogue at livespec v103. Compatibility enforcement, if any, is this repository's choice — e.g., a shared check under `livespec_dev_tooling/checks/` that validates `compat` block presence/shape or pin freshness — and MAY be specified by a follow-on propose-change. This proposal deliberately does NOT decide whether or how to enforce.

## Cross-repo coordination automation surface

This section codifies the reusable GitHub workflow surface that implements the pin-and-bump policy declared in §"Consumer compat block — pin-and-bump policy" uniformly across every pin-and-bump *consumer* repository (the non-pin-consuming fleet members carved out in §"Bump-pin policy" — e.g. the Control-Plane console — carry none of this surface). The contract here is the canonical implementation specification; the preceding section owns the policy (relocated from livespec core at v103/v104, whose `contracts.md` §"Cross-repo coordination — pin-and-bump" now points here). Per the DRY discipline, every consumer's per-repo coordination footprint is three thin shim workflows that delegate to the reusable workflows defined here; no coordination logic is duplicated across consumers.

### Sibling discovery

The fleet member set is defined by livespec core's committed `.livespec-fleet-manifest.jsonc` (at the livespec repo root), fetched from livespec master at run time, per `livespec/SPECIFICATION/non-functional-requirements.md` §"Fleet membership contract" (livespec v108). Both the release fan-out (§"`reusable-release-dispatch.yml`") and the fleet-conformance check (§"Fleet surface — central conformance and reconcile") MUST read the manifest; neither derives the member set from topic search. A repository is excluded from dispatch by being absent from the manifest — adding or removing a member is a manifest change in livespec core, not an edit to this library.

Every member repository MUST still carry the `livespec-sibling` GitHub topic on its repository metadata — demoted from source of truth to a discovery safety net: the fleet-conformance discovery sweep flags any owner repository matching `livespec-*` naming or carrying the topic that is NOT declared in the manifest, so a half-wired or unregistered repo becomes a red fleet finding rather than an invisible straggler.

The member list MUST NOT live in this library — the surviving intent of the original static-registry prohibition. Fleet-level facts are livespec-core-owned, so adding a new sibling still requires NO edits to this library's source; the register-first repo-birth procedure (scaffold → register in the manifest FIRST → run the reconcile CLI → fleet conformance green) makes the half-wired interval loud instead of silent.

### Fleet surface — central conformance and reconcile

`livespec_dev_tooling/fleet/` is a non-canonical surface (central, not per-repo: it asserts the WHOLE fleet from one vantage point, so it lives outside `livespec_dev_tooling/checks/` and is NOT a canonical check slug). It implements both modes of the fleet membership contract ("assert mode is CI; reconcile mode is wiring") against ONE shared obligation-table definition:

- **Shared obligation table** (`livespec_dev_tooling/fleet/contract.py`). One statically-enumerated table of per-member obligation rows consumed by BOTH modes; each row carries an assert function and, where a machine fix exists from this vantage point, a reconcile reference (otherwise a `manual_hint`). `parse_manifest` parses livespec core's `.livespec-fleet-manifest.jsonc`.
- **Assert mode** — `python -m livespec_dev_tooling.fleet.fleet_conformance`. Fetches the manifest from livespec master at run time, asserts every member's per-class obligations from the central vantage point (the piece repo-local CI cannot provide — a repo missing wiring never fails checks it does not run), and runs the discovery sweep per §"Sibling discovery". Env lever `LIVESPEC_RUN_FLEET_CONFORMANCE` (the single self-documenting per-check lever for network-dependent checks): unset → the check logs "skipped" and exits 0; set to a non-empty value → the full sweep runs. The check is always wired — into this repo's `just check` aggregate (`check-fleet-conformance`), its CI job, the scheduled `fleet-conformance.yml` workflow, and the release fan-out's blocking preflight — with the lever set in the contexts that run it; no external gate, no silent skip. Exit codes: `0` (lever unset, or no error-severity finding), `1` (precondition failure with the lever set: owner unresolvable, or the manifest unfetchable / unparseable), `4` (one or more error-severity findings; warning-severity findings such as pin staleness log but do not fail).
- **Reconcile mode** — `python -m livespec_dev_tooling.fleet.wire_fleet_member --repo <member>`. Operator-invoked (NOT CI; no run lever), idempotent: walks the SAME obligation table for ONE member and, for each violated row, applies the row's reconcile reference — secrets pushed from the 1Password-wrapper environment (values flow env→stdin only), branch protection set from the member's ci.yml matrix, the topic applied, ONE shim-workflow PR opened for missing shims — or surfaces the row's `manual_hint` where no machine fix exists from this vantage point. MUST be invoked under `with-livespec-env.sh` so the secret projection is present. Exits `1` when `--repo` is NOT in the manifest (register-first: a repo is wired only after it is a declared member). Secret VALUES never appear in any output stream.

### Reusable workflow inventory

The library MUST ship the following reusable workflows under `.github/workflows/`, each with a `workflow_call` trigger and the inputs/outputs declared below. Each workflow's path is the semver-stable identifier consumers reference via `uses:`.

#### `reusable-release-dispatch.yml`

Fan-out dispatcher invoked by each sibling's own `release-dispatch.yml` shim on `on: release: types: [published]`.

Inputs:
- `source_repo` (string, required) — the publishing repository's short name (e.g., `livespec-runtime`).
- `tag` (string, required) — the published release tag (e.g., `v0.3.0`).
- `release_url` (string, required) — the GitHub release page URL, used in downstream PR descriptions.

Secrets: `APP_ID`, `APP_PRIVATE_KEY` (inherited via `secrets: inherit`).

Behavior: reads the fleet member set per §"Sibling discovery" (livespec core's `.livespec-fleet-manifest.jsonc`, fetched from livespec master at run time), excludes `source_repo` from the dispatch matrix, fires a `repository_dispatch` event to each remaining member carrying the payload contract per §"`repository_dispatch` payload contract". A 404 from any sibling (e.g., App not installed) surfaces as a workflow annotation and does NOT fail the dispatch loop (soft-fail per §"Soft-fail semantics").

Fleet-conformance preflight (BLOCKING): a `fleet-preflight` job runs the central fleet-conformance check (assert mode per §"Fleet surface — central conformance and reconcile", with the env lever set) against livespec-dev-tooling master BEFORE any `sibling-released` dispatch goes out; the dispatch matrix `needs` this job, so a red fleet fails the release fast and loudly instead of silently skipping an unwired member. No-circular-gating guarantee: every conformance finding is fixable without a dev-tooling release and without this fan-out running — the reconcile CLI is operator-run, shim-workflow PRs land via member-repo CI, and manifest changes land via livespec core.

#### `reusable-bump-pin-from-dispatch.yml`

Per-consumer handler invoked by each sibling's own `bump-pin-from-dispatch.yml` shim on `on: repository_dispatch: types: [sibling-released]`.

Inputs:
- `source_repo` (string, required) — extracted from `client_payload.source_repo`.
- `tag` (string, required) — extracted from `client_payload.tag`.
- `release_url` (string, optional) — extracted from `client_payload.release_url`; included in the PR body for traceability.

Behavior: clones the consumer repository, runs the pin-autodiscovery walk per §"Pin autodiscovery rules", edits every matching pin to `tag`, commits with the `chore:`-prefixed message per §"PR commit-message convention", opens an auto-merge PR via the GitHub App per §"GitHub App auth model". The workflow deliberately does NOT run the consumer's `just check`: the authoritative post-bump gate is the consumer's OWN CI / branch-protection required status checks on the opened auto-merge PR — not an in-workflow check run in this incomplete CI environment, which lacks the consumer's installed plugin, its core checkout, and its installed hooks, so a faithful `just check` is not reconstructable here. The `--auto` merge defers the merge until those required checks pass, per §"Fallback to known-good pin".

Rewrite path: `github_workflow_uses_ref` pins are rewritten by replacing the literal `@<current_value>` suffix on the matched `uses:` line with `@<tag>` — equivalent to the sed-replace discipline used for other formats, but scoped to the specific `pin_key` prefix so that other `uses:` references in the same file are not modified.

When autodiscovery surfaces zero matching pins (the consumer does not depend on `source_repo`), the workflow exits `0` with a workflow annotation explaining the no-op.

When the consumer's `.vendor.jsonc` carries an entry for the normalized form of `source_repo`, the workflow ADDITIONALLY invokes the consumer's `just vendor-update <lib>` recipe before committing, so re-vendoring lands atomically in the same commit as the manifest pin update.

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
- **`.github/workflows/*.yml` / `*.yaml` `uses:` ref** — every line in any GitHub Actions workflow file (under `.github/workflows/`) matching the form `uses: <owner>/<repo>/<path>@<ref>`, where `<path>` is a non-empty path segment (distinguishing reusable-workflow calls from simple action references such as `uses: actions/checkout@v4` which have no path segment). The pin's source repo is derived from the `<repo>` segment verbatim. `current_value` is `<ref>`. `pin_key` is the full `uses:` reference excluding the `@<ref>` suffix (`<owner>/<repo>/<path>`), which uniquely identifies the line for targeted rewriting. Lines whose `<repo>` segment does not match the requested `--source-repo` filter are excluded per the standard source-repo-filter semantics.

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

The rationale for App-token over `GITHUB_TOKEN` mirrors the existing `auto-enable-merge.yml` and bump-pin shim workflow choices in livespec: pushes authored by `GITHUB_TOKEN` do not trigger downstream CI workflows (GitHub's workflow-recursion ceiling), which would leave bump PRs permanently `BLOCKED` with no CI re-runs against the updated head SHA.

### Soft-fail semantics

A 404 response from a target sibling during dispatch (App not installed on that sibling, or repository missing) MUST surface as a workflow annotation and MUST NOT fail the dispatch loop. Other 4xx and 5xx responses MUST fail the dispatch job for that sibling but MUST NOT cascade to other siblings (each sibling occupies its own matrix entry with `fail-fast: false`).

### PR commit-message convention

Bump-pin PRs MUST use the Conventional Commits `chore:` prefix on the PR title and the commit subject. The `chore:` prefix is explicitly excluded from triggering a release-please version bump per the Conventional Commits → semver mapping at `livespec/SPECIFICATION/contracts.md` §"Plugin versioning"; this prevents an automatic-bump-PR cycle where a sibling's release triggers a bump PR in this library which triggers another release of this library which triggers another round of bump PRs.

The PR title template is `chore(deps): bump <source_repo> pin to <tag>`. The PR body MUST include the `release_url` from the dispatch payload for traceability.

### Pin-freshness threshold defaults

The `staleness_threshold_releases` input to `reusable-pin-freshness.yml` defaults to `1` — any pin one or more releases behind the latest tag triggers a bump PR. A consumer MAY override via the input on its `pin-freshness.yml` shim if its cadence demands higher tolerance for drift.

The cron cadence is consumer-owned; the dev-tooling reusable workflow accepts whatever schedule the shim declares. The recommended cadence is daily (`0 13 * * *`) — frequent enough to catch missed dispatches within one business day, infrequent enough to avoid noise.

### Fallback to known-good pin

When a bump PR fails its required status checks on the new pin, the bump PR MUST remain open with the check failure marked. The bump-pin workflow itself does NOT run the consumer's `just check`; it opens the PR with `--auto --rebase` and the consumer's OWN CI / branch-protection required status checks gate the merge, so a check failure surfaces on the PR's status checks rather than inside the bump workflow's incomplete CI environment. The consumer's last green pin remains the active pin on `master` until the failure is resolved.

Resolution paths, in order of preference:

1. **Auto-rollback (future).** A planned future workflow `reusable-pin-rollback.yml` MAY revert the pin to the most recent commit on `master` whose `just check` last passed, on detection of N consecutive failing bump attempts. This future surface is OUT OF SCOPE for v1 and is named here only to reserve the design space; a subsequent propose-change cycle defines its contract.
2. **Manual pin to known-good.** A human contributor edits the pin file directly to a known-good tag, commits with the `chore:` prefix per §"PR commit-message convention", and merges. This is the v1 fallback for any failure the planned auto-rollback would have handled.

The `bump-pin` workflow MUST NOT silently force-push past a failing check. The auto-merge label is the consumer's standard auto-merge label (configurable per consumer via repo settings); the workflow only attaches the label, it does not bypass branch-protection gates.

### Retry semantics (rerun vs fresh dispatch)

`gh run rerun` (and the Actions UI re-run button) re-executes a workflow run with the ORIGINAL event payload. `actions/checkout` resolves the event's pinned `github.sha` onto the branch ref, so the rerun literally builds the stale commit labeled as `origin/master`. A rerun therefore can NEVER observe commits merged to the target branch after the original event.

Consequently:

- **Rerun is the correct retry ONLY for transient/flake failures** where rebuilding the same SHA is the point — e.g., the known GitHub release-CDN 504 and uv cache hardlink flakes.
- **Any retry intended to pick up a fix merged to the target branch after the event MUST be a fresh event, not a rerun.** For the bump fan-out, the canonical form is:

  ```
  gh api repos/<owner>/<repo>/dispatches \
    -f event_type=sibling-released \
    -f 'client_payload[source_repo]=<repo>' \
    -f 'client_payload[tag]=<tag>' \
    -f 'client_payload[release_url]=<url>'
  ```

  with the payload shape per §"`repository_dispatch` payload contract".
- **This rule applies to every event-triggered workflow in the fleet** (`repository_dispatch`, `release`, `push`) — when the fix landed post-event, re-trigger the event; never rerun.

Mechanical guard: `reusable-bump-pin-from-dispatch.yml` SHALL detect the invalid retry — when `github.run_attempt > 1` AND the consumer's default-branch HEAD no longer equals the event-pinned SHA, the workflow MUST fail fast with an actionable error that includes the fresh-dispatch command for the in-flight tag. A flake rerun on an unmoved branch proceeds normally. Refusal on ANY post-event movement — related to the failure or not — is correct: building a stale HEAD also produces BEHIND PRs, which is undesirable regardless of why the branch moved.

### Self-hosting

The library is itself a sibling consumer of its own coordination automation surface. The library's own `.github/workflows/` MUST include the three consumer shims (`release-dispatch.yml`, `bump-pin-from-dispatch.yml`, `pin-freshness.yml`) and the repository MUST carry the `livespec-sibling` topic. The shims delegate to the reusable workflows at the library's own currently-pinned release tag; consequently the library pin-and-bumps itself when livespec releases.

The self-hosting bootstrap is a one-time manual step: a human contributor authors the three consumer shims with their `uses:` lines pinned to a hand-chosen bootstrap tag (typically the first tag of this library that ships all three reusable workflows under `.github/workflows/`), tags the bootstrap release, and verifies that the first dispatch from a sibling release reaches this library and opens a bump-PR. Thereafter the system perpetuates via its own dispatches and the manual step is never repeated.

### Semver coverage extension

The semver-stable surface declared in §"Semver discipline" is hereby extended to cover the following new elements introduced by this section:

- Each reusable workflow's path AND its declared inputs / outputs / secrets contract.
- The `repository_dispatch` payload contract (event type + `client_payload` shape).
- The sibling discovery mechanism (the `livespec-sibling` topic name).
- The pin autodiscovery rules' format coverage (adding a new pin format is a MINOR bump; removing or breaking compatibility of an existing format is a MAJOR bump).

Pure implementation changes that preserve every element above MAY land via PATCH bump per the existing discipline.

## Semver discipline

The library's semver-stable surface — the canonical enumeration required by `livespec/SPECIFICATION/contracts.md` §"Shared code sync — livespec-dev-tooling" — is:

- The `python -m livespec_dev_tooling.checks.<slug>` invocation set (each slug's argv contract and exit-code semantics per §"CLI surface" and §"Exit-code table").
- The composite Action paths and their declared inputs / outputs (per §"Composite Actions wire contract").
- The reusable workflow paths and their declared inputs / outputs / secrets / concurrency (per §"Reusable workflows wire contract").
- The `[tool.livespec_dev_tooling]` consumer-configuration key set (per §"Consumer configuration schema").
- The cross-repo coordination automation surface elements pinned by §"Cross-repo coordination automation surface" §"Semver coverage extension" — the `repository_dispatch` payload contract, the `livespec-sibling` GitHub topic name, and the pin autodiscovery rules' format coverage.

Bump rules:

- **MAJOR** — any change that REMOVES, RENAMES, or BREAKS-COMPATIBILITY-OF a surface element (including removing or incompatibly reinterpreting a recognized `[tool.livespec_dev_tooling]` key).
- **MINOR** — adding a new check, a new composite Action, a new reusable workflow, a new optional configuration key, or a new pin-autodiscovery format.
- **PATCH** — a pure implementation change that preserves every surface element.

The Conventional Commits → semver mapping (`feat:` MINOR, `fix:` PATCH, `feat!:` MAJOR, etc.) MUST be honored by every commit on `master` so that `release-please` derives the correct next version (see §"Versioning").

## Versioning

Releases are managed by `release-please` per the Conventional Commits → semver mapping documented in `livespec/SPECIFICATION/contracts.md` §"Plugin versioning". The `pyproject.toml` `version` field, the `.release-please-manifest.json` entry, and the git tag MUST stay in lockstep; `release-please` is the only tool that writes to these.
