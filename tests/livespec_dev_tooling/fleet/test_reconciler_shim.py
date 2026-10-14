"""Tests for `livespec_dev_tooling/fleet/_reconciler_shim.py`.

The master-health reconciler's DISTRIBUTION surface — child D of plan
`red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`, work-item
`livespec-dev-tooling-dw7dzd`). C1 shipped the reconciler's DECISIONS as four
pure modules under `livespec_dev_tooling/cross_repo/`; this module is how those
decisions REACH a fleet repository: the canonical per-repo shim, the canonical
reusable workflow the shim calls, and the obligation row that fails a member
whose shim is missing or drifted.

The trigger assertions parse the canonical shim's `on:` block into its events
rather than matching substrings against the whole file. A substring match
cannot tell "`types: [completed]` under `workflow_run`" from the same bytes
under some other event, so it would keep passing through exactly the edit that
moves a trigger onto the wrong event — and that edit is silent, because a
workflow with a misplaced trigger is still a VALID workflow that simply never
fires on the thing the reconciler depends on.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.fleet._reconciler_shim import (
    REUSABLE_RECONCILER_WORKFLOW,
    reconciler_shim_content,
)

__all__: list[str] = []


_OWNER = "acme"

# GitHub's own floor for a `schedule:` trigger is five minutes, so "a schedule
# no coarser than five minutes" IS `*/5`. The assertion below is written as an
# INEQUALITY rather than a literal match on purpose: the deadline enforcement
# and the missed-event cover both ride this cadence, so a later coarsening
# (`*/15`, an hourly cron) must fail here instead of reading as a cosmetic
# edit to a quoted string.
_COARSEST_RECONCILE_MINUTES = 5

_CRON = re.compile(r"- cron: '(?P<expression>[^']+)'")
_EVERY_N_MINUTES = re.compile(r"^\*/(?P<step>\d+)$")
_EVENT = re.compile(r"^  (?P<event>\w+):")


def _shim() -> str:
    return reconciler_shim_content(owner=_OWNER)


def _on_events(*, source: str) -> dict[str, str]:
    """Each event under the workflow's `on:` key, mapped to its own block.

    The trigger region is cut out FIRST — between the `on:` key and the `jobs:`
    key — so an event name is only ever read from the trigger block it actually
    sits in. A canonical shim whose first trigger line is not an event name
    raises `KeyError` here rather than being silently attributed to a
    neighbour; loud is the right failure for a helper that exists to stop
    exactly that kind of misattribution.
    """
    region = source.split("\non:\n", 1)[1].split("\njobs:", 1)[0]
    events: dict[str, str] = {}
    name = ""
    for line in region.splitlines():
        match = _EVENT.match(line)
        if match is None:
            events[name] = f"{events[name]}{line}\n"
            continue
        name = match.group("event")
        events[name] = ""
    return events


def test_the_shim_fires_on_master_ci_completion() -> None:
    """`workflow_run` on the CI workflow's completion is the primary trigger.

    `workflow_run` matches on the upstream workflow's `name:`, not its file
    name, and every fleet repository's gating workflow is named `CI`. Both
    conclusions are wanted: a FAILURE opens the episode, and a SUCCESS is what
    closes it, so filtering to `completed` rather than to a conclusion is what
    lets one trigger serve the whole episode lifecycle.
    """
    events = _on_events(source=_shim())

    assert "workflow_run" in events, (
        "without `workflow_run` the reconciler learns of a red master only on "
        "its next scheduled tick, which spends the latency the hard cap budgets"
    )
    assert "workflows: [CI]" in events["workflow_run"]
    assert "types: [completed]" in events["workflow_run"]


def test_the_shim_fires_on_revert_and_fix_forward_pull_request_events() -> None:
    """Revert and fix-forward pull requests both reach the reconciler.

    There is deliberately NO `branches:` filter. A revert pull request sits on
    GitHub's generated `revert-<n>-<branch>` head, but a FIX-FORWARD rides a
    head branch of the author's choosing, so any filter narrow enough to name
    the revert is blind to the claim that holds it. `labeled` is in the set
    because the fix-forward CLAIM is mechanical — a label on the revert pull
    request — and a claim the reconciler only notices on the next tick is a
    claim that loses a race against the revert it is meant to hold.
    """
    events = _on_events(source=_shim())

    assert "pull_request" in events
    types = events["pull_request"]
    for event_type in ("opened", "reopened", "synchronize", "labeled", "closed"):
        assert event_type in types, event_type


def test_the_shim_reconciles_on_a_schedule_no_coarser_than_five_minutes() -> None:
    """The cadence that enforces the deadline and covers a missed event.

    GitHub drops `workflow_run` and `pull_request` deliveries, and the hard cap
    is a DEADLINE — it has to fire on a branch where nothing is happening, which
    is precisely the state that generates no events at all. So the schedule is
    not redundant with the event triggers; it is the only one of the three that
    works when the forge has gone quiet.
    """
    expressions = _CRON.findall(_shim())

    assert expressions, "the shim must carry a `schedule:` trigger"
    for expression in expressions:
        minutes, *rest = expression.split()
        step = _EVERY_N_MINUTES.match(minutes)
        assert step is not None, (
            f"cron minute field {minutes!r} is not an every-N-minutes step, so "
            "the cadence cannot be read as a bound at all"
        )
        assert int(step.group("step")) <= _COARSEST_RECONCILE_MINUTES, expression
        assert rest == ["*", "*", "*", "*"], (
            f"cron {expression!r} restricts hour, day, month or weekday — a "
            "reconciler that sleeps through part of the week cannot enforce a "
            "deadline during it"
        )


def test_the_shim_calls_the_reusable_reconciler_workflow_in_the_owners_dev_tooling() -> None:
    """The shim is a THIN caller: it declares triggers and delegates.

    The owner is templated rather than hardcoded so the shim a fork or a second
    organisation receives calls ITS dev-tooling, and `secrets: inherit` is what
    carries `APP_ID` / `APP_PRIVATE_KEY` through to the reusable workflow that
    mints the fleet App token.
    """
    shim = _shim()

    assert f"uses: {_OWNER}/livespec-dev-tooling/{REUSABLE_RECONCILER_WORKFLOW}@" in shim
    assert "secrets: inherit" in shim
