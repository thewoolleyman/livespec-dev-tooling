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
# the one arming that cannot block an unrelated commit.
#
# THE ARMING IS SCOPED TO WHAT THIS COMMIT AUTHORS, which is what makes
# that last sentence true. Two levers are set together: the release lever
# arms the tier, and LIVESPEC_SCOPE_HEADING_COVERAGE_TODOS_TO_HEAD_DIFF
# narrows its VERDICT to the registry entries added or modified since
# HEAD. Unscoped the tier judged the WHOLE registry, so from 2026-08-16
# until livespec-dev-tooling-3ztbdq every commit that added a heading was
# refused for the 58 pre-existing unowned entries it never touched, and
# tests/heading-coverage.json was unwritable. The narrowing is of the
# verdict only: an out-of-scope TODO is still reported (warning level,
# `out_of_staged_scope`), and a baseline git cannot produce falls back to
# arming the whole registry rather than to arming nothing. The LLOC
# soft-band check is deliberately NOT armed here: entering the soft
# band during authoring is allowed by design (constraints.md "File
# LLOC ceiling"); its release-tier reds are a burn-down concern, not a
# wiring one.
echo ":: doc-only subset: repo-state checks for non-.py input surfaces"
just check-claude-md-coverage
just check-comment-line-anchors
just check-agents-ai-references-resolve
just check-plan-anchor-declared
just check-vendor-manifest
if git diff --cached --name-only | grep -qx 'tests/heading-coverage.json'; then
    echo ":: staged changeset edits tests/heading-coverage.json — arming the TODO-ownership release tier for the entries this commit authors"
    LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST=true \
        LIVESPEC_SCOPE_HEADING_COVERAGE_TODOS_TO_HEAD_DIFF=true \
        just check-no-todo-registry
else
    just check-no-todo-registry
fi

# check-heading-coverage ALWAYS runs — it is a repo-state check over input
# surfaces a doc-only changeset can touch, exactly like the six above. Its
# direction 5 (the TODO-`reason` acknowledgment guard, plan
# fleet-heading-coverage-convergence charter D4, ratified at v064) is the one
# direction with a lever: unset it REPORTS a non-acknowledging reason at
# warning level, and LIVESPEC_SCOPE_HEADING_COVERAGE_REASONS_TO_HEAD_DIFF arms
# the VERDICT for the rows this commit AUTHORS.
#
# The arming is scoped for the same reason the two levers above are, and
# against the same incident (livespec-dev-tooling-3ztbdq): at P1 landing all
# 373 heading-coverage TODO rows across the fleet carry reasons this guard
# rejects, so a whole-registry verdict would refuse every commit for rows it
# never touched and make the shared co-edit registry unwritable again. Those
# rows burn down under the plan's P2 track; what this arming refuses is a NEW
# cop-out. An out-of-scope finding is still reported (warning,
# `out_of_staged_scope`), and a baseline git cannot produce falls back to
# judging every reason rather than to judging none.
if git diff --cached --name-only | grep -qx 'tests/heading-coverage.json'; then
    echo ":: staged changeset edits tests/heading-coverage.json — arming the TODO-reason acknowledgment guard for the rows this commit authors"
    LIVESPEC_SCOPE_HEADING_COVERAGE_REASONS_TO_HEAD_DIFF=true \
        just check-heading-coverage
else
    just check-heading-coverage
fi

# The shrink-only debt ratchet (plan fleet-heading-coverage-convergence
# charter D3, ratified at v064) is THE authoring-time tier: a `TODO` row
# absent from tests/heading-coverage-debt.json is a new cop-out, and the
# register may only shrink. It ALWAYS runs here — a repo-state check over
# input surfaces a doc-only changeset can touch, exactly like the six above.
#
# LIVESPEC_SCOPE_HEADING_COVERAGE_DEBT_TO_HEAD_DIFF narrows its VERDICT to the
# rows this commit AUTHORS whenever the changeset touches either file. The
# reasoning is the scope lever's above, and the incident is the same one
# (livespec-dev-tooling-3ztbdq): armed over a whole register, a gate on a
# shared mandatory co-edit registry refuses commits for rows they never
# touched, and the file becomes unwritable. An out-of-scope finding is still
# REPORTED (warning, `out_of_staged_scope`); only the verdict narrows. A
# changeset touching neither file gets the unscoped whole-register verdict,
# which the frozen baseline already satisfies.
if git diff --cached --name-only |
    grep -qxE 'tests/heading-coverage(-debt)?\.json'; then
    echo ":: staged changeset edits a heading-coverage file — scoping the debt ratchet to the rows this commit authors"
    LIVESPEC_SCOPE_HEADING_COVERAGE_DEBT_TO_HEAD_DIFF=true \
        just check-heading-coverage-debt-register
else
    just check-heading-coverage-debt-register
fi
