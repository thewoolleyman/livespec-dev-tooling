#!/usr/bin/env bash
set -euo pipefail

# Doc-only pre-commit subset (work-item livespec-dev-tooling-yilyxr.5).
# Previously a literal no-op ("no repo-metadata checks wired yet"): a
# zero-.py changeset ran NOTHING locally, so repo-state breakage in
# docs/config/plan/spec surfaces only in CI. This wires the cheap
# repo-state checks whose input surfaces are exactly the files a
# doc-only changeset can touch (~8s total, measured). The full
# aggregate remains the load-bearing safety net at pre-push and in CI.
#
# check-no-todo-registry runs in its per-commit tier (warn-only) like
# everywhere else, EXCEPT when the staged changeset itself touches
# tests/heading-coverage.json: the commit that AUTHORS a TODO entry is
# armed to the release tier, because per that check's own contract "an
# unowned TODO entry is never valid" — refusing it at authoring time is
# the one arming that cannot block an unrelated commit. The LLOC
# soft-band check is deliberately NOT armed here: entering the soft
# band during authoring is allowed by design (constraints.md "File
# LLOC ceiling"); its release-tier reds are a burn-down concern, not a
# wiring one.
echo ":: doc-only subset: repo-state checks for non-.py input surfaces"
just check-heading-coverage
just check-claude-md-coverage
just check-comment-line-anchors
just check-agents-ai-references-resolve
just check-plan-anchor-declared
just check-vendor-manifest
if git diff --cached --name-only | grep -qx 'tests/heading-coverage.json'; then
    echo ":: staged changeset edits tests/heading-coverage.json — arming the TODO-ownership release tier for this commit"
    LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST=true just check-no-todo-registry
else
    just check-no-todo-registry
fi
