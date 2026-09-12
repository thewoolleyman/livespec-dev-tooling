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
export skip := ""

# pytest-xdist worker count, lane-aware (plan/fabro-ci-image-factoring cont.5).
# GitHub-hosted CI (LIVESPEC_CI_LANE=hosted, set from CI_RUNNER_LABELS in
# ci.yml) uses all cores (-n auto — GH runners are small + dedicated). The
# self-hosted/local lane throttles to LIVESPEC_TEST_PARALLELISM, defaulting to
# 25% of cores (min 1) so a shared host is never oversubscribed. Tune per host
# by exporting LIVESPEC_TEST_PARALLELISM (a dedicated box can set it to `auto`
# or a high N); local dev may export it to speed a laptop run.
export test_nprocs := if env_var_or_default("LIVESPEC_CI_LANE", "local") == "hosted" { "auto" } else { env_var_or_default("LIVESPEC_TEST_PARALLELISM", `c=$(nproc 2>/dev/null || echo 4); n=$(( c / 4 )); [ "$n" -ge 1 ] || n=1; echo "$n"`) }

# `red_staged` — the single staged test path at a Red commit (empty
# otherwise). When non-empty, `check:` derives the Red-mode skip set
# from the staged-path CLASS via `red_leg_scope` and UNIONs it into
# `skip`: always the coverage gates (verified at the Green amend) plus
# any orthogonal legs a staged unit test cannot affect (livespec's
# e2e-mock / prompts / doctor-static — dev-tooling has none, so it is
# the coverage floor here; the win lands cross-repo via the pin bump).
# Work-item livespec-dev-tooling-7us.6; research item #4. The tracked
# `check-targets.txt` inventory is the SINGLE source of truth — the
# script passes it and the staged path to the scope module, which
# computes the skip set and FAILS FAST (the caller then runs the full
# aggregate) rather than ever emitting an empty Red selection.
#
# DECIDED 2026-09-07 (livespec-dev-tooling-bvbe): dev-tooling will NOT
# wire doctor-static into `check:` either, so "dev-tooling has none"
# above stays true BY CHOICE rather than by oversight. The static
# doctor is livespec CORE's suite: core runs it from its own tree, and
# nothing in this repo's gate path materializes a core checkout. Wiring
# it would make this repo's merge gate resolve core out of a host-level
# plugin install that CI runners and fresh clones do not have — a gate
# whose verdict depends on the host — and fetching core at gate time to
# fix that is barred by the ratified "Network I/O from any check"
# non-goal in SPECIFICATION/spec.md. It would also aim the gate at core
# MASTER while `.livespec.jsonc` pins core at a tag, so a core-side
# catalogue change could redden this repo on a commit it did not cause;
# and it would close a dependency loop, since core already consumes
# THIS repo's checks and spec.md lists a dependency the other way as a
# non-goal. The ratified venue for the static-doctor verdict is the
# `/livespec:revise` post-step, per spec.md's Definition of Done ("The
# doctor static phase passes against the working spec").
#
# ACCEPTED RESIDUAL RISK, named because bvbe is what it looks like: a
# finding of that class can sit in tree from commit until the next
# revise, and a spuriously non-zero revise wrapper teaches its readers
# to ignore the exit code that would report a REAL ratification
# failure. The mitigation is hermetic and repo-local — pin the specific
# rule in the offending module's own test, as bvbe does — NOT a gate
# that reaches outside the repo for its verdict.
export red_staged := ""

# `hook_gate` — set to a non-empty value by the two LOCAL git-hook gates
# (`check-pre-commit`, `check-pre-push`) and by nothing else. When set,
# `scripts/just/check.sh` UNIONs its own `hook_gate_skips` list into
# `skip`, omitting the aggregate members whose verdict is a fact about
# the WORLD at this instant rather than about the commit being made.
# Default empty, so a bare `just check` — the operator's own world-gate
# run — is unchanged and still runs every member. This is a CALLER
# distinction, not a lever on any check: no recipe body changes, and no
# env var, exemption, or opt-in can demote a target from a run that did
# not ask for the hook-gate subset (work-item livespec-dev-tooling-mmqe,
# absorbing tkzf).
export hook_gate := ""

# Default to listing targets when no recipe is invoked.
default:
    @just --list

# ---------------------------------------------------------------
# First-time setup.
# ---------------------------------------------------------------

# Worktree-discipline pack recipe fragments — OPTIONAL imports (`import?`, NOT
# plain `import`): the fragments are gitignored-and-installed by
# `just install-worktree-pack` (run from the `worktree-pack` local obligation
# row that `bootstrap` walks), so they are absent on a fresh clone until then.
import? 'dev-tooling/worktree.just'
import? 'dev-tooling/branch-protection.just'
# First-touch setup — a THIN delegator to this package's OWN LOCAL first-touch
# reconcile verb (`livespec_dev_tooling.fleet.local_reconcile`), the generalized
# successor to this recipe's former inline steps (livespec-zs22.8 M5). This repo
# IS livespec_dev_tooling, so `uv run python -m ...` runs the local package
# directly (no external pin). The verb walks the LOCAL obligation partition
# (`contract.LOCAL_OBLIGATION_ROWS`): mise trust/install, uv sync, the
# canonical worktree pack, the structural
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
# source. Applies the same declared-ness gate as its verifier: a
# DECLARED-ABSENT key no-ops at exit 0 (this consumer does not carry the
# neutral hook body); an UNDECLARED key is a hard error naming it. The
# `check-no-shadow-ledger-body-identical` verifier guards the installed
# bytes against drift.
install-no-shadow-ledger:
    uv run python -m livespec_dev_tooling.install_no_shadow_ledger

# Install (or idempotently re-install) the canonical worktree-discipline pack
# into the current checkout's `dev-tooling/` directory. The file set is NOT
# restated here — `install_worktree_pack.WORKTREE_PACK_FILES` is its single
# enumeration, and three hand-written copies of it had already drifted apart
# (livespec-dev-tooling-l5gypl). The installer module is the
# single canonical-body carrier, retiring the copier-template COPIES. The pack
# files are GITIGNORED-AND-MATERIALIZED, never tracked: nothing is committed,
# and each checkout re-materializes them. `bootstrap` covers this automatically
# via the `worktree-pack` LOCAL obligation row, so this recipe is the standalone
# repair path rather than a step bootstrap must duplicate. The
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

# Compare each enabled Claude plugin's installed build with the locally
# resolved origin/<ref> of its committed marketplace pin. This is deliberately
# a world-state operator probe rather than a member of `check:`: installed
# records and marketplace clones are host-local and can change without a commit.
plugin-build-currency:
    mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.plugin_build_currency

# Idempotent host-wide Codex plugin provisioning. Codex does not support
# project-scoped plugin enablement, so these registrations intentionally land in
# the user's default CODEX_HOME and are visible to every repo on the host. Codex
# is an optional dogfooding runtime; bootstrap skips this target when the CLI is
# absent but fails on real install errors when Codex is present.
ensure-codex-plugins:
    scripts/just/ensure-codex-plugins.sh

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

# scripts/just/check.sh owns fail-closed mirror validation and the aggregate's
# continue-on-failure behavior. The literal array is a compatibility bridge for
# livespec CORE readers pinned to v1.17.1; the script compares it byte-for-entry
# with check-targets.txt before dispatch.
#
# Every target must run and the complete failure set be reported rather than
# stopping at the first failing member, so errexit is deliberately omitted.
check:
    #!/usr/bin/env bash
    set -uo pipefail
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
        check-ci-gate-parity
        check-ci-matrix-completeness
        check-claude-md-coverage
        check-comment-line-anchors
        check-commit-pairs-source-and-test
        check-file-lloc
        check-fleet-marketplace-relative-sources
        check-global-writes
        check-handoff-dispatch-routing
        check-heading-coverage
        check-heading-coverage-debt-register
        check-hook-trees-not-io-exempt
        check-keyword-only-args
        check-local-memory-drift-audit
        check-main-guard
        check-marketplace-ref-release-only
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
        check-no-shadow-ledger-body-typechecks
        check-no-todo-registry
        check-no-write-direct
        check-partition-completeness
        check-pbt-coverage-pure-modules
        check-per-file-coverage
        check-plan-anchor-declared
        check-plan-epic-parity
        check-plan-no-live-handoff-file
        check-plan-no-tombstone
        check-plan-record-conformance
        check-plugin-resolution
        check-primary-checkout-commit-refuse-hook-installed
        check-private-calls
        check-public-api-result-typed
        check-red-green-replay
        check-required-role-keys-declared
        check-rop-pipeline-shape
        check-self-hosted-routing
        check-self-hosted-uv-lane
        check-shell-quality
        check-skill-invocation-paths
        check-source-trees-scoped-to-consumer
        check-supervisor-discipline
        check-tests-mirror-pairing
        check-tests-no-subprocess-spawn
        check-tool-backed-check-completeness
        check-vendor-manifest
        check-work-item-interpolation-delimiters
        check-work-item-status-vocabulary
        check-wrapper-shape
        check-ansible-lint
        check-lint
        check-format
        check-types
        check-coverage
        check-fleet-conformance
        check-fleet-conformance-admin
        check-fabro-image-pin-lockstep
        check-no-direct-github-access
        check-no-workflow-edits
        check-shipped-path-release-guard
        check-uv-lock-version-sync
    )
    scripts/just/check.sh "${targets[@]}"

# ---------------------------------------------------------------
# Tool-backed checks. NOT canonical-aggregate slugs (not in
# canonical_checks.py's discovery set — they live as helper recipes,
# not under livespec_dev_tooling/checks/), so check-aggregate-
# completeness does not enforce them. They ARE literal members of the
# tracked `check-targets.txt` inventory (repo-private block) AND of the
# CI check-python matrix; the check-tool-backed-check-completeness
# meta-check enforces that both-surfaces wiring (epic li-pyright-gate,
# work-item li-pyright-gate-wi3, LITERAL-membership design). check-lint
# / check-format are cheap ruff passes; the coverage gate is
# consolidated onto the SINGLE pytest run that check-per-file-coverage
# already performs (see check-coverage below).
# ---------------------------------------------------------------

# --- Ansible: the LEGACY-ONLY host-provisioning tree under `ansible/` ---
#
# livespec work-item livespec-sab5gn.4. `ansible/inventory/legacy.yml` covers
# the pre-Talos Ubuntu machines and MUST NEVER list a Talos node; read its
# header before adding a host.
#
# WHY `uvx` RATHER THAN A pyproject DEPENDENCY GROUP. Ansible is a tool this
# repo INVOKES, never a library it imports, and ansible-core 2.21 requires
# Python >=3.12 while this repo's `requires-python` floor is >=3.10.16.
# Raising that floor is a fleet-wide decision about the shared enforcement
# suite and has nothing to do with provisioning hosts, so the tool resolves
# through `uvx` against its own interpreter with both versions pinned
# exactly. The justfile stays the single source of truth for the invocation.

check-ansible-lint:
    uvx --from ansible-lint==26.8.0 --with ansible-core==2.21.4 ansible-lint ansible/

# `ansible-drift` — the drift report. This is what replaced the bespoke
# verify-installed-tree.sh: it reports what the host would change and changes
# nothing. Run it before every apply.
[positional-arguments]
ansible-drift *args:
    uvx --from ansible-core==2.21.4 ansible-playbook --check --diff -i ansible/inventory/legacy.yml "$@"

# `ansible-apply` — converge the named playbook. Idempotent; re-running is the
# supported repair path. Run `just ansible-drift <playbook>` first.
[positional-arguments]
ansible-apply *args:
    uvx --from ansible-core==2.21.4 ansible-playbook -i ansible/inventory/legacy.yml "$@"

# Operator-invoked, future-state-only Git author identity audit. The output
# path MUST be below this checkout's ignored tmp/ tree. This is deliberately
# absent from `just check` and CI: it reaches all four legacy hosts and verifies
# caller-supplied Fabro canary evidence against the named commit.
[positional-arguments]
git-identity-audit output fabro_evidence:
    uv run python -m livespec_dev_tooling.fleet.git_identity_audit "$1" "$2"

check-lint:
    uv run ruff check .

check-format:
    uv run ruff format --check .

check-types:
    uv run pyright

# `warm-typecheck` — populate pyright's bundled node runtime + typeshed
# ONCE, serially, so a later PARALLEL `just check` never cold-downloads it
# concurrently. The `pyright==<pin>` PyPI wrapper fetches the node-based
# pyright (typeshed bundled inside) on its first invocation; `just check`
# runs its targets through `parallel_check_dispatcher`, so on a COLD cache
# two targets can race that first fetch and leave it half-written, which
# surfaces as pyright's "Stub file not found for 'typing'". Invoking pyright
# once up front makes that fetch happen serially and completely.
#
# This exists for the delegated pre-push GATE POD, whose cache is cold every
# run: it copied UV_CACHE_DIR=/__w/_warm/uv from the ARC runner template but
# has no volume seeded there (only an emptyDir workspace), and the sandbox
# image deliberately pre-warms no uv packages. So the gate container script
# runs `just warm-typecheck` before `just hook_gate=1 check` — see
# ci-runner/k3s/phase2/gates/gate-job-template.yaml. On a warm dev/CI cache
# it is a fast no-op. Like `check-static`, it is a helper recipe: NOT a
# tracked check-target, NOT a canonical slug, NOT in the CI matrix.
# (plan livespec `k3s-on-gmktec-for-vps-usage`, epic livespec-sab5gn,
# slice F livespec-dev-tooling-rwmo.6.)
warm-typecheck:
    uv run pyright --version

# `check-static` — fastest-first fail-fast helper for fast agent/dev
# feedback (work-item livespec-dev-tooling-7us.8). Runs ONLY the cheap
# static checks — `ruff format --check .`, `ruff check .`, `pyright`
# (i.e. check-format, check-lint, check-types) — as a fail-fast
# sequence: it STOPS at the first failing check and exits non-zero, so
# a sub-2s ruff/pyright failure surfaces immediately instead of after
# `just check`'s slow pytest+coverage tail. This is a developer/agent
# convenience like the helper recipes above; it is deliberately NOT a
# member of the tracked check-target inventory, NOT a
# canonical slug (no livespec_dev_tooling/checks/ module), and NOT in
# the CI matrix. The authoritative full gate remains `just check`
# (still run at pre-push and in CI) — `check-static` is a fast
# pre-flight, never a replacement for it.
check-static:
    scripts/just/check-static.sh

# Factory-boundary guard: fail if the current branch changes GitHub workflow
# files without human authorization. Delegates to the worktree-pack's single
# canonical body (livespec-dev-tooling-fy02) — installed into dev-tooling/ by
# `just install-worktree-pack`, byte-verified by the pack arm of
# check-primary-checkout-commit-refuse-hook-installed, no escape of any kind.
# A repo-LOCAL member of the `check` aggregate (never mirrored into CI: the
# guard is a CI-venue no-op by design); the Dispatcher janitor invokes it too.
check-no-workflow-edits:
    bash dev-tooling/check-no-workflow-edits.sh

# Release-drift guard: fail when uv.lock's own editable `[[package]]` entry
# records a different version than pyproject.toml's `[project].version`. The
# PREVENTION is the release-please-config.json `extra-files` entry that rewrites
# both numbers in the same release commit; this is its backstop, because a
# release-please JSONPath that stops matching is a SILENT no-op that would
# quietly restore the every-checkout-starts-dirty behavior. Repo-private (not
# under livespec_dev_tooling/checks/), so check-aggregate-completeness does not
# enforce it; a literal member of check-targets.txt's repo-private block.
#
# `--no-sync` is LOAD-BEARING, not tidiness: a bare `uv run` resolves the
# environment first, which reconciles uv.lock's self-entry to the pyproject
# version BEFORE the module opens the file. The check would then read a lock uv
# had just repaired, return 0 against real drift, and dirty the tree doing it —
# committing the very bug this work-item fixes. With `--no-sync` uv skips the
# resolve, so the module reads the COMMITTED bytes and the drift surfaces.
check-uv-lock-version-sync:
    uv run --no-sync python -m livespec_dev_tooling.uv_lock_version_sync

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
# Helper recipe (like `check-static`): NOT a member of the tracked
# check-target inventory, NOT a canonical slug, NOT in the CI
# matrix.
changed-files:
    scripts/just/changed-files.sh

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
# of the tracked check-target inventory, NOT a canonical slug,
# and NOT in the CI matrix.
check-changed:
    scripts/just/check-changed.sh

# Aggregate (total) coverage gate at `fail_under = 100` (pyproject.toml
# [tool.coverage.report]). Consume-once reuse of the CLEAN producer run
# (work-item livespec-dev-tooling-yilyxr.1): check-per-file-coverage now
# runs its suite with COVERAGE_FILE UNSET, so its repo-root `.coverage`
# measures IDENTICALLY to this recipe's own clean run by construction.
# When that file is present (the `just check` aggregate — the dispatcher
# serializes this target after the producer), this recipe reads it via
# `coverage report --fail-under=100` and DELETES it, so no stale data
# can ever back a later standalone report; when absent (CI's standalone
# matrix job, a manual invocation), it runs the clean suite itself.
# The reuse is gated on PROVENANCE (work-item livespec-dev-tooling-sc0z):
# the producer stamps its run with the tracked-tree id from
# scripts/just/coverage-reuse-id.sh, and this recipe reuses a `.coverage`
# only under a matching marker (or inside a GitHub Actions job, where the
# file is this run's downloaded producer artifact by construction). A
# file without one — what a focused `pytest --cov` run leaves at the repo
# root — is discarded and the clean suite runs, because reading it as the
# suite's verdict reported a 49% total against a Green amend.
#
# HISTORY, because this reuse was once reverted and the hazard must not
# be reintroduced silently: the PREVIOUS reuse read the producer's data
# from the dispatcher's EXPORTED namespaced COVERAGE_FILE (the isolation
# of work-item livespec-dev-tooling-cmn). A module whose own coverage is
# self-referential on coverage's machinery — code branching on
# `COVERAGE_FILE == COV_CORE_DATAFILE` — read as COVERED under that
# exported env but UNCOVERED in CI's clean standalone run, so `just
# check` green-lit a false 100% that CI then failed at 99.99%. The
# revert's own condition ("reversible if a future design measures both
# gates identically without the divergence") is what the clean-producer
# design satisfies: the divergence came from the exported env, and the
# producer no longer runs under it.
#
# NOTE on the dispatcher: check-coverage remains check-per-file-coverage's
# namespace-shared CONSUMER in parallel_check_dispatcher.py, so it runs
# only after that producer completes — under this design that ordering
# is again a REAL data dependency (the producer writes the `.coverage`
# this recipe consumes), not the benign serialization it briefly was.
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
[positional-arguments]
check-fleet-conformance *args:
    uv run python -m livespec_dev_tooling.fleet.fleet_conformance "$@"

# Release-dispatch sibling-matrix filter (livespec-f73t Slice 2b):
# partitions the discovered sibling set by the per-member verdict
# artifact `check-fleet-conformance --emit-member-verdicts` wrote, so
# one non-conformant member is EXCLUDED from the fan-out (loudly, with
# its failing rows) instead of halting dispatch to every conformant
# member. Fail-closed: malformed/missing inputs or a sibling with no
# verdict entry exit 1 and keep the preflight job red. Invoked by
# reusable-release-dispatch.yml's fleet-preflight job; not part of the
# `check:` aggregate (it is a workflow helper, not a repo gate).
[positional-arguments]
filter-dispatch-matrix *args:
    uv run python -m livespec_dev_tooling.fleet.dispatch_matrix_filter "$@"

# ADMIN-vantage (world-gate) lane of the same fleet-membership contract.
# Two obligation rows — `secret-names` and `branch-protection` — need
# GitHub ADMIN scope on each member. Every AUTOMATED context that runs
# the central sweep above (per-PR CI, the scheduled
# fleet-conformance.yml, the release fan-out preflight) authenticates
# with the fleet GitHub App installation token, which deliberately
# lacks admin scope; and the central sweep's RUN lever is unset locally.
# So before this lane existed, those two rows were enforced in ZERO
# contexts.
#
# This lane ALSO owns the posture-gated adopter currency leg
# (livespec-dev-tooling-453): manifest `adopters` iterated for the
# `claude-plugin-currency` concern only, `posture: released` only —
# never the per-class obligation rows, which the spec binds to the
# `fleet` array alone. The fleet App's installation MUST be restricted
# to fleet repos, so a private released adopter is unreadable to every
# automated central-lane context; homing the leg here is what keeps it
# from being vacuously green. Pinned/none postures are reported as
# posture-excluded (a declared choice, honored by never reading the
# repo); an unreadable released adopter reports BLIND (error severity,
# it fails the run); findings are error-severity (fail loud).
#
# This is a WORLD GATE in the same sense as check-master-ci-green and
# check-branch-protection-alignment: it reads live world state under
# the OPERATOR's own admin `gh` credentials, is wired into the `just
# check` aggregate, and is deliberately NOT mirrored into the per-PR CI
# matrix, where the App token would make it always-skip. There is NO run
# lever: a lever defaulting to unset would restore the zero-enforcement
# hole this recipe exists to close.
#
# ⛔ ITS ENFORCEMENT POINT IS A DELIBERATE `just check`, NOT A GIT HOOK.
# The two LOCAL hook gates pass `hook_gate=1`, and `scripts/just/check.sh`
# omits this member for that caller alone (work-item
# livespec-dev-tooling-mmqe, absorbing tkzf). The reason is what a world
# gate IS: its verdict is a fact about nine OTHER repositories at this
# instant, so a sibling's unrepaired state refuses commits and pushes here
# that have nothing to do with it — measured 2026-09-06 06:35Z, when
# livespec-console-beads-fabro's `upstream-dep-gate-wired` required check
# (forbidden by contracts.md `required_check_missing_from_ci`) exited this
# lane 4 and refused a hand push in THIS repo. That is not a demotion: the
# recipe is unchanged, no lever or exemption exists, and a bare `just
# check` — the operator's own world-gate run — still runs it.
#
# COST, measured against the live 9-member fleet: ~35 GitHub API reads,
# ~18s. That is NOT cheaper than the central sweep, and the comment that
# used to sit here claiming otherwise would have been wrong. The reads
# are ~4 per member: the secrets list, the protection payload, and — for
# the branch-protection ALIGNMENT leg — the member's default branch plus
# its ci.yml. Every one of those is intrinsic to what the two rows
# assert; none is incidental, so the cost is proportionate rather than
# small. It runs in parallel with the pytest/coverage targets that
# dominate `just check`, so it does not extend the critical path.
#
# Credential-CLASS boundary (the context list above is exhaustive on
# purpose — CI is not the only deliberately-non-admin context that
# reaches this recipe): a Fabro dispatch sandbox's commit hooks run the
# `just check` aggregate holding only the dispatch credential, a
# `ghs_`-class GitHub App installation token projected as GITHUB_TOKEN,
# from which admin scope is DELIBERATELY withheld (the ratified livespec
# v045 capability boundary). That credential class is structurally NOT
# this lane's vantage — the lane belongs to the operator's deliberate
# `just check` under their own admin gh credentials — so under it the
# lane classifies
# its rows (and the adopter leg) OUT-OF-VANTAGE, names that owning
# context, and exits 0 at zero API reads. Treating the class as a
# shortfall instead was the repo-wide factory outage journaled on
# livespec-dev-tooling-34t2 (no sandbox could complete a Red commit).
# This is vantage classification via the shared `ghs_` credential-class
# rule (`holds_app_class_credential`), not a lever.
#
# Running it under a USER-class credential without admin scope makes
# both rows skip fleet-wide, which it reports as BLIND (error severity,
# exit 4) — this is the lane that SHOULD read them, so a credential
# shortfall fails the run rather than reading as a vacuous pass. No
# lever, env var, or exemption can demote it (livespec-dev-tooling-29qo,
# the b02 recorded end state); the dispatch-class classification never
# widens beyond the `ghs_` prefix.
check-fleet-conformance-admin:
    uv run python -m livespec_dev_tooling.fleet.fleet_conformance_admin

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

# GitHub request-budget Verifier (work-item livespec-dev-tooling-t2q4): fail
# when first-party code reaches GitHub directly — an argv whose first element
# is `gh`, or a string constant naming the GitHub API host — instead of going
# through livespec_dev_tooling.budgeted_gh.gh_read. Armed unconditionally: no
# lever, no warn-only mode, no skip. Repo-private (the module deliberately
# lives OUTSIDE livespec_dev_tooling/checks/, so canonical_check_slugs never
# discovers it) because arming it fleet-wide would redden three siblings that
# still hold 20 unrouted call sites, and would hard-fail the one fleet member
# with zero first-party Python on its anti-vacuous guard alone; promotion
# travels with that cross-repo retrofit, per livespec's New-obligation
# discipline. A literal member of check-targets.txt's repo-private block.
check-no-direct-github-access:
    uv run python -m livespec_dev_tooling.no_direct_github_access

check-coverage:
    scripts/just/check-coverage.sh

# ---------------------------------------------------------------
# Canonical aggregate recipes — one per canonical slug emitted by
# `python -m livespec_dev_tooling.canonical_checks --json`. Each
# resolves to `uv run python -m livespec_dev_tooling.checks.<slug>`
# with the snake_case slug.
# ---------------------------------------------------------------

check-agents-ai-references-resolve:
    uv run python -m livespec_dev_tooling.checks.agents_ai_references_resolve

# Wiring-completeness gate — verifies the tracked check-target inventory
# carries every canonical slug in alphabetical order
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
[positional-arguments]
check-check-coverage-incremental *args:
    uv run python -m livespec_dev_tooling.checks.check_coverage_incremental "$@"

# Always invoked plainly; the module self-manages its RUN/SKIP lever
# (epic li-cvaudit, cvtodo). `LIVESPEC_RUN_MUTATION` unset → the check
# logs "skipped" and exits 0; set to a non-empty value (CI sets it to
# `true`) → the mutmut suite runs. No external gate, no silent skip.
check-check-mutation:
    uv run python -m livespec_dev_tooling.checks.check_mutation

check-check-tools:
    uv run python -m livespec_dev_tooling.checks.check_tools

# PR-gate ≡ master-gate parity guard (plan pr-gate-master-parity, R2).
# The companion to check-ci-matrix-completeness: from this repo's OWN
# ci.yml, asserts no GATING job (one in ci-green.needs) conditions its
# real steps on a changeset `.py`-detection output (`py_changed`), which
# would run it on a push to master but skip it on a doc-only pull request.
# Warn-default (severity lever `LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST`),
# so the slug propagates and warns each not-yet-fixed repo without reddening it.
check-ci-gate-parity:
    uv run python -m livespec_dev_tooling.checks.ci_gate_parity

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

# Handoff dispatch-routing lint — active plan documents
# (legacy plan/*/handoff.md and migrated plan/*/epic.md, excluding
# plan/archive/) MUST route implementation through the factory dispatch route
# (the `drive` operation impl:<id> / the Dispatcher drain), never the
# colon-qualified in-session-implement token. Keeps the 2026-07-15
# defective-handoff-wording incident from regenerating.
check-handoff-dispatch-routing:
    uv run python -m livespec_dev_tooling.checks.handoff_dispatch_routing

# Always invoked plainly; the module self-manages its ONE lever
# (`LIVESPEC_SCOPE_HEADING_COVERAGE_REASONS_TO_HEAD_DIFF`), which arms
# direction 5 — the TODO-`reason` acknowledgment guard of plan
# fleet-heading-coverage-convergence charter D4, ratified at v064 — for the rows
# a commit AUTHORS. The authoring-time pre-commit subset sets it; unset here, so
# the aggregate, pre-push and CI REPORT a non-acknowledging reason at warning
# level without judging it. That is the per-commit tier the plan's P2 burn-down
# runs under: at P1 landing all 373 fleet rows carry rejected reasons, and
# judging them whole is the livespec-dev-tooling-3ztbdq shape that made
# tests/heading-coverage.json unwritable. The other four directions are
# unlevered and judge the whole tree here.
check-heading-coverage:
    uv run python -m livespec_dev_tooling.checks.heading_coverage

# The shrink-only heading-coverage debt ratchet (plan
# fleet-heading-coverage-convergence charter D3, ratified at v064). Always
# invoked plainly; the module self-manages both of its levers.
# `LIVESPEC_SCOPE_HEADING_COVERAGE_DEBT_TO_HEAD_DIFF`, which the
# authoring-time pre-commit subset sets, narrows the VERDICT to the rows a
# commit authors. Unset here, so the aggregate, pre-push and CI judge the whole
# register. `LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` — no_todo_registry's
# release lever, SHARED rather than duplicated, because the ratified clause
# pairs liveness and age in one sentence — arms the age bound (charter D5):
# unset, an overdue row warns and the direction contributes no exit code; set,
# a row whose first-seen date is older than the configured bound (default 30
# days) fails. Age stays release-tier-only because it depends on the CLOCK
# rather than on anything a commit authors, and a per-commit verdict on it
# could turn master red with no landed change. Regenerate the register with
# `just generate-heading-coverage-debt-register` — it is never authored by hand.
check-heading-coverage-debt-register:
    uv run python -m livespec_dev_tooling.checks.heading_coverage_debt_register

# Regenerate `tests/heading-coverage-debt.json` from the live
# `tests/heading-coverage.json`, stamping each row's first-seen date from git
# history. The register is DERIVED, never authored: a hand-edited baseline is
# an exemption list, and the ratchet it feeds would become a formality.
generate-heading-coverage-debt-register:
    uv run python -m livespec_dev_tooling.heading_coverage_debt

check-keyword-only-args:
    uv run python -m livespec_dev_tooling.checks.keyword_only_args

check-local-memory-drift-audit:
    uv run python -m livespec_dev_tooling.checks.local_memory_drift_audit

check-main-guard:
    uv run python -m livespec_dev_tooling.checks.main_guard

# Refuse a committed `.claude/settings.json` that pins a shared
# `thewoolleyman/livespec*` plugin marketplace to any ref other than `release`.
# The plugin marketplace registry is HOST-GLOBAL — one ref per marketplace name,
# shared by every checkout — so a tag pin here rewrites the slot every sibling
# repo reads and silently breaks their `ensure-plugins`.
check-marketplace-ref-release-only:
    uv run python -m livespec_dev_tooling.checks.marketplace_ref_release_only

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
# #1). OPT-IN via the `neutral_hook_body_path` role key: DECLARED-EMPTY
# (`""`) → sanctioned `info` no-op (this consumer does not carry the neutral
# hook body); declared non-empty → the configured path MUST be byte-identical
# to the single packaged carrier constant
# `install_no_shadow_ledger.CANONICAL_NO_SHADOW_LEDGER_BODY`. An UNDECLARED
# key is a hard ERROR naming it, per v0.54.12 — absence is no longer a
# sanctioned spelling of "not applicable". The installer recipe above runs
# the SAME gate, so the two agree in all three states; they diverged on the
# undeclared arm between slice L and livespec-dev-tooling-eihv.
check-no-shadow-ledger-body-identical:
    uv run python -m livespec_dev_tooling.checks.no_shadow_ledger_body_identical

# Strict-type Verifier for the SAME single-sourced neutral no-shadow-ledger
# Stop-hook body. The body ships as the wheel-safe string constant
# `install_no_shadow_ledger.CANONICAL_NO_SHADOW_LEDGER_BODY` (a carrier, not a
# real module), so pyright never sees it and an annotation regression would
# ship silently. This check renders the constant to a throwaway `.py` and runs
# pyright in strict mode (mirroring this repo's `[tool.pyright]` bar) against
# it, failing on any error diagnostic. Always runs (the constant always
# exists); the only skip is pyright being unavailable.
check-no-shadow-ledger-body-typechecks:
    uv run python -m livespec_dev_tooling.checks.no_shadow_ledger_body_typechecks

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
# CLEAN-ENV PRODUCER (work-item livespec-dev-tooling-yilyxr.1): the
# script runs both the suite and the per-file read with COVERAGE_FILE
# explicitly UNSET (`env -u`), overriding the dispatcher's namespaced
# export from work-item livespec-dev-tooling-cmn. That makes this run
# measure IDENTICALLY to CI's standalone clean jobs — the
# self-referential-branch leniency that once forced check-coverage to
# re-run the whole suite cannot occur — and its combined repo-root
# `.coverage` is the single data file check-coverage consumes
# (consume-once; see that recipe's comment). This is the PRODUCER of
# the full-tree coverage data shared with check-coverage; CI proves the
# clean-env full-suite measurement daily in both standalone matrix jobs.
# The run is stamped with a provenance marker
# (`.livespec-coverage-reuse-token`, gitignored) so the consumer can tell
# this file from a focused-run leftover (work-item livespec-dev-tooling-sc0z).
# In Red-mode pre-commit this target is omitted by `check-pre-commit`
# via the `check skip=...` argument (coverage is verified at the Green
# amend), so no ambient env-var read is needed here.
check-per-file-coverage:
    scripts/just/check-per-file-coverage.sh

# Plan-lifecycle enforcement — static half: every active legacy
# plan/*/handoff.md or migrated plan/*/epic.md declares a concrete ledger epic
# id (credential-free, runs everywhere, including consumer CI).
check-plan-anchor-declared:
    uv run python -m livespec_dev_tooling.checks.plan_anchor_declared

# Plan-lifecycle enforcement — ledger-parity half: an active legacy
# plan/*/handoff.md or migrated plan/*/epic.md must not point at a done/closed
# epic. Armed-only — self-skips unless LIVESPEC_RUN_PLAN_EPIC_PARITY and
# BEADS_DOLT_PASSWORD are set, so it never self-gates a credential-less
# `just check`.
check-plan-epic-parity:
    uv run python -m livespec_dev_tooling.checks.plan_epic_parity

# Plan-lifecycle carrier ban: no commit or push may ADD or MODIFY a live
# plan/<topic>/handoff.md or plan/<topic>/supervisor-handoff.md. Scoped to the
# CHANGE (the staged index UNIONed with origin/master...HEAD), not to the tree,
# so an existing live handoff file is frozen and deletable rather than an
# instant red. plan/archive/** and a plan's research/ tree are unaffected.
check-plan-no-live-handoff-file:
    uv run python -m livespec_dev_tooling.checks.plan_no_live_handoff_file

# Plan-lifecycle tombstone ban: a topic must not exist at BOTH
# plan/<topic>/ and plan/archive/<topic>/.
check-plan-no-tombstone:
    uv run python -m livespec_dev_tooling.checks.plan_no_tombstone

# The eleven ratified plan-record conformance verdicts (the orchestrator's
# SPECIFICATION/contracts.md §"Plan-record conformance checks", v095): the
# plan_slug family, the associated_work_item_id anchor pair, the delegated
# lifecycle parity, and the timeline family (close evidence, typed next_action,
# plus the two WARN verdicts that never fail a run).
# Armed-only — self-skips unless LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE and
# BEADS_DOLT_PASSWORD are set, so it never self-gates a credential-less
# `just check`. SHIPPED UNARMED: arm it in a tenant only after that contract's
# one-shot plan-record migration has run there. The delegated lifecycle leg
# reads plan_epic_parity's own LIVESPEC_RUN_PLAN_EPIC_PARITY lever.
check-plan-record-conformance:
    uv run python -m livespec_dev_tooling.checks.plan_record_conformance

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
[positional-arguments]
check-red-green-replay *args:
    uv run python -m livespec_dev_tooling.checks.red_green_replay "$@"

check-required-role-keys-declared:
    uv run python -m livespec_dev_tooling.checks.required_role_keys_declared

# Shipped-path release guard. NOT a canonical-aggregate slug — its module lives
# at livespec_dev_tooling/shipped_path_release_guard_check.py rather than under
# livespec_dev_tooling/checks/, so canonical_checks.py's filesystem walk does not
# discover it and it is wired in the repo-private block below the canonical set.
#
# Two modes on the `check-red-green-replay` precedent above, which solves the
# identical problem. WITH a message-file argument (lefthook's commit-msg hook
# passes `{1}`) it judges the pending commit against the staged diff. With NO
# argument — the `just check` / pre-push / CI invocation — it judges every
# non-merge commit in origin/master..HEAD. `"$@"` is therefore load-bearing:
# dropping it would silently run the range on every commit-msg invocation
# (work-item livespec-dev-tooling-sxdz).
[positional-arguments]
check-shipped-path-release-guard *args:
    uv run python -m livespec_dev_tooling.shipped_path_release_guard_check "$@"

check-rop-pipeline-shape:
    uv run python -m livespec_dev_tooling.checks.rop_pipeline_shape

# Self-hosted CI runner routing guard (security). Reading a repo's OWN
# .github/workflows/*.yml|*.yaml, fails when any workflow whose `on:` set
# contains a FORBIDDEN trigger (pull_request_target, workflow_run,
# issue_comment, repository_dispatch, merge_group, workflow_dispatch) also
# has a job whose `runs-on` references the unprivileged `local-ci`
# self-hosted label — the code-execution hole a fork-reachable/privileged
# non-PR event opens on the contained CI lane. Keyed on `local-ci`
# specifically (not generic self-hosted), so the privileged
# `livespec-orchestrator` gate runner is out of scope. Fail-by-default (no
# severity lever): this is a security guard, not a style check. A no-op for
# every repo with no local-ci job.
check-self-hosted-routing:
    uv run python -m livespec_dev_tooling.checks.self_hosted_routing

# A workflow routing gating jobs to self-hosted capacity via CI_RUNNER_LABELS
# and invoking uv must bound uv's fetch concurrency, lane-selected against the
# same fallback literal its runs-on uses. uv's default of 50 concurrent
# downloads per job, times the slots sharing one host, reddened master branches
# with PyPI timeouts. A genuine no-op in every hosted-only repo.
check-self-hosted-uv-lane:
    uv run python -m livespec_dev_tooling.checks.self_hosted_uv_lane

check-shell-quality:
    uv run python -m livespec_dev_tooling.checks.shell_quality

check-skill-invocation-paths:
    uv run python -m livespec_dev_tooling.checks.skill_invocation_paths

check-hook-trees-not-io-exempt:
    uv run python -m livespec_dev_tooling.checks.hook_trees_not_io_exempt

check-source-trees-scoped-to-consumer:
    uv run python -m livespec_dev_tooling.checks.source_trees_scoped_to_consumer

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
# LITERAL member of BOTH this repo's tracked check-target inventory
# AND the CI check-python matrix. Self-passes because the targets
# array + CI matrix wire all four literally.
check-tool-backed-check-completeness:
    uv run python -m livespec_dev_tooling.checks.tool_backed_check_completeness

check-vendor-manifest:
    uv run python -m livespec_dev_tooling.checks.vendor_manifest

# Ledger-text enforcement: a NON-CLOSED work item must not carry a literal
# doubled-brace template-interpolation delimiter pair in its editable fields or
# in an append-only comment — such a record makes ITSELF undispatchable. Closed
# items are out of the population by design (never dispatched, and historical
# ones still carry the pair). The conforming way to write about workflow syntax
# ships with the check: docs/work-item-interpolation-delimiters.md.
# Armed-only — self-skips unless LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS
# and BEADS_DOLT_PASSWORD are set, so it never self-gates a credential-less
# `just check`. Arm it only after a measured sweep reports zero non-closed
# offenders.
check-work-item-interpolation-delimiters:
    uv run python -m livespec_dev_tooling.checks.work_item_interpolation_delimiters

# Ledger-lane enforcement: a LIVE work item must sit at a status inside the
# runtime's declared `WorkItemStatus` vocabulary. `bd create` leaves a record at
# BEADS status `open`, which is not in it, and `lane_of` passes an unrecognised
# status straight out as a lane name nothing consumes — so the item is never
# ranked by `next`, never parked in `backlog`, never held at `blocked`, and
# never awaiting admission at `pending-approval`. Closed items are out of the
# population by design (never ranked, so no status can strand them). The check
# reports; it never re-triages, because answering the intake Definition-of-
# Ready gates for work you have not read is how a silent item becomes a
# wrongly-ranked one.
# Armed-only — self-skips unless LIVESPEC_RUN_WORK_ITEM_STATUS_VOCABULARY and
# BEADS_DOLT_PASSWORD are set, so it never self-gates a credential-less
# `just check`.
check-work-item-status-vocabulary:
    uv run python -m livespec_dev_tooling.checks.work_item_status_vocabulary

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
    scripts/just/check-pre-commit.sh

# When zero `.py` files are staged, `check-pre-commit` delegates here.
# `check-pre-commit` delegates here for zero-`.py` staged trees — a local
# pre-commit speed optimization only; pre-push and CI never subset.
check-pre-commit-doc-only:
    scripts/just/check-pre-commit-doc-only.sh

# Pre-push runs the FULL `just check` aggregate — the same gating set CI
# runs on a pull_request and on a push to master (PR gate ≡ master gate;
# plan pr-gate-master-parity, livespec-citqsd). The former zero-`.py`
# doc-only branch was retired; the sound green-token clean-tree skip is kept.
check-pre-push:
    scripts/just/check-pre-push.sh

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
    scripts/just/check-scoped.sh

# ---------------------------------------------------------------
# Detached gate runs — decouple gate RUNTIME from harness PATIENCE.
#
# The gate-start / gate-wait / gate-status / gate-list recipes now ship
# in the worktree-discipline pack's `worktree.just` fragment (imported
# above), backed by the canonical `dev-tooling/gate-run.sh` body the
# pack materializes — the same single-source pattern as the worktree
# recipes, so every governed repo gets the detached runner from
# `just bootstrap` with no per-repo wiring (work-item
# livespec-dev-tooling-yilyxr.7). A run that does not finish reports
# DIED_WITHOUT_VERDICT; it can never read as a pass.
# ---------------------------------------------------------------

# ---------------------------------------------------------------
# Pre-commit auxiliary gates.
# ---------------------------------------------------------------

# Ruff fix + format on staged .py files BEFORE the rest of the
# pre-commit gate runs. Non-blocking — unfixable issues fall through
# to the check-lint / check-format targets that the `just check`
# aggregate's tracked check-target inventory wires as literal members
# (repo-private block; epic li-pyright-gate, work-item
# li-pyright-gate-wi3). Re-stages post-autofix bytes.
lint-autofix-staged:
    scripts/just/lint-autofix-staged.sh

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
[positional-arguments]
tdd-commit *args:
    uv run python -m livespec_dev_tooling.tdd_commit "$@"
