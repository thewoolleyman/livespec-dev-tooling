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

# `skip` — space-separated list of `check:` aggregate targets to omit
# from a single run (epic li-cvaudit, cvredmd). Default empty: the full
# aggregate runs. The Red-mode pre-commit overrides it on the command
# line — `just skip="check-coverage check-per-file-coverage" check` — so
# the coverage gates are not run at the Red commit (coverage is verified
# at the Green amend). This is a self-contained just variable; it replaces
# the prior ambient `LIVESPEC_PRECOMMIT_RED_MODE` env var with no env var
# and no spec change.
skip := ""

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
    just ensure-plugins

# Idempotent: `claude plugin marketplace add` / `install` / `update` all exit 0
# when the target is already present / already at latest. The `update` calls
# after each `install` are required because `install` is a no-op when any
# version is already present locally — without `update`, a bumped upstream
# release never reaches a previously-bootstrapped working copy. Installs the
# livespec plugin plus the ACTIVE impl plugin (livespec-impl-beads), mirroring
# the canonical recipe in livespec-impl-beads/justfile.
ensure-plugins:
    claude plugin marketplace add thewoolleyman/livespec
    claude plugin marketplace add thewoolleyman/livespec-impl-beads
    claude plugin install livespec@livespec
    claude plugin install livespec-impl-beads@livespec-impl-beads
    claude plugin update livespec@livespec
    claude plugin update livespec-impl-beads@livespec-impl-beads

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
    # `skip` is a just VARIABLE (declared at the top of this justfile,
    # default empty): a space-separated list of target names to omit from
    # this run (epic li-cvaudit, cvredmd). The Red-mode pre-commit invokes
    # `just skip="check-coverage check-per-file-coverage" check` so coverage
    # is not gated at the Red commit (it is verified at the Green amend) —
    # a self-contained just variable that replaces the prior ambient
    # `LIVESPEC_PRECOMMIT_RED_MODE` env var. The recipe header stays the
    # bare `check:` the wiring-completeness checks parse for. Pre-push and
    # CI invoke `just check` with no `skip`, so the full aggregate stays
    # the safety net.
    read -ra skip_targets <<< "{{skip}}"
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
        check-no-direct-destructive-cli
        check-no-direct-tool-invocation
        check-no-except-outside-io
        check-no-inheritance
        check-no-lloc-soft-warnings
        check-no-raise-outside-io
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
        check-tool-backed-check-completeness
        check-vendor-manifest
        check-wrapper-shape
        # ---- Repo-private block (extends after the canonical block) ----
        # Per the wiring-completeness invariant, repo-private extras MAY
        # follow the canonical block in any order. These are the four
        # tool-backed checks (ruff lint, ruff format, pyright types,
        # aggregate coverage) — helper recipes, NOT canonical slugs (not
        # under livespec_dev_tooling/checks/), so check-aggregate-
        # completeness does not enforce them. They are wired here as
        # LITERAL members so the local `just check` aggregate gives full
        # lint / format / types / coverage feedback and matches the CI
        # check-python matrix; the check-tool-backed-check-completeness
        # meta-check (canonical block above) enforces that both-surfaces
        # wiring (epic li-pyright-gate, work-item li-pyright-gate-wi3,
        # LITERAL-membership design). check-coverage gates the aggregate
        # `fail_under = 100` off the SINGLE pytest run that the canonical
        # check-per-file-coverage already performed (it reads the existing
        # `.coverage`), so wiring it here adds NO duplicate suite run.
        check-lint
        check-format
        check-types
        check-coverage
    )
    failed=()
    ran=0
    for t in "${targets[@]}"; do
        skip_this=0
        for s in "${skip_targets[@]:-}"; do
            if [[ "$t" == "$s" ]]; then
                skip_this=1
                break
            fi
        done
        if [[ "$skip_this" -eq 1 ]]; then
            printf '\n::: just %s (skipped)\n' "$t"
            continue
        fi
        ran=$((ran + 1))
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
    printf '\nAll %d targets passed.\n' "$ran"

# ---------------------------------------------------------------
# Tool-backed checks. NOT canonical-aggregate slugs (not in
# canonical_checks.py's discovery set — they live as helper recipes,
# not under livespec_dev_tooling/checks/), so check-aggregate-
# completeness does not enforce them. They ARE literal members of the
# `check:` aggregate's `targets=(...)` array (repo-private block) AND
# of the CI check-python matrix; the check-tool-backed-check-
# completeness meta-check enforces that both-surfaces wiring (epic
# li-pyright-gate, work-item li-pyright-gate-wi3, LITERAL-membership
# design). check-lint / check-format are cheap ruff passes; the
# coverage gate is consolidated onto the SINGLE pytest run that
# check-per-file-coverage already performs (see check-coverage below).
# ---------------------------------------------------------------

check-lint:
    uv run ruff check .

check-format:
    uv run ruff format --check .

check-types:
    uv run pyright

# Aggregate (total) coverage gate at `fail_under = 100` (pyproject.toml
# [tool.coverage.report]). To avoid a DUPLICATE full pytest run when
# invoked inside the `just check` aggregate, this recipe gates off the
# EXISTING `.coverage` data file when present (the canonical
# check-per-file-coverage slug runs `pytest --cov` upfront and runs
# alphabetically before this repo-private extra, so `.coverage` is
# already produced by the time this runs locally). When `.coverage` is
# ABSENT — the CI check-python matrix runs check-coverage as a
# standalone job in its own runner with no prior pytest — the recipe
# runs the suite itself so the aggregate gate still fires there. Either
# way the result is the `fail_under = 100` aggregate assertion with NO
# duplicate suite run in `just check`.
check-coverage:
    #!/usr/bin/env bash
    set -uo pipefail
    if [[ -f .coverage ]]; then
        echo ":: check-coverage: reading existing .coverage (produced by check-per-file-coverage); no duplicate suite run"
        uv run coverage report --fail-under=100
    else
        echo ":: check-coverage: no .coverage data file (CI standalone job); running the suite"
        uv run pytest -n auto --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
    fi

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

# Path-scoped fast-feedback variant of check-coverage. With explicit
# `--paths <impl_path> [<impl_path>...]` (repo-root-relative) it scopes
# the per-file 100% gate to those paths. With NO args (the canonical
# aggregate / `just check` invocation) the check DERIVES the changed
# impl-`.py` set from `git diff --name-only origin/master...HEAD` and
# gates those — no longer a no-op (epic li-cvaudit, cvnoarg). The
# interactive developer use case still passes `--paths` explicitly:
# `just check-check-coverage-incremental --paths livespec_dev_tooling/checks/foo.py`.
check-check-coverage-incremental *args:
    uv run python -m livespec_dev_tooling.checks.check_coverage_incremental {{args}}

# Always invoked plainly; the module self-manages its RUN/SKIP lever
# (epic li-cvaudit, cvtodo). `LIVESPEC_RUN_MUTATION` unset → the check
# logs "skipped" and exits 0; set to a non-empty value (CI sets it to
# `true`) → the mutmut suite runs. No external gate, no silent skip.
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

# Destructive-default CLI wrapping gate (livespec/SPECIFICATION/
# non-functional-requirements.md §"Destructive-default CLI wrapping"):
# greps the agent-facing trees (dev-tooling/, .claude-plugin/,
# .claude/plugins/) for direct invocations of known-destructive-default
# CLIs (bd init, git push --force/-f, git reset --hard, gh repo delete)
# outside the explicit `[tool.livespec_dev_tooling].
# destructive_cli_allowlist` path-prefix allowlist.
check-no-direct-destructive-cli:
    uv run python -m livespec_dev_tooling.checks.no_direct_destructive_cli

check-no-direct-tool-invocation:
    uv run python -m livespec_dev_tooling.checks.no_direct_tool_invocation

check-no-except-outside-io:
    uv run python -m livespec_dev_tooling.checks.no_except_outside_io

check-no-inheritance:
    uv run python -m livespec_dev_tooling.checks.no_inheritance

# Always invoked plainly; the module self-manages its severity lever
# (epic li-cvaudit, cvtodo). The 201-250 LLOC soft-band scan ALWAYS
# runs; `LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST` unset → soft-band
# offenders warn + exit 0; set (CI sets it to `true`) → they fail.
check-no-lloc-soft-warnings:
    uv run python -m livespec_dev_tooling.checks.no_lloc_soft_warnings

check-no-raise-outside-io:
    uv run python -m livespec_dev_tooling.checks.no_raise_outside_io

# Always invoked plainly; the module self-manages its severity lever
# (epic li-cvaudit, cvtodo). The heading-coverage.json TODO scan ALWAYS
# runs; `LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` unset → TODO
# offenders warn + exit 0 (authoring placeholders surface without
# blocking per-commit `just check`); set (CI sets it to `true`) → they
# fail. Replaces the prior LIVESPEC_RELEASE_GATE skip carve-out, which
# silently skipped the scan entirely when the gate was unset.
check-no-todo-registry:
    uv run python -m livespec_dev_tooling.checks.no_todo_registry

check-no-write-direct:
    uv run python -m livespec_dev_tooling.checks.no_write_direct

check-pbt-coverage-pure-modules:
    uv run python -m livespec_dev_tooling.checks.pbt_coverage_pure_modules

# Per-file 100% line+branch coverage gate. Reads `.coverage`; we run
# pytest --cov upfront in the recipe so the data file exists when the
# canonical aggregate invokes the slug as a self-contained check.
# In Red-mode pre-commit this target is omitted by `check-pre-commit`
# via the `check skip=...` argument (coverage is verified at the Green
# amend), so no ambient env-var read is needed here.
check-per-file-coverage:
    #!/usr/bin/env bash
    set -uo pipefail
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

# Trailer-based Red→Green replay verification (hard gate). Invoked by
# lefthook commit-msg stage with the commit-message file path as argv[1]
# (the per-commit verifier: content-triggered — a failing staged test
# authors a Red under ANY prefix; product impl .py with Red trailers at
# HEAD takes the Green amend leg; product impl .py without a Red leg is
# green-verified by a full passing suite, recording TDD-Suite-Green-*
# trailers; the prefix never rejects product code, its only semantic is
# the feat:/fix: test-passed-at-red guard). The canonical aggregate /
# `just check` / pre-push / CI invokes this with NO msg_path; the module
# then validates the COMMIT RANGE origin/master..HEAD — every non-merge
# commit touching product impl .py must carry EITHER the
# TDD-Red-*/TDD-Green-* pair shape OR the TDD-Suite-Green-* shape,
# regardless of prefix (work-item livespec-dev-tooling-eld + the
# 2026-06-11 green-verified correction; the load-bearing branch-level
# gate).
check-red-green-replay *args:
    uv run python -m livespec_dev_tooling.checks.red_green_replay {{args}}

check-rop-pipeline-shape:
    uv run python -m livespec_dev_tooling.checks.rop_pipeline_shape

check-skill-invocation-paths:
    uv run python -m livespec_dev_tooling.checks.skill_invocation_paths

check-supervisor-discipline:
    uv run python -m livespec_dev_tooling.checks.supervisor_discipline

check-tests-mirror-pairing:
    uv run python -m livespec_dev_tooling.checks.tests_mirror_pairing

# Tool-backed-check completeness meta-check (epic li-pyright-gate,
# work-item li-pyright-gate-wi3). Asserts each tool-backed check
# (check-lint / check-format / check-types / check-coverage) is a
# LITERAL member of BOTH this justfile's `check:` targets=(...) array
# AND the CI check-python matrix. Self-passes because the targets
# array + CI matrix wire all four literally.
check-tool-backed-check-completeness:
    uv run python -m livespec_dev_tooling.checks.tool_backed_check_completeness

check-vendor-manifest:
    uv run python -m livespec_dev_tooling.checks.vendor_manifest

check-wrapper-shape:
    uv run python -m livespec_dev_tooling.checks.wrapper_shape

# ---------------------------------------------------------------
# Pre-commit aggregate — Red-mode-aware. Classifies the staged
# tree shape; in Red mode it passes `skip="check-coverage
# check-per-file-coverage"` to `just check` so the coverage gates
# are omitted (the commit-msg replay hook is the verifier; coverage
# is checked at the Green amend). This is a self-contained recipe
# argument — there is NO ambient env var (epic li-cvaudit, cvredmd).
# Pre-push and CI keep invoking `just check` directly.
# ---------------------------------------------------------------

check-pre-commit:
    #!/usr/bin/env bash
    set -uo pipefail
    # Empty-commit guard (work-item livespec-dev-tooling-74q): an empty
    # commit cannot change repo state, so repo-state gates yield zero
    # information about it. `git commit --allow-empty` (e.g. machine
    # checkpoint commits) passes immediately. Deliberately unfiltered
    # (no --diff-filter): a deletion-only commit is NOT empty and still
    # flows through the classification below.
    if [[ -z "$(git diff --cached --name-only)" ]]; then
        echo ":: empty commit detected (nothing staged at all): repo-state gates have nothing to gate; exit 0"
        exit 0
    fi
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
        echo ":: skipping coverage gates (commit-msg replay hook is the verifier; coverage runs at Green amend)"
        just skip="check-coverage check-per-file-coverage" check
        exit $?
    fi
    # Green-amend shape needs no special-casing: the no-arg
    # `check-red-green-replay` aggregate variant validates the commit
    # RANGE origin/master..HEAD (work-item livespec-dev-tooling-eld),
    # and during a Green amend HEAD is the in-progress Red commit —
    # which touches tests-only .py and therefore carries no trailer
    # obligation. The full aggregate runs as-is.
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
# to the check-lint / check-format targets that the `just check`
# aggregate's `targets=(...)` array wires as literal members
# (repo-private block; epic li-pyright-gate, work-item
# li-pyright-gate-wi3). Re-stages post-autofix bytes.
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

# Mechanize the Red-commit-then-Green-amend TDD ritual for a product
# `.py` change: stage the TEST alone and commit (Red), then stage the
# IMPL file(s) and amend (Green), yielding ONE commit carrying the test,
# the impl, and both TDD-Red-*/TDD-Green-* trailer sets (per the
# red-green-replay commit-refuse hook). Replaces the error-prone hand-
# orchestration (`git add <test>` → commit → `git add <impl>` → amend).
#
# Usage (--impl is repeatable; --subject must be feat:/fix:):
#   just tdd-commit --test tests/livespec_dev_tooling/test_foo.py \
#       --impl livespec_dev_tooling/foo.py --subject "feat: add foo"
#
# Git runs through `mise exec -- git` by default so lefthook's commit-msg
# shim fires and the trailers get written; pass `--no-mise` for a
# hook-less repo. Opt-in mutating target — NOT part of the `check:`
# aggregate.
tdd-commit *args:
    uv run python -m livespec_dev_tooling.tdd_commit {{args}}
