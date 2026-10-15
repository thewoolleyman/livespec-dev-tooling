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

import base64
import json
import re

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._contract_classes import ALL_CLASSES
from livespec_dev_tooling.fleet._contract_model import ObligationRow
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS
from livespec_dev_tooling.fleet._reconcile_shims import (
    SHIM_BRANCH,
    reconcile_shim_workflows,
)
from livespec_dev_tooling.fleet._reconciler_shim import (
    MASTER_HEALTH_WORKFLOW,
    REUSABLE_RECONCILER_WORKFLOW,
    reconciler_shim_content,
)
from livespec_dev_tooling.fleet._rows_files import (
    BUMP_PIN_WORKFLOW,
    PIN_FRESHNESS_WORKFLOW,
    RELEASE_DISPATCH_WORKFLOW,
)

__all__: list[str] = []


_OWNER = "acme"
_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")

_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_MASTER_REF: tuple[str, ...] = ("api", "repos/acme/widget/git/ref/heads/master")
_BRANCH_PROBE: tuple[str, ...] = ("api", f"repos/acme/widget/git/ref/heads/{SHIM_BRANCH}")
_REFS_POST: tuple[str, ...] = (
    "api",
    "repos/acme/widget/git/refs",
    "--method",
    "POST",
    "--input",
    "-",
)
_PULLS_POST: tuple[str, ...] = (
    "api",
    "repos/acme/widget/pulls",
    "--method",
    "POST",
    "--input",
    "-",
)

_PIN_AND_BUMP_SHIMS = (BUMP_PIN_WORKFLOW, PIN_FRESHNESS_WORKFLOW, RELEASE_DISPATCH_WORKFLOW)

_RECONCILER_ROW_ID = "workflow-master-health-reconcile"

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


def _put_args(*, path: str) -> tuple[str, ...]:
    return ("api", f"repos/acme/widget/contents/{path}", "--method", "PUT", "--input", "-")


def _ok(*, payload: object) -> GhResult:
    """A successful API result carrying a JSON payload."""
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def _tree(*, paths: tuple[str, ...]) -> GhResult:
    return _ok(payload={"tree": [{"path": p, "mode": "100644"} for p in paths], "truncated": False})


def _make_context(
    *,
    table: dict[tuple[str, ...], GhResult],
    calls: list[tuple[tuple[str, ...], str | None]],
) -> FleetContext:
    """A call-recording `FleetContext` for owner `acme`."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        key = tuple(args)
        calls.append((key, stdin))
        return table.get(key, GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner=_OWNER, run_gh=lift_gh(runner))


def _mutating(*, calls: list[tuple[tuple[str, ...], str | None]]) -> list[tuple[str, ...]]:
    """The argv of every recorded call that would CHANGE the member repository."""
    return [args for args, _stdin in calls if "--method" in args]


def _install_table(*, present: tuple[str, ...]) -> dict[tuple[str, ...], GhResult]:
    """A canned table where `present` is already committed and the rest is writable."""
    table: dict[tuple[str, ...], GhResult] = {
        _TREE_ARGS: _tree(paths=present),
        _BRANCH_PROBE: GhResult(returncode=1, stdout="", stderr="Not Found"),
        _MASTER_REF: _ok(payload={"object": {"sha": "abc123"}}),
        _REFS_POST: _ok(payload={}),
        _PULLS_POST: _ok(payload={"number": 11}),
    }
    for path in (*_PIN_AND_BUMP_SHIMS, MASTER_HEALTH_WORKFLOW):
        table[_put_args(path=path)] = _ok(payload={})
    return table


def test_wire_fleet_member_writes_the_reconciler_shim_into_a_member_that_lacks_it() -> None:
    """The install leg: a member carrying every other shim but not this one gets it.

    `wire-fleet-member` is the ONLY path by which the shim reaches a fleet
    repository (plan charter item 6 — never configured by hand), so the bytes it
    PUTs must be the canonical body verbatim rather than anything rendered a
    second way. The PUT content is decoded and compared whole for that reason.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    ctx = _make_context(table=_install_table(present=_PIN_AND_BUMP_SHIMS), calls=calls)

    outcome = reconcile_shim_workflows(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowPass)
    assert MASTER_HEALTH_WORKFLOW in outcome.note
    put_body = next(
        stdin for args, stdin in calls if args == _put_args(path=MASTER_HEALTH_WORKFLOW)
    )
    assert put_body is not None
    decoded = base64.b64decode(json.loads(put_body)["content"]).decode("utf-8")
    assert decoded == reconciler_shim_content(owner=_OWNER)


def test_a_second_run_against_a_fully_wired_member_changes_nothing() -> None:
    """Idempotence, and the proof that the pass is not vacuous.

    The first clause is the Definition of Done's "a second run leaves the
    repository unchanged": against a member already carrying every shim the
    reconcile issues no mutating call at all. On its own that clause would also
    hold if the reconciler shim were simply absent from the install set, so the
    second clause drops ONLY that shim and requires the same reconcile to act —
    which is what makes the first clause a statement about THIS shim.
    """
    wired_calls: list[tuple[tuple[str, ...], str | None]] = []
    wired = _install_table(present=(*_PIN_AND_BUMP_SHIMS, MASTER_HEALTH_WORKFLOW))

    settled = reconcile_shim_workflows(
        ctx=_make_context(table=wired, calls=wired_calls), member=_MEMBER
    )

    assert isinstance(settled, RowPass)
    assert _mutating(calls=wired_calls) == []

    lacking_calls: list[tuple[tuple[str, ...], str | None]] = []
    reconcile_shim_workflows(
        ctx=_make_context(table=_install_table(present=_PIN_AND_BUMP_SHIMS), calls=lacking_calls),
        member=_MEMBER,
    )

    assert _put_args(path=MASTER_HEALTH_WORKFLOW) in _mutating(calls=lacking_calls)


def _contents_args(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _reconciler_shim_row() -> ObligationRow:
    """The registered conformance row, or a failure naming its absence.

    Resolved through `OBLIGATION_ROWS` rather than by importing the asserter
    directly: the row's REGISTRATION is half of what the Definition of Done
    asks for, and an asserter nothing dispatches to reports on no repository.
    """
    registered = [row for row in OBLIGATION_ROWS if row.row_id == _RECONCILER_ROW_ID]

    assert registered, f"no obligation row {_RECONCILER_ROW_ID} is registered"
    return registered[0]


def _row_outcome(*, table: dict[tuple[str, ...], GhResult]) -> RowOutcome:
    return _reconciler_shim_row().assert_member(
        ctx=_make_context(table=table, calls=[]), member=_MEMBER
    )


def test_the_reconciler_shim_row_is_registered_for_every_repository_class() -> None:
    """Every governed member owes this shim, and the row is machine-fixable.

    Scoping is BY CLASS and the class set is every one of them: a red master
    stops ANY member's factory, so there is no class that can opt out. The row
    carries a `reconcile` reference because `wire-fleet-member` can write the
    shim itself — a row with no reconcile would leave the fleet's only install
    path to a `manual_hint`, which charter item 6 forbids.
    """
    row = _reconciler_shim_row()

    assert row.obligation_type == "committed-file"
    assert row.applies_to == ALL_CLASSES
    assert row.reconcile is reconcile_shim_workflows


def test_conformance_convicts_a_member_whose_reconciler_shim_is_missing() -> None:
    """An absent shim is a definitive violation, and the finding names the path."""
    outcome = _row_outcome(table={_TREE_ARGS: _tree(paths=_PIN_AND_BUMP_SHIMS)})

    assert isinstance(outcome, RowFinding)
    assert MASTER_HEALTH_WORKFLOW in outcome.message


def test_conformance_convicts_a_member_whose_reconciler_shim_has_drifted() -> None:
    """A shim PRESENT but edited is the failure presence alone cannot see.

    This is the half that makes the row worth having. A hand-edited shim keeps
    its path, so a presence-only row reads it as conforming while its triggers,
    its `uses:` target or its `secrets: inherit` may all have been changed —
    and a reconciler that is never invoked fails silently, which is the worst
    shape for exactly this mechanism.
    """
    drifted = reconciler_shim_content(owner=_OWNER).replace("*/5 * * * *", "0 * * * *")
    outcome = _row_outcome(
        table={
            _TREE_ARGS: _tree(paths=(*_PIN_AND_BUMP_SHIMS, MASTER_HEALTH_WORKFLOW)),
            _contents_args(path=MASTER_HEALTH_WORKFLOW): GhResult(
                returncode=0, stdout=drifted, stderr=""
            ),
        }
    )

    assert isinstance(outcome, RowFinding)
    assert "drifted" in outcome.message.lower()


def test_conformance_passes_a_member_carrying_the_canonical_shim() -> None:
    """The byte-identical case is the only pass, so the row has no slack."""
    outcome = _row_outcome(
        table={
            _TREE_ARGS: _tree(paths=(*_PIN_AND_BUMP_SHIMS, MASTER_HEALTH_WORKFLOW)),
            _contents_args(path=MASTER_HEALTH_WORKFLOW): GhResult(
                returncode=0, stdout=reconciler_shim_content(owner=_OWNER), stderr=""
            ),
        }
    )

    assert isinstance(outcome, RowPass)


def test_a_shim_present_but_unreadable_skips_rather_than_convicting() -> None:
    """Can't-read is never reported as drift — a token limit must not red the fleet.

    The repository-wide discipline (`livespec-dev-tooling-6ge`): a read this run
    could not perform is a SKIP, because treating unreadable bytes as different
    bytes would convict every member a scoped token cannot see into.
    """
    outcome = _row_outcome(
        table={_TREE_ARGS: _tree(paths=(*_PIN_AND_BUMP_SHIMS, MASTER_HEALTH_WORKFLOW))}
    )

    assert isinstance(outcome, RowSkip)
