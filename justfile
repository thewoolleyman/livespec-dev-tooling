# justfile — livespec-dev-tooling dev-tooling task runner.
#
# Authority: livespec/SPECIFICATION/non-functional-requirements.md
#   §"Enforcement-suite invocation" — `just` is the canonical entry
#   point for every dev-tooling invocation. Lefthook and CI MUST
#   delegate to `just <target>`; direct tool invocations are banned
#   (enforced by the no-direct-tool-invocation check, migrated in
#   Phase G.4 of epic li-fgqgnk).
#
# Authority: livespec/SPECIFICATION/contracts.md
#   §"Pre-commit step ordering" — gates wired in lefthook.yml mirror
#   the spec-required ordering.
#   §"Shared code sync — livespec-dev-tooling" — this library is the
#   canonical home for the shared enforcement-suite checks; once G.4
#   completes, every `check-*` target listed in `check`'s aggregate
#   below resolves to `uv run python -m livespec_dev_tooling.checks.
#   <slug>`. At G.2 the aggregate carries only the tool-backed
#   subset (ruff lint/format, pyright types, pytest+cov) since no
#   structural checks have been migrated yet.

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

# ---------------------------------------------------------------
# Aggregate check — tool-backed targets only at Phase G.2.
# Add structural-check targets to the aggregate as Phase G.4
# migrates each `livespec_dev_tooling.checks.<slug>` module.
# ---------------------------------------------------------------

check:
    #!/usr/bin/env bash
    set -uo pipefail
    targets=(
        check-lint
        check-format
        check-coverage
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
# Tool-backed checks.
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

# Universal cross-boundary invariant: every livespec-governed primary
# checkout MUST have `core.bare = true` set in `.git/config`.
# Ported from livespec/.claude-plugin/scripts/livespec/doctor/static/
# primary_checkout_bare_flag_set.py — generalized for project-agnostic
# invocation. NOT wired into the `check` aggregate above: dev-tooling's
# own primary is currently non-bare, so wiring would self-fail; self-
# host migration is a downstream phase. CI matrix runs this target
# with a `git config core.bare true` step so the matrix entry passes.
check-primary-checkout-bare-flag-set:
    uv run python -m livespec_dev_tooling.checks.primary_checkout_bare_flag_set

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
# Add doc-only-relevant repo-metadata checks (claude-md-coverage,
# heading-coverage, no-direct-tool-invocation, check-tools) as Phase
# G.4 migrates the corresponding scripts.
check-pre-commit-doc-only:
    #!/usr/bin/env bash
    set -uo pipefail
    echo ":: doc-only subset (no repo-metadata checks wired yet — populate as scripts migrate in Phase G.4)"
    exit 0

# Skip the Python-code check subset when the pushed commits contain
# zero `.py` changes; those checks are deterministic functions of
# the source tree and would pass-or-fail identically against the
# merge-base. Falls back to `origin/master` when no upstream branch
# is configured locally.
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
# Commit-message gates. Invoked by lefthook commit-msg stage; the
# commit-message file path arrives as argv[1] via lefthook's {1}.
# At Phase G.2 these are stubs; Phase G.4 migrates the real scripts.
# ---------------------------------------------------------------

# v034 D3 hard gate: trailer-based Red→Green replay verification.
# Real implementation lands when Phase G.4 migrates
# livespec/dev-tooling/checks/red_green_replay.py.
check-red-green-replay msg_path:
    #!/usr/bin/env bash
    echo ":: check-red-green-replay stub ({{msg_path}}) — real implementation migrates in Phase G.4"
    exit 0

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

# Commit-pair gate: every commit touching source files also touches
# tests. Real implementation lands when Phase G.4 migrates
# livespec/dev-tooling/checks/commit_pairs_source_and_test.py.
check-commit-pairs-source-and-test:
    #!/usr/bin/env bash
    echo ":: check-commit-pairs-source-and-test stub — real implementation migrates in Phase G.4"
    exit 0

# ---------------------------------------------------------------
# Mutating targets (opt-in; not run in CI).
# ---------------------------------------------------------------

fmt:
    uv run ruff format .

lint-fix:
    uv run ruff check --fix .
