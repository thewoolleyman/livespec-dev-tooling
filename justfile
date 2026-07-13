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
# aggregate runs. This is a self-contained just variable; it replaces
# the prior ambient `LIVESPEC_PRECOMMIT_RED_MODE` env var with no env var
# and no spec change. Pre-push and CI invoke `just check` with no `skip`,
# so the full aggregate stays the safety net.
skip := ""

# `red_staged` — the single staged test path at a Red commit (empty
# otherwise). When non-empty, `check:` derives the Red-mode skip set
# from the staged-path CLASS via `red_leg_scope` and UNIONs it into
# `skip`: always the coverage gates (verified at the Green amend) plus
# any orthogonal legs a staged unit test cannot affect (livespec's
# e2e-mock / prompts / doctor-static — dev-tooling has none, so it is
# the coverage floor here; the win lands cross-repo via the pin bump).
# Work-item livespec-dev-tooling-7us.6; research item #4. The `check:`
# `targets=(...)` array is the SINGLE source of truth — the scope
# module receives it and the staged path, computes the skip set, and
# FAILS FAST (the caller then runs the full aggregate) rather than ever
# emitting an empty Red selection.
red_staged := ""

# Default to listing targets when no recipe is invoked.
default:
    @just --list

# ---------------------------------------------------------------
# First-time setup.
# ---------------------------------------------------------------

# First-touch setup — a THIN delegator to this package's OWN LOCAL first-touch
# reconcile verb (`livespec_dev_tooling.fleet.local_reconcile`), the generalized
# successor to this recipe's former inline steps (livespec-zs22.8 M5). This repo
# IS livespec_dev_tooling, so `uv run python -m ...` runs the local package
# directly (no external pin). The verb walks the LOCAL obligation partition
# (`contract.LOCAL_OBLIGATION_ROWS`): mise trust/install, uv sync, the structural
# commit-refuse hooks (subsuming `lefthook install` — the canonical hook
# overwrites the lefthook stubs and delegates to `lefthook run`), the advisory
# `refs/notes/*` refspec, the worktree-root mise-trust entry, the beads
# tenant-dir hardening, the beads-runtime detect-and-guide probes, and
# project-scoped Claude/Codex plugin registration via THIS repo's own
# `ensure-plugins` / `ensure-codex-plugins` recipes below (a member lacking
# either recipe SKIPs that row). The verb resolves the target checkout
# worktree-safely via `git rev-parse --git-common-dir`. Dogfoods the verb against
# its own package — the most direct exercise of the local-reconcile contract.
bootstrap:
    uv run python -m livespec_dev_tooling.fleet.local_reconcile

# Install (or idempotently re-install) the canonical livespec commit-refuse
# hook at the primary checkout's shared `.git/hooks/{pre-commit,pre-push,
# commit-msg}`. The installer module is the single canonical-body carrier; it
# resolves the target via `git rev-parse --git-common-dir` so the hooks land in
# the primary's shared hooks directory even when invoked from a secondary
# worktree. Armed on install (structural primary detection, no
# `livespec.primaryPath`); the lone opt-out is `git config
# livespec.sandboxExempt true`. Invoked by `bootstrap` and re-runnable
# standalone to repair a fresh clone's hooks.
install-commit-refuse-hooks:
    uv run python -m livespec_dev_tooling.install_commit_refuse_hooks

# Install (or idempotently re-install) the canonical neutral no-shadow-ledger
# Stop-hook body at the current checkout's configured `neutral_hook_body_path`
# role key (a `[tool.livespec_dev_tooling]` key in `pyproject.toml`). The
# installer module is the single canonical-body carrier, mirroring
# `install-commit-refuse-hooks`; the body is the Stop-hook BOTH livespec
# Driver plugins ship (livespec-driver-claude, livespec-driver-codex), so
# this keeps each Driver's copy byte-identical to the single dev-tooling
# source. No-ops when the role key is absent (this consumer does not carry
# the neutral hook body). The
# `check-no-shadow-ledger-body-identical` verifier guards the installed
# bytes against drift.
install-no-shadow-ledger:
    uv run python -m livespec_dev_tooling.install_no_shadow_ledger

# Install (or idempotently re-install) the canonical worktree-discipline pack
# (`worktree-lib.sh` + `branch-protection.sh`) into the current checkout's
# `dev-tooling/` directory, each executable. The installer module is the single
# canonical-body carrier (its `CANONICAL_WORKTREE_LIB_BODY` /
# `CANONICAL_BRANCH_PROTECTION_BODY` constants), retiring the copier-template
# COPIES. The pack scripts are TRACKED files, so the installer targets the
# work-tree root (`git rev-parse --show-toplevel`) and the result is committed
# through the normal worktree → PR flow. The
# `check-primary-checkout-commit-refuse-hook-installed` verifier guards the
# installed bytes against drift.
install-worktree-pack:
    uv run python -m livespec_dev_tooling.install_worktree_pack

# The standard shared derive-from-settings wrapper: it reads the committed
# .claude/settings.json (extraKnownMarketplaces incl. ref, enabledPlugins)
# at runtime and issues the marketplace add / install / update commands for
# exactly what it finds. One source of truth — recipe-content drift is
# structurally impossible. The SessionStart hook in `.claude/settings.json`
# runs this recipe so each new session's project-scope plugins are current.
ensure-plugins:
    mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins

# Idempotent host-wide Codex plugin provisioning. Codex does not support
# project-scoped plugin enablement, so these registrations intentionally land in
# the user's default CODEX_HOME and are visible to every repo on the host. Codex
# is an optional dogfooding runtime; bootstrap skips this target when the CLI is
# absent but fails on real install errors when Codex is present.
ensure-codex-plugins:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v codex >/dev/null 2>&1; then
        echo "codex CLI not found; skipping host-wide Codex plugin install." >&2
        exit 0
    fi
    codex plugin marketplace add thewoolleyman/livespec --ref release
    codex plugin marketplace add thewoolleyman/livespec-driver-codex --ref release
    codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro --ref release
    codex plugin marketplace upgrade livespec
    codex plugin marketplace upgrade livespec-driver-codex
    codex plugin marketplace upgrade livespec-orchestrator-beads-fabro
    codex plugin add livespec@livespec
    codex plugin add livespec@livespec-driver-codex
    codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro

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
    # `just red_staged="<test>" check`, which derives the Red-mode skip
    # set from the staged-path class (red_leg_scope) and unions it into
    # `skip` so coverage (and any orthogonal legs) are not gated at the
    # Red commit (they are verified at the Green amend) — a self-contained
    # just variable that replaces the prior ambient
    # `LIVESPEC_PRECOMMIT_RED_MODE` env var. The recipe header stays the
    # bare `check:` the wiring-completeness checks parse for. Pre-push and
    # CI invoke `just check` with no `skip`, so the full aggregate stays
    # the safety net.
    # Sync the environment ONCE per aggregate pass, then run every
    # target with UV_NO_SYNC=1 so the ~44 per-target `uv run`
    # invocations skip their redundant per-invocation re-sync
    # (work-item livespec-dev-tooling-ool). The single up-front sync
    # keeps the freshness guarantee — a stale lockfile/venv still
    # fails here, loudly, before any target runs. This also caps the
    # cost of a corrupted-venv re-sync loop (e.g. an orphaned
    # dist-info missing its RECORD file, which a sync can never
    # uninstall and therefore retries on EVERY invocation) at one
    # sync attempt per pass instead of one per target, and shrinks
    # the concurrent-sync race window that produces that corruption
    # in the first place. Standalone `just check-<x>` invocations
    # keep uv's default sync-on-run behavior; CI's per-target matrix
    # jobs each sync their own fresh runner and are unaffected.
    if ! uv sync --all-groups; then
        echo "ERROR: up-front 'uv sync --all-groups' failed; aborting the check aggregate" >&2
        exit 1
    fi
    export UV_NO_SYNC=1
    targets=(
        check-agents-ai-references-resolve
        check-aggregate-completeness
        check-all-declared
        check-assert-never-exhaustiveness
        check-branch-protection-alignment
        check-canonical-recipe-fidelity
        check-check-coverage-incremental
        check-check-mutation
        check-check-tools
        check-ci-matrix-completeness
        check-claude-md-coverage
        check-comment-line-anchors
        check-commit-pairs-source-and-test
        check-file-lloc
        check-fleet-marketplace-relative-sources
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
        check-no-fmt-directives
        check-no-inheritance
        check-no-lloc-soft-warnings
        check-no-raise-outside-io
        check-no-shadow-ledger-body-identical
        check-no-todo-registry
        check-no-write-direct
        check-partition-completeness
        check-pbt-coverage-pure-modules
        check-per-file-coverage
        check-plugin-resolution
        check-primary-checkout-commit-refuse-hook-installed
        check-private-calls
        check-public-api-result-typed
        check-red-green-replay
        check-rop-pipeline-shape
        check-skill-invocation-paths
        check-supervisor-discipline
        check-tests-mirror-pairing
        check-tests-no-subprocess-spawn
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
        # `fail_under = 100` by running its OWN clean `pytest --cov`
        # (COVERAGE_FILE unset), measuring IDENTICALLY to the CI standalone
        # check-coverage job — a deliberate duplicate suite run (see the
        # recipe header below) chosen so the local gate can never
        # green-light coverage that CI will fail.
        check-lint
        check-format
        check-types
        check-coverage
        # Central fleet-membership conformance check (livespec v108
        # §"Fleet membership contract") — repo-private extra, NOT a
        # canonical slug (it lives under livespec_dev_tooling/fleet/,
        # not checks/: it asserts the WHOLE fleet from one vantage
        # point, so siblings do not each wire it). Always wired here;
        # the module self-manages its RUN/SKIP lever (see the recipe).
        check-fleet-conformance
        # Fabro sandbox image pin-lockstep gate — repo-private extra,
        # NOT a canonical slug (the module lives at
        # livespec_dev_tooling/fabro_image_pin_lockstep.py, not under
        # checks/: this repo OWNS the fleet Fabro sandbox image at
        # docker/fabro-sandbox/Dockerfile, so siblings have nothing
        # to wire). See the recipe comment below.
        check-fabro-image-pin-lockstep
    )
    # Red-mode scope reduction (work-item livespec-dev-tooling-7us.6):
    # when `red_staged` names the single staged test path at a Red
    # commit, derive the additional skip set from the staged-path CLASS
    # against the SAME `targets` array (its single source of truth) and
    # union it into `skip`. The module FAILS FAST (exit 1) rather than
    # ever emitting an empty Red selection; on failure we abort here so
    # the Red gate is never silently empty (it surfaces loudly and the
    # author re-runs the full aggregate). Pre-push / CI pass no
    # `red_staged`, so the full aggregate is unaffected.
    effective_skip="{{skip}}"
    if [[ -n "{{red_staged}}" ]]; then
        red_skip=$(uv run python -m livespec_dev_tooling.red_leg_scope \
            --staged {{red_staged}} --targets "${targets[@]}") || {
            echo "ERROR: red_leg_scope fail-fast; the Red selection would be empty — run the full aggregate instead" >&2
            exit 1
        }
        effective_skip="{{skip}} ${red_skip}"
    fi
    uv run python -m livespec_dev_tooling.parallel_check_dispatcher --skip "${effective_skip}" -- "${targets[@]}" || exit 1
    # The advisory green token records a FULL green pass only. A partial
    # run (explicit `skip` OR a Red-mode `red_staged` scope reduction)
    # must NOT write it, or pre-push would skip the full aggregate on a
    # tree that never had one.
    if [[ -z "{{skip}}" && -z "{{red_staged}}" ]]; then uv run python -m livespec_dev_tooling.green_token write || true; fi

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

# `check-static` — fastest-first fail-fast helper for fast agent/dev
# feedback (work-item livespec-dev-tooling-7us.8). Runs ONLY the cheap
# static checks — `ruff format --check .`, `ruff check .`, `pyright`
# (i.e. check-format, check-lint, check-types) — as a fail-fast
# sequence: it STOPS at the first failing check and exits non-zero, so
# a sub-2s ruff/pyright failure surfaces immediately instead of after
# `just check`'s slow pytest+coverage tail. This is a developer/agent
# convenience like the helper recipes above; it is deliberately NOT a
# member of the `check:` aggregate `targets=(...)` array, NOT a
# canonical slug (no livespec_dev_tooling/checks/ module), and NOT in
# the CI matrix. The authoritative full gate remains `just check`
# (still run at pre-push and in CI) — `check-static` is a fast
# pre-flight, never a replacement for it.
check-static:
    #!/usr/bin/env bash
    set -euo pipefail
    uv run ruff format --check .
    uv run ruff check .
    uv run pyright

# `changed-files` — print the changed `.py` set this branch touches,
# repo-root-relative, one path per line, sorted + de-duplicated
# (work-item livespec-dev-tooling-7us.9). The set is the UNION of two
# git views, so an agent gets the live working set whether or not it has
# committed yet:
#   - `git diff --name-only origin/master...HEAD` — every `.py` this
#     branch's commits changed vs the merge-base with origin/master;
#   - `git diff --cached --name-only --diff-filter=AM` — added/modified
#     `.py` currently staged but not yet committed.
# This is the exact set `check-changed` consumes for its scoped gate.
# Helper recipe (like `check-static`): NOT a member of the `check:`
# aggregate `targets=(...)` array, NOT a canonical slug, NOT in the CI
# matrix.
changed-files:
    #!/usr/bin/env bash
    set -uo pipefail
    # `grep` exits 1 on zero matches; an empty changed set is normal (a
    # clean branch), so swallow that into exit 0 via `|| true` — the
    # consuming `check-changed` treats empty as "nothing to gate".
    { git diff --name-only origin/master...HEAD;
      git diff --cached --name-only --diff-filter=AM; } \
        | { grep -E '\.py$' || true; } | sort -u

# `check-changed` — modified-files INNER-LOOP gate for fast scoped
# feedback during iteration (work-item livespec-dev-tooling-7us.9). Feeds
# the `changed-files` set into `check-check-coverage-incremental --paths
# <set>`, which already (a) resolves each changed impl `.py` to its
# mirror-paired test and runs that pytest SUBSET, and (b) applies the
# path-scoped per-file coverage gate — i.e. it composes the existing
# scoping plumbing rather than re-deriving it. An empty changed set is a
# no-op (exit 0): nothing changed, nothing to gate.
#
# SCOPE — INNER-LOOP SPEEDUP ONLY, NOT a replacement for the final gate.
# It runs only the test subset + path-scopable checks for the files this
# branch touched, so an agent gets sub-suite feedback while iterating. The
# AUTHORITATIVE gate remains `just check`, which runs the FULL suite + the
# full AST scans + the aggregate 100% coverage gate at pre-push and in CI.
# Like `check-static`, this is a developer/agent convenience: NOT a member
# of the `check:` aggregate `targets=(...)` array, NOT a canonical slug,
# and NOT in the CI matrix.
check-changed:
    #!/usr/bin/env bash
    set -uo pipefail
    mapfile -t changed < <(just changed-files)
    if [[ "${#changed[@]}" -eq 0 ]]; then
        echo ":: check-changed: no changed .py vs origin/master (and none staged); nothing to gate"
        echo ":: the authoritative full gate remains 'just check' (run at pre-push + CI)"
        exit 0
    fi
    echo ":: check-changed: scoping the test subset + per-file coverage gate to ${#changed[@]} changed .py:"
    printf '   %s\n' "${changed[@]}"
    echo ":: INNER-LOOP ONLY — 'just check' runs the FULL suite/AST scans at pre-push + CI"
    just check-check-coverage-incremental --paths "${changed[@]}"

# Aggregate (total) coverage gate at `fail_under = 100` (pyproject.toml
# [tool.coverage.report]). This recipe ALWAYS runs its own clean
# `pytest --cov` with COVERAGE_FILE UNSET, measuring coverage IDENTICALLY
# to CI's standalone check-coverage matrix job — so the local / pre-PR
# gate is a faithful predictor of CI by construction.
#
# WHY NOT reuse check-per-file-coverage's data (the prior optimization):
# the parallel check dispatcher runs check-per-file-coverage's `pytest
# --cov` with COVERAGE_FILE EXPORTED to an isolated namespace dir (the
# coverage-data isolation of work-item livespec-dev-tooling-cmn). For a
# module whose OWN coverage is self-referential on coverage's machinery
# — e.g. code that branches on `COVERAGE_FILE == COV_CORE_DATAFILE` — an
# exported COVERAGE_FILE makes that branch execute during the suite (the
# two paths are equal), so the line reads as COVERED. CI runs
# check-coverage standalone with COVERAGE_FILE UNSET, where that branch
# does NOT execute, so the same line reads as UNCOVERED. Reusing the
# exported-namespace data therefore measured LENIENTLY and let `just
# check` green-light lines CI then failed (the pre-PR gate that Fabro's
# janitor runs passed at a false 100% while the PR's CI check-coverage
# failed at 99.99%). Running the clean suite here closes that gap.
#
# TRADE-OFF: this re-introduces ONE duplicate full pytest run in the
# `just check` aggregate (check-per-file-coverage runs the suite for its
# per-file gate; this gate runs it again, clean, for the total). Gate
# correctness over speed; the optimization is reversible if a future
# design measures both gates identically without the divergence.
#
# NOTE on the dispatcher: check-coverage remains check-per-file-coverage's
# namespace-shared CONSUMER in parallel_check_dispatcher.py, so it still
# runs only after that producer completes. It no longer READS the
# producer's data file, so that ordering is now a benign serialization
# rather than a data dependency — a dispatcher-side simplification is a
# possible follow-up, kept out of this justfile-scoped change.
# Central fleet-membership conformance check (livespec v108 §"Fleet
# membership contract"): fetches .livespec-fleet-manifest.jsonc from livespec
# master, asserts every member's per-class obligations from the
# central vantage point, and runs the discovery sweep. Always invoked
# plainly; the module self-manages its RUN/SKIP lever (the
# check_mutation precedent for network-dependent checks):
# `LIVESPEC_RUN_FLEET_CONFORMANCE` unset → the check logs "skipped"
# and exits 0 (a local per-commit aggregate run does not fan ~35
# GitHub API reads); set to a non-empty value (the CI job, the
# scheduled fleet-conformance.yml workflow, and the release fan-out
# preflight in reusable-release-dispatch.yml set it) → the full
# central sweep runs. No external gate, no silent skip. The reconcile
# twin is operator-invoked, NOT CI:
#   with-livespec-env.sh -- env PATH="$HOME/.local/bin:$PATH" uv run python -m \
#       livespec_dev_tooling.fleet.wire_fleet_member --repo <member>
check-fleet-conformance:
    uv run python -m livespec_dev_tooling.fleet.fleet_conformance

# Fabro sandbox image pin-lockstep gate — repo-private extra (this
# repo owns the fleet Fabro sandbox image; the module deliberately
# lives OUTSIDE livespec_dev_tooling/checks/ so it stays out of the
# canonical fleet-universal slug set). Fails when any tool version
# baked into docker/fabro-sandbox/Dockerfile (its greppable ARG-form
# pins) drifts from this repo's own pin sources: `.mise.toml`
# `[tools]` for uv / just / lefthook, `.python-version` for the
# interpreter. The uv.lock cache pre-warm needs no check: the image
# build COPYs this repo's own pyproject.toml + uv.lock from the build
# context, so it cannot reference a stale lockfile. Wired in the
# `check:` aggregate above AND the CI check-metadata matrix.
check-fabro-image-pin-lockstep:
    uv run python -m livespec_dev_tooling.fabro_image_pin_lockstep

check-coverage:
    #!/usr/bin/env bash
    set -uo pipefail
    # Always measure the `fail_under = 100` aggregate gate the SAME way CI's
    # standalone check-coverage job does: a clean `pytest --cov` with
    # COVERAGE_FILE UNSET (`env -u`). In the `just check` aggregate the
    # parallel dispatcher exports COVERAGE_FILE for this target's namespace;
    # `env -u COVERAGE_FILE` strips it so the suite runs exactly as the CI
    # standalone runner does. See the header comment above for why reusing
    # check-per-file-coverage's exported-namespace data measured LENIENTLY
    # (it green-lit self-referential lines that CI's clean run then failed).
    echo ":: check-coverage: clean standalone suite (COVERAGE_FILE unset) — strict, matches CI"
    env -u COVERAGE_FILE uv run pytest -n auto --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing

# ---------------------------------------------------------------
# Canonical aggregate recipes — one per canonical slug emitted by
# `python -m livespec_dev_tooling.canonical_checks --json`. Each
# resolves to `uv run python -m livespec_dev_tooling.checks.<slug>`
# with the snake_case slug.
# ---------------------------------------------------------------

check-agents-ai-references-resolve:
    uv run python -m livespec_dev_tooling.checks.agents_ai_references_resolve

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

# Anti-fork guard: verifies every canonical `check-<slug>:` recipe in
# this justfile invokes the pinned shared module
# `python -m livespec_dev_tooling.checks.<module>`. Closes the gap
# check-aggregate-completeness (targets-array membership only) and
# check-tool-backed-check-completeness (four tool slugs) leave open —
# neither inspects the recipe BODY, so a consumer could satisfy both
# while repointing a shared check at a local script / bash fork (the
# "B1" incident). Self-validating: this very recipe must invoke the
# shared module.
check-canonical-recipe-fidelity:
    uv run python -m livespec_dev_tooling.checks.canonical_recipe_fidelity

# Path-scoped fast-feedback variant of check-coverage. With explicit
# `--paths <impl_path> [<impl_path>...]` (repo-root-relative) it scopes
# the per-file 100% gate to those paths. With NO args (the canonical
# aggregate / `just check` invocation) the check DERIVES the changed
# impl-`.py` set from `git diff --name-only origin/master...HEAD` and
# gates those — no longer a no-op (epic li-cvaudit, cvnoarg). The
# interactive developer use case still passes `--paths` explicitly:
# `just check-check-coverage-incremental --paths livespec_dev_tooling/checks/foo.py`.
#
# Coverage-data isolation (work-item livespec-dev-tooling-cmn): the
# module sets its own isolated COVERAGE_FILE for the inner pytest, and
# the parallel check dispatcher additionally assigns this target its OWN
# coverage namespace dir + TMPDIR. With check-per-file-coverage's
# `coverage combine` now confined to ITS OWN namespace dir, this gate's
# data file can never be globbed-and-erased by a concurrent
# per-file-coverage run. The former hand-pinned serialization edge
# (check-check-coverage-incremental -> check-per-file-coverage, 7us.6)
# is RETIRED; this gate runs fully concurrently.
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

# CI-aggregate drift-guard (epic fleet-ci-aggregate-coverage, slice 1).
# Asserts, from this repo's OWN committed files, that CI runs (a) and
# gates (b) the whole canonical aggregate: the CI-covered canonical slug
# set is a superset of the justfile aggregate, and a `ci-green` job's
# `needs:` covers every check-bearing job. Warn-default (severity lever
# `LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST`), so the slug propagates and
# warns each not-yet-wired repo without reddening it.
check-ci-matrix-completeness:
    uv run python -m livespec_dev_tooling.checks.ci_matrix_completeness

check-claude-md-coverage:
    uv run python -m livespec_dev_tooling.checks.claude_md_coverage

check-comment-line-anchors:
    uv run python -m livespec_dev_tooling.checks.comment_line_anchors

check-commit-pairs-source-and-test:
    uv run python -m livespec_dev_tooling.checks.commit_pairs_source_and_test

check-file-lloc:
    uv run python -m livespec_dev_tooling.checks.file_lloc

# Fleet marketplace ref-pin guard: catalog plugin sources MUST stay
# checkout-relative (`./...`). Github-type or other non-relative
# sources silently ignore the registered marketplace ref pin and clone
# default HEAD instead.
check-fleet-marketplace-relative-sources:
    uv run python -m livespec_dev_tooling.checks.fleet_marketplace_relative_sources

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

check-no-fmt-directives:
    uv run python -m livespec_dev_tooling.checks.no_fmt_directives

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

# Byte-identity Verifier for the neutral no-shadow-ledger Stop-hook body
# BOTH livespec Driver plugins ship (livespec-driver-claude at
# `.claude-plugin/hooks/`, livespec-driver-codex at `livespec/hooks/`),
# mirroring the commit-refuse-hook precedent (Conformance-Pattern concern
# #1). OPT-IN via the `neutral_hook_body_path` role key: absent → no-op
# (this consumer does not carry the neutral hook body); present → the
# configured path MUST be byte-identical to the single packaged carrier
# constant `install_no_shadow_ledger.CANONICAL_NO_SHADOW_LEDGER_BODY`.
check-no-shadow-ledger-body-identical:
    uv run python -m livespec_dev_tooling.checks.no_shadow_ledger_body_identical

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

check-partition-completeness:
    uv run python -m livespec_dev_tooling.checks.partition_completeness

check-pbt-coverage-pure-modules:
    uv run python -m livespec_dev_tooling.checks.pbt_coverage_pure_modules

# Per-file 100% line+branch coverage gate. Runs pytest --cov upfront so
# the data file exists when per_file_coverage reads it.
#
# Coverage-data isolation (work-item livespec-dev-tooling-cmn): the
# parallel check dispatcher exports COVERAGE_FILE pointed at this
# target's isolated namespace dir. pytest-cov honors COVERAGE_FILE
# natively (parallel `.coverage.*` data files land beside it and
# `coverage combine` globs only THAT dir), and a COVERAGE_PROCESS_START
# child a test spawns inherits the same COVERAGE_FILE, so the subprocess
# case is isolated for free. per_file_coverage reads the same file via
# COVERAGE_FILE. A standalone run leaves COVERAGE_FILE unset and uses the
# repo-root `.coverage` default. This is the PRODUCER of the full-tree
# coverage namespace shared with check-coverage.
# In Red-mode pre-commit this target is omitted by `check-pre-commit`
# via the `check skip=...` argument (coverage is verified at the Green
# amend), so no ambient env-var read is needed here.
check-per-file-coverage:
    #!/usr/bin/env bash
    set -uo pipefail
    uv run pytest -n auto --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
    uv run python -m livespec_dev_tooling.checks.per_file_coverage

# Cross-harness plugin-resolution Verifier (Conformance-Pattern concern
# #2, per livespec/SPECIFICATION/non-functional-requirements.md
# §"Conformance Pattern"). Always-on layer: validate the repo's local
# `.livespec.jsonc` `harnesses` declaration (absent → skip; garbled →
# fail). Live layer (opt-in, env-gated by the same LIVESPEC_E2E_HARNESS
# dialect cli_e2e uses — `real` runs it, default `mock` does not): a
# fresh-session resolution smoke that invokes each supported harness's
# canonical command through the command surface and asserts it resolves
# and returns, rejecting a raw-CLI fallback as proof (the ob-4ts class);
# an unavailable binary SKIPs (work-item livespec-mjnv), an exempt harness
# PASSes by declaration.
check-plugin-resolution:
    uv run python -m livespec_dev_tooling.checks.plugin_resolution

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
# authors a Red under ANY prefix; product impl .py with Red trailers
# AND NO Green trailers at HEAD — a genuine amend-in-progress — takes
# the Green amend leg; any other product impl .py staging is
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

# Test-spawned-Python-subprocess guard (epic 7us, work-item
# livespec-dev-tooling-4i5). Flags `subprocess.run([sys.executable, ...])`
# (and python/python3-literal) spawns under tests/ — they self-instrument
# under pytest --cov and race the parallel dispatcher (the 7us.6 flaky
# "No data to report" bug) and are slower than the in-process main()
# pattern. The subprocess_spawn_allowlist in pyproject.toml exempts tests
# that genuinely need a real subprocess (they must scrub COVERAGE_PROCESS_START
# + COV_CORE_*). Defense-in-depth pairing with cmn.
check-tests-no-subprocess-spawn:
    uv run python -m livespec_dev_tooling.checks.tests_no_subprocess_spawn

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
        echo ":: scoping the Red gate by staged-path class (red_leg_scope): coverage gates skip"
        echo ":: (verified at the Green amend) + any orthogonal legs a staged unit test cannot affect"
        just red_staged="$test_staged" check
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
    if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
        echo ":: pre-push: green token matched — tree byte-identical to last green check; skipping full aggregate (CI is authoritative)"
        exit 0
    fi
    just check

# Change-aware aggregate for agent dispatch (work-item livespec-dev-tooling-ool).
# Compares the branch against origin/master, detects the change class, and routes
# to the appropriate check subset locally:
#   - Zero .py changes (doc/config/yml/json/deletion-only) → check-pre-commit-doc-only
#     (fast gate; avoids the full 44-check Python suite for trivial changesets)
#   - Any .py changes → full `just check` aggregate (same safety level as today)
# CI ignores this target and continues to run the full matrix as the authoritative
# safety net. Agents SHOULD call `just check-scoped` instead of `just check` so
# that trivial changesets (e.g. a stray-gitlink deletion) pay only the doc-only cost.
check-scoped:
    #!/usr/bin/env bash
    set -uo pipefail
    upstream="origin/master"
    changeset=$(git diff --name-only "${upstream}...HEAD")
    if [[ -z "$changeset" ]]; then
        echo ":: check-scoped: no changes vs ${upstream}; nothing to gate"
        exit 0
    fi
    py_changed=$(echo "$changeset" | grep -E '\.py$' || true)
    if [[ -z "$py_changed" ]]; then
        echo ":: check-scoped: no .py changes vs ${upstream} (change class: doc/config/deletion)"
        echo ":: running fast doc-only subset; CI runs the full matrix as the load-bearing gate"
        just check-pre-commit-doc-only
        exit $?
    fi
    echo ":: check-scoped: .py changes detected vs ${upstream}: running full check aggregate"
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
