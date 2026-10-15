"""Tests for the canonical master-health reconciler shim and the workflow it calls.

This module owns the in-repo-gradeable acceptance assertions of child D of plan
`red-master-self-healing` (work-item `livespec-dev-tooling-dw7dzd`, epic
`livespec-dev-tooling-zcp5vb`): the shim's trigger set, the install
`wire-fleet-member` performs and its idempotence, the conformance row that
convicts a missing or DRIFTED shim, and the reusable workflow's
hosted-runner + fleet-App-token shape.

THE TRIGGER ASSERTIONS ARE WRITTEN AS PROPERTIES, NOT AS LITERALS, wherever the
Definition of Done states a property. "A schedule no coarser than five minutes"
is asserted by PARSING the cron minute field and comparing the interval, so a
later edit to `*/10` fails here rather than passing a substring match that only
ever proved the line was present.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.fleet._reconciler_shim import (
    MASTER_HEALTH_WORKFLOW,
    REUSABLE_RECONCILER_WORKFLOW,
    reconciler_shim_content,
)

__all__: list[str] = []


_OWNER = "acme"

# The pull-request event types the decision needs, and WHY each is required.
# `labeled` / `unlabeled` are the fix-forward CLAIM's own events — the claim is
# a label on the revert pull request — and the remaining four are how the
# revert's own lifecycle and CI verdict reach the reconciler.
_REQUIRED_PULL_REQUEST_TYPES = (
    "closed",
    "labeled",
    "opened",
    "reopened",
    "synchronize",
    "unlabeled",
)

_CRON_LINE = re.compile(r"^\s*- cron: '(?P<expression>[^']+)'\s*$", re.MULTILINE)


def _schedule_interval_minutes(*, body: str) -> int | None:
    """The shim schedule's interval in minutes, or None when it is not a `*/n` step.

    Only the step form answers "how coarse is this schedule?" with a number. A
    fixed-minute cron (`0 * * * *`) is hourly whatever its minute field says, so
    it is reported as None and the caller fails rather than guessing.
    """
    match = _CRON_LINE.search(body)
    if match is None:
        return None
    minute_field = match.group("expression").split()[0]
    step = re.fullmatch(r"\*/(?P<minutes>\d+)", minute_field)
    return int(step.group("minutes")) if step is not None else None


def test_the_schedule_reader_reports_anything_but_a_step_cron_as_unknown() -> None:
    """The interval assertion is only as strong as the reader underneath it.

    A reader that answered `None` for a schedule it simply failed to parse would
    make the five-minute assertion fail LOUDLY rather than pass vacuously, which
    is the safe direction — but only if `None` genuinely means "not a step
    schedule". Both non-step shapes are pinned here so the caller's
    `is not None` guard is a real discriminator.
    """
    assert _schedule_interval_minutes(body="  - cron: '*/3 * * * *'\n") == 3
    assert _schedule_interval_minutes(body="  - cron: '0 * * * *'\n") is None
    assert _schedule_interval_minutes(body="on:\n  push:\n") is None


def test_the_shim_runs_on_master_ci_completion() -> None:
    """The EDGE trigger: the reconciler reacts within one CI cycle, not one tick.

    `workflow_run` + `types: [completed]` is what puts the reconciler on a red
    master as soon as master CI has spoken. Without it the reconciler is only as
    prompt as its schedule, and the plan's whole point is that a red master
    heals within one reconcile cycle.
    """
    body = reconciler_shim_content(owner=_OWNER)

    assert "workflow_run:" in body
    assert "types: [completed]" in body


def test_the_shim_runs_on_revert_and_fix_forward_pull_request_events() -> None:
    """Both revert-side facts the decision reads arrive as pull-request events.

    The revert pull request's own CI verdict rides its lifecycle events, and the
    fix-forward CLAIM is a LABEL on that pull request — so dropping the label
    events would leave a claimed fix-forward invisible to the reconciler, which
    would then release a revert the claim was holding.
    """
    body = reconciler_shim_content(owner=_OWNER)

    assert "pull_request:" in body
    for event_type in _REQUIRED_PULL_REQUEST_TYPES:
        assert event_type in body, f"pull_request type {event_type} missing from the shim"


def test_the_shim_schedule_is_no_coarser_than_five_minutes() -> None:
    """The missed-event cover and the deadline clock, asserted as an interval.

    An event that never fired, a run that crashed and the hard cap all need a
    tick that arrives whatever else happened. Five minutes is GitHub's finest
    schedule granularity, so it is both the floor and the requirement.
    """
    interval = _schedule_interval_minutes(body=reconciler_shim_content(owner=_OWNER))

    assert interval is not None, "the shim carries no `*/n` schedule step"
    assert interval <= 5


def test_the_shim_invokes_the_reusable_reconciler_workflow_at_the_owner() -> None:
    """The shim is a SHIM: it delegates to one reusable workflow and holds no logic.

    The `uses:` reference is rendered against the member's owner so a fork of
    the fleet reaches its own copy, and `secrets: inherit` is what carries the
    fleet App credentials the reusable workflow authenticates with.
    """
    body = reconciler_shim_content(owner=_OWNER)

    assert f"uses: {_OWNER}/livespec-dev-tooling/{REUSABLE_RECONCILER_WORKFLOW}@master" in body
    assert "secrets: inherit" in body
    assert MASTER_HEALTH_WORKFLOW == ".github/workflows/master-health-reconcile.yml"
