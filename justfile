# justfile — livespec-dev-tooling dev-tooling task runner.
#
# Authority: livespec/SPECIFICATION/non-functional-requirements.md
#   §"Enforcement-suite invocation" — `just` is the canonical entry
#   point for every dev-tooling invocation. Lefthook and CI MUST
#   delegate to `just <target>`; direct tool invocations are banned
#   (enforced by the no-direct-tool-invocation check).
#
# Authority: livespec/SPECIFICATION/contracts.md
#   §"Pre-commit step ordering" — gates wired in lefthook.yml mirror
#   the spec-required ordering.
#   §"Shared code sync — livespec-dev-tooling" — this library is the
#   canonical home for the shared enforcement-suite checks. The
#   `check:` aggregate below wires EVERY canonical check slug emitted
#   by `python -m livespec_dev_tooling.canonical_checks --json`, in
#   alphabetical order, per the wiring-completeness invariant
#   enforced by `check-aggregate-completeness` (epic li-univck Phase
#   1.3). livespec-dev-tooling dogfoods the full canonical aggregate
#   against itself from v0.4.0 onwards (epic li-univck Phase 1.4,
#   work-item li-ldtv03).

# Default to listing targets when no recipe is invoked.
default:
    @just --list

# ---------------------------------------------------------------
# First-time setup.
# ---------------------------------------------------------------

# Install the lefthook git hooks so pre-commit / commit-msg / pre-push
# gates fire automatically. Re-running is idempotent: `lefthook install`
# rewrites the hook files atomically.
bootstrap:
    uv sync --all-groups
    uv run lefthook install
    # Idempotent install of the canonical livespec commit-refuse hook
    # at the primary checkout's `.git/hooks/pre-commit` AND
    # `.git/hooks/pre-push`, plus the `livespec.primaryPath` config
    # entry the hook body reads. Per livespec/SPECIFICATION/
    # non-functional-requirements.md §"Commit-refuse hook bootstrap
    # procedure"; self-hosts the `check-primary-checkout-commit-refuse-
    # hook-installed` shared check shipped at v0.5.0. Targets
    # `git rev-parse --git-common-dir` so the install lands in the
    # primary's shared hooks directory regardless of whether bootstrap
    # is invoked from the primary or a secondary worktree. Runs AFTER
    # `lefthook install` because the canonical hook DELEGATES to
    # `lefthook run <hook-name>` after the refuse-at-primary check —
    # overwriting the lefthook stubs is intentional, the canonical
    # hook subsumes them.
    cp dev-tooling/livespec-commit-refuse-hook.sh "$(git rev-parse --git-common-dir)/hooks/pre-commit"
    cp dev-tooling/livespec-commit-refuse-hook.sh "$(git rev-parse --git-common-dir)/hooks/pre-push"
    chmod +x "$(git rev-parse --git-common-dir)/hooks/pre-commit" "$(git rev-parse --git-common-dir)/hooks/pre-push"
    git config --file "$(git rev-parse --git-common-dir)/config" livespec.primaryPath "$(git rev-parse --git-common-dir | xargs dirname | xargs realpath)"

# ---------------------------------------------------------------
# Aggregate check — wires EVERY canonical check slug emitted by
# `python -m livespec_dev_tooling.canonical_checks --json`, in
# alphabetical order. Enforced by `check-aggregate-completeness`
# (epic li-univck Phase 1.3). Repo-private extras (none today) would
# appear AFTER the canonical block per the same invariant.
#
# Continues on failure (matches CI fail-fast: false); exits non-zero
# with the failure list if any target failed.
# ---------------------------------------------------------------

check:
    #!/usr/bin/env bash
    set -uo pipefail
    targets=(
        check-aggregate-completeness
        check-all-declared
        check-assert-never-exhaustiveness
        check-branch-protection-alignment
        check-check-coverage-incremental
        check-check-mutation
        check-check-tools
        check-claude-md-coverage
        check-comment-line-anchors
        check-commit-pairs-source-and-test
        check-file-lloc
        check-global-writes
        check-heading-coverage
        check-keyword-only-args
        check-main-guard
        check-master-ci-green
        check-match-keyword-only
        check-newtype-domain-primitives
        check-no-direct-tool-invocation
        check-no-except-outside-io
        check-no-inheritance
        check-no-lloc-soft-warnings
        check-no-raise-outside-io
        check-no-stale-revise-branches
        check-no-todo-registry
        check-no-write-direct
        check-pbt-coverage-pure-modules
        check-per-file-coverage
        check-primary-checkout-commit-refuse-hook-installed
        check-private-calls
        check-public-api-result-typed
        check-red-green-replay
        check-rop-pipeline-shape
        check-skill-invocation-paths
        check-supervisor-discipline
        check-tests-mirror-pairing
        check-vendor-manifest
        check-wrapper-shape
    )
    failed=()
    for t in "${targets[@]}"; do
        printf '\n::: just %s\n' "$t"
        if ! just "$t"; then
            failed+=("$t")
        fi
    done
    if [[ ${#failed[@]} -gt 0 ]]; then
        printf '\nFailed targets (%d):\n' "${#failed[@]}"
        printf '  - %s\n' "${failed[@]}"
        exit 1
    fi
    printf '\nAll %d targets passed.\n' "${#targets[@]}"

# ---------------------------------------------------------------
# Tool-backed checks. Not canonical-aggregate targets; invoked from
# canonical recipes (check-lint runs ruff check, etc.) but the slugs
# `check-lint` / `check-format` / `check-coverage` / `check-types`
# are NOT canonical (not in canonical_checks.py's discovery set).
# They remain as helper recipes; they are not wired into the
# `check:` aggregate's `targets=(...)`.
# ---------------------------------------------------------------

check-lint:
    uv run ruff check .

check-format:
    uv run ruff format --check .

check-types:
    uv run pyright

check-coverage:
    #!/usr/bin/env bash
    set -uo pipefail
    if [[ -n "${LIVESPEC_PRECOMMIT_RED_MODE:-}" ]]; then
        echo ":: check-coverage skipped (Red-mode pre-commit; verified at Green amend)"
        exit 0
    fi
    uv run pytest -n auto --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing

# ---------------------------------------------------------------
# Canonical aggregate recipes — one per canonical slug emitted by
# `python -m livespec_dev_tooling.canonical_checks --json`. Each
# resolves to `uv run python -m livespec_dev_tooling.checks.<slug>`
# with the snake_case slug.
# ---------------------------------------------------------------

# Wiring-completeness gate — verifies the targets=(...) array in this
# very justfile carries every canonical slug in alphabetical order
# (epic li-univck Phase 1.3, work-item li-aggchk). Self-bootstrapping:
# wiring this slug forces wiring every other canonical slug.
check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness

check-all-declared:
    uv run python -m livespec_dev_tooling.checks.all_declared

check-assert-never-exhaustiveness:
    uv run python -m livespec_dev_tooling.checks.assert_never_exhaustiveness

check-branch-protection-alignment:
    uv run python -m livespec_dev_tooling.checks.branch_protection_alignment

# Path-scoped fast-feedback variant of check-coverage. Requires
# `--paths <impl_path> [<impl_path>...]` (repo-root-relative). The
# canonical aggregate invokes this with NO args (since no impl
# paths are scoped at aggregate time), so the recipe short-circuits
# when called with zero args — the per-file 100% gate is already
# enforced by `check-per-file-coverage` against the full tree. The
# interactive developer use case passes `--paths` explicitly:
# `just check-check-coverage-incremental --paths livespec_dev_tooling/checks/foo.py`.
check-check-coverage-incremental *args:
    #!/usr/bin/env bash
    set -uo pipefail
    if [[ -z "{{args}}" ]]; then
        echo ":: check-check-coverage-incremental skipped (no --paths provided; aggregate-mode no-op)"
        echo ":: full-tree per-file 100% gate is enforced by check-per-file-coverage"
        exit 0
    fi
    uv run python -m livespec_dev_tooling.checks.check_coverage_incremental {{args}}

# Release-gate ONLY in livespec; runs unconditionally here as part of
# the canonical aggregate self-host. If too slow for per-commit
# cadence, file a follow-up to move to release-tag CI only.
check-check-mutation:
    uv run python -m livespec_dev_tooling.checks.check_mutation

check-check-tools:
    uv run python -m livespec_dev_tooling.checks.check_tools

check-claude-md-coverage:
    uv run python -m livespec_dev_tooling.checks.claude_md_coverage

check-comment-line-anchors:
    uv run python -m livespec_dev_tooling.checks.comment_line_anchors

check-commit-pairs-source-and-test:
    uv run python -m livespec_dev_tooling.checks.commit_pairs_source_and_test

check-file-lloc:
    uv run python -m livespec_dev_tooling.checks.file_lloc

check-global-writes:
    uv run python -m livespec_dev_tooling.checks.global_writes

check-heading-coverage:
    uv run python -m livespec_dev_tooling.checks.heading_coverage

check-keyword-only-args:
    uv run python -m livespec_dev_tooling.checks.keyword_only_args

check-main-guard:
    uv run python -m livespec_dev_tooling.checks.main_guard

check-master-ci-green:
    uv run python -m livespec_dev_tooling.checks.master_ci_green

check-match-keyword-only:
    uv run python -m livespec_dev_tooling.checks.match_keyword_only

check-newtype-domain-primitives:
    uv run python -m livespec_dev_tooling.checks.newtype_domain_primitives

check-no-direct-tool-invocation:
    uv run python -m livespec_dev_tooling.checks.no_direct_tool_invocation

check-no-except-outside-io:
    uv run python -m livespec_dev_tooling.checks.no_except_outside_io

check-no-inheritance:
    uv run python -m livespec_dev_tooling.checks.no_inheritance

# Release-gate ONLY in livespec; runs unconditionally here as part of
# the canonical aggregate self-host.
check-no-lloc-soft-warnings:
    uv run python -m livespec_dev_tooling.checks.no_lloc_soft_warnings

check-no-raise-outside-io:
    uv run python -m livespec_dev_tooling.checks.no_raise_outside_io

# Refuse new revise passes while a stale spec/* branch is ahead of
# master. Invoked by livespec's /livespec:revise SKILL.md pre-step
# refusal; included in the canonical aggregate for cross-cutting
# self-host coverage.
check-no-stale-revise-branches:
    uv run python -m livespec_dev_tooling.checks.no_stale_revise_branches

# Release-gate ONLY (paired with check-no-lloc-soft-warnings and
# check-check-mutation in the release-tag CI workflow). Gated by
# LIVESPEC_RELEASE_GATE so the canonical aggregate can wire the slug
# (per epic li-univck Phase 1.4 wiring-completeness) without making
# per-commit `just check` runs choke on TODO entries that are
# legitimate authoring placeholders. The release-tag workflow MUST
# set LIVESPEC_RELEASE_GATE=1 before invoking this target. The
# wiring-vs-release-gate tension (this slug is canonical-aggregate
# AND release-only — semantics are mutually inconsistent at face
# value) is a known finding from the Phase 1.4 self-host PR;
# follow-up work-item will revisit at the spec layer.
check-no-todo-registry:
    #!/usr/bin/env bash
    set -uo pipefail
    if [[ -z "${LIVESPEC_RELEASE_GATE:-}" ]]; then
        echo ":: check-no-todo-registry skipped (LIVESPEC_RELEASE_GATE unset; release-gate-only check)"
        exit 0
    fi
    uv run python -m livespec_dev_tooling.checks.no_todo_registry

check-no-write-direct:
    uv run python -m livespec_dev_tooling.checks.no_write_direct

check-pbt-coverage-pure-modules:
    uv run python -m livespec_dev_tooling.checks.pbt_coverage_pure_modules

# Per-file 100% line+branch coverage gate. Reads `.coverage`; we run
# pytest --cov upfront in the recipe so the data file exists when the
# canonical aggregate invokes the slug as a self-contained check.
# Red-mode pre-commit skip preserved (commit-msg replay hook is the
# verifier; aggregate-time coverage is not load-bearing in Red mode).
check-per-file-coverage:
    #!/usr/bin/env bash
    set -uo pipefail
    if [[ -n "${LIVESPEC_PRECOMMIT_RED_MODE:-}" ]]; then
        echo ":: check-per-file-coverage skipped (Red-mode pre-commit; verified at Green amend)"
        exit 0
    fi
    uv run pytest -n auto --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
    uv run python -m livespec_dev_tooling.checks.per_file_coverage

# Universal cross-boundary invariant: every livespec-governed primary
# checkout MUST install `.git/hooks/pre-commit` AND `.git/hooks/pre-push`
# hooks whose body matches the canonical livespec commit-refuse
# fingerprint. Supersedes the v091-v094 `core.bare = true` mechanism
# per livespec v095 §"Primary-checkout commit-refuse hook"; the
# bare-flag mechanism caused stale-on-disk-read failures at primaries
# that the hook mechanism does not. CI's metadata matrix runs this
# target against a populated working tree (no `core.bare` gating
# step needed); fresh-clone failures are corrected by `just bootstrap`.
check-primary-checkout-commit-refuse-hook-installed:
    uv run python -m livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed

check-private-calls:
    uv run python -m livespec_dev_tooling.checks.private_calls

check-public-api-result-typed:
    uv run python -m livespec_dev_tooling.checks.public_api_result_typed

# Trailer-based Red→Green replay verification (hard gate). Invoked
# by lefthook commit-msg stage with the commit-message file path as
# argv[1]. The canonical aggregate invokes this with NO msg_path
# (since no in-flight commit message exists at aggregate time), so
# the recipe short-circuits when called with no args — the load-
# bearing verifier is the commit-msg hook, not `just check`.
check-red-green-replay *args:
    #!/usr/bin/env bash
    set -uo pipefail
    if [[ -z "{{args}}" ]]; then
        echo ":: check-red-green-replay skipped (no msg_path provided; aggregate-mode no-op)"
        echo ":: load-bearing verifier is the commit-msg hook (lefthook)"
        exit 0
    fi
    uv run python -m livespec_dev_tooling.checks.red_green_replay {{args}}

check-rop-pipeline-shape:
    uv run python -m livespec_dev_tooling.checks.rop_pipeline_shape

check-skill-invocation-paths:
    uv run python -m livespec_dev_tooling.checks.skill_invocation_paths

check-supervisor-discipline:
    uv run python -m livespec_dev_tooling.checks.supervisor_discipline

check-tests-mirror-pairing:
    uv run python -m livespec_dev_tooling.checks.tests_mirror_pairing

check-vendor-manifest:
    uv run python -m livespec_dev_tooling.checks.vendor_manifest

check-wrapper-shape:
    uv run python -m livespec_dev_tooling.checks.wrapper_shape

# ---------------------------------------------------------------
# Pre-commit aggregate — Red-mode-aware. Classifies the staged
# tree shape; sets LIVESPEC_PRECOMMIT_RED_MODE=1 in Red mode so
# check-coverage skips (commit-msg replay hook is the verifier).
# Pre-push and CI keep invoking `just check` directly.
# ---------------------------------------------------------------

check-pre-commit:
    #!/usr/bin/env bash
    set -uo pipefail
    staged=$(git diff --cached --name-only --diff-filter=AM)
    py_staged=$(echo "$staged" | grep -E '\.py$' || true)
    test_staged=$(echo "$staged" | grep -E '^tests/.*\.py$' || true)
    impl_staged=$(echo "$staged" | grep -E '^livespec_dev_tooling/.*\.py$' || true)
    test_count=0
    impl_count=0
    [[ -n "$test_staged" ]] && test_count=$(echo "$test_staged" | wc -l)
    [[ -n "$impl_staged" ]] && impl_count=$(echo "$impl_staged" | wc -l)
    if [[ -z "$py_staged" ]]; then
        echo ":: doc-only mode detected (zero .py files staged): running just check-pre-commit-doc-only"
        echo ":: pre-push + CI keep the full aggregate as the load-bearing safety net"
        just check-pre-commit-doc-only
        exit $?
    fi
    if [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; then
        echo ":: Red-mode shape detected: $test_staged"
        echo ":: skipping check-coverage (commit-msg replay hook is the verifier)"
        export LIVESPEC_PRECOMMIT_RED_MODE=1
    fi
    just check

# When zero `.py` files are staged, `check-pre-commit` delegates here.
# Pre-push delegates here via `check-pre-push` for zero-py changesets.
check-pre-commit-doc-only:
    #!/usr/bin/env bash
    set -uo pipefail
    echo ":: doc-only subset (no repo-metadata checks wired yet)"
    exit 0

# Skip the Python-code check subset when the pushed commits contain
# zero `.py` changes. Falls back to `origin/master` when no upstream
# branch is configured locally.
check-pre-push:
    #!/usr/bin/env bash
    set -uo pipefail
    upstream=$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null || echo "origin/master")
    changeset=$(git diff --name-only "${upstream}..HEAD")
    py_changed=$(echo "$changeset" | grep -E '\.py$' || true)
    if [[ -z "$py_changed" ]]; then
        echo ":: doc-only push detected (zero .py changes vs ${upstream}): running check-pre-commit-doc-only"
        just check-pre-commit-doc-only
        exit $?
    fi
    just check

# ---------------------------------------------------------------
# Pre-commit auxiliary gates.
# ---------------------------------------------------------------

# Ruff fix + format on staged .py files BEFORE the rest of the
# pre-commit gate runs. Non-blocking — unfixable issues fall through
# to check-lint / check-format inside `just check` later. Re-stages
# post-autofix bytes.
lint-autofix-staged:
    #!/usr/bin/env bash
    set -uo pipefail
    staged=$(git diff --cached --name-only --diff-filter=AM | grep -E '\.py$' || true)
    if [[ -z "$staged" ]]; then
        exit 0
    fi
    echo "$staged" | xargs uv run ruff check --fix --exit-zero
    echo "$staged" | xargs uv run ruff format
    echo "$staged" | xargs git add

# ---------------------------------------------------------------
# Mutating targets (opt-in; not run in CI).
# ---------------------------------------------------------------

fmt:
    uv run ruff format .

lint-fix:
    uv run ruff check --fix .
