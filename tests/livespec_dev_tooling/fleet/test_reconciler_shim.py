"""Tests for the canonical master-health reconciler shim and the workflow it calls.

This module owns the in-repo-gradeable acceptance assertions of child D of plan
`red-master-self-healing` (work-item `livespec-dev-tooling-dw7dzd`, epic
`livespec-dev-tooling-zcp5vb`): the shim's trigger set, the renderer's
byte-stability, the install `wire-fleet-member` performs and its idempotence,
and the reusable workflow's hosted-runner + fleet-App-token shape.

THE TRIGGER ASSERTIONS ARE WRITTEN AS PROPERTIES, NOT AS LITERALS, wherever the
Definition of Done states a property. "A schedule no coarser than five minutes"
is asserted by PARSING the cron minute field and comparing the interval, so a
later edit to `*/10` fails here rather than passing a substring match that only
ever proved the line was present.

AND THE INSTALL IS DRIVEN THROUGH `reconcile_member` — `wire-fleet-member`'s own
engine — rather than through the shared shim reconcile it delegates to. The
Definition of Done states its install assertions about `wire-fleet-member`, and
this provisioning deliberately carries NO fleet conformance row: with the three
pin-and-bump shim rows passing, nothing in the obligation table fires at all, so
a pull request can only come from the step the engine performs itself. Testing
the delegate directly would pass whether or not that step is wired.
"""

from __future__ import annotations

import base64
import json
import re
from typing import TYPE_CHECKING

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
)
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS
from livespec_dev_tooling.fleet._reconcile_shims import SHIM_BRANCH, shim_content
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
from livespec_dev_tooling.fleet.wire_fleet_member import reconcile_member

if TYPE_CHECKING:
    import pytest
    import structlog.stdlib

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


def _contents_args(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


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
    """A call-recording `FleetContext` for owner `acme`.

    The `gh` seam is the only one injected, and the DOWNLOAD seam deliberately
    is not, which matters because the tests below drive `reconcile_member` over
    the whole obligation table. Exactly one row reads a member's tree SNAPSHOT
    (`cross-repo-public-api-declared`), and it skips on an EMPTY roster before
    any download is attempted — `FleetContext.members` defaults to `()` for that
    stated reason, so the default downloader is unreachable here rather than
    merely unused, and these tests never touch the network.
    """

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        key = tuple(args)
        calls.append((key, stdin))
        return table.get(key, GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner=_OWNER, run_gh=lift_gh(runner))


def _wire_log() -> structlog.stdlib.BoundLogger:
    import structlog

    return structlog.get_logger("test_reconciler_shim")


def _mutating(*, calls: list[tuple[tuple[str, ...], str | None]]) -> list[tuple[str, ...]]:
    """The argv of every recorded call that would CHANGE the member repository."""
    return [args for args, _stdin in calls if "--method" in args]


def _opened_pull_requests(
    *, calls: list[tuple[tuple[str, ...], str | None]]
) -> list[tuple[str, ...]]:
    """Every `POST .../pulls` the run issued — i.e. every pull request it opened.

    `_reconcile_shims._open_shim_pr` is the ONLY `POST` to a member's `pulls`
    anywhere on the fleet surface, so counting these counts pull requests, which
    is the unit the Definition of Done states ("opens exactly one pull
    request" / "opens no pull request").
    """
    return [args for args in _mutating(calls=calls) if args == _PULLS_POST]


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


def _committed(*, text: str) -> GhResult:
    """The member's committed shim bytes, as the raw contents API returns them."""
    return GhResult(returncode=0, stdout=text, stderr="")


def test_the_install_and_the_drift_read_render_the_canonical_shim_identically() -> None:
    """Rendering the shim twice from the same inputs yields byte-identical content.

    Asserted ACROSS THE TWO RENDERERS that exist rather than by calling one of
    them twice, because that is where the property can actually break and a pure
    function called twice could never fail. `wire-fleet-member` renders through
    `shim_content` when it WRITES the shim and through `reconciler_shim_content`
    when it READS a committed one back to judge drift; the moment those two
    disagree by a byte, every member the install just wired reads as DRIFTED and
    the mechanism accuses itself. One template, one rendering, both paths.
    """
    ctx = _make_context(table={}, calls=[])

    installed = shim_content(path=MASTER_HEALTH_WORKFLOW, ctx=ctx, member=_MEMBER)

    assert installed == reconciler_shim_content(owner=_OWNER)
    assert installed == shim_content(path=MASTER_HEALTH_WORKFLOW, ctx=ctx, member=_MEMBER)
    # Not vacuous: an empty or un-substituted body would satisfy equality alone.
    assert _OWNER in installed
    assert REUSABLE_RECONCILER_WORKFLOW in installed


def test_wire_fleet_member_opens_one_pull_request_for_a_member_lacking_the_shim() -> None:
    """The install leg, driven through `wire-fleet-member`'s own engine.

    The member already carries every OTHER shim, which is what makes this a
    statement about the RECONCILER shim rather than about shim provisioning in
    general: the three pin-and-bump rows pass, so nothing in the obligation table
    fires, and the pull request can only come from the step the engine performs
    itself.

    `wire-fleet-member` is the ONLY path by which the shim reaches a fleet
    repository (plan charter item 6 — never configured by hand), so the bytes it
    PUTs must be the canonical body verbatim rather than anything rendered a
    second way. The PUT content is decoded and compared whole for that reason.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    ctx = _make_context(table=_install_table(present=_PIN_AND_BUMP_SHIMS), calls=calls)

    _ = reconcile_member(ctx=ctx, member=_MEMBER, log=_wire_log())

    assert len(_opened_pull_requests(calls=calls)) == 1
    put_body = next(
        stdin for args, stdin in calls if args == _put_args(path=MASTER_HEALTH_WORKFLOW)
    )
    assert put_body is not None
    decoded = base64.b64decode(json.loads(put_body)["content"]).decode("utf-8")
    assert decoded == reconciler_shim_content(owner=_OWNER)


def test_wire_fleet_member_opens_no_pull_request_for_a_member_already_carrying_it(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """The idempotence leg: a second run over the repository the first one produced.

    Nothing is created, nothing is written, and no pull request is opened — the
    Definition of Done's "opens no pull request", which for a member wired by an
    earlier run is also "a second run leaves the repository unchanged".

    The REPORTED verdict is what stops that being VACUOUS, and it has to be the
    verdict rather than the read: a step that was never wired in satisfies every
    negative clause above trivially, and the committed shim's bytes are read by
    the pin-currency row too (it materializes every `.github/workflows/*.yml` a
    member carries), so observing the read would not discriminate either. The
    engine must SAY it found the canonical shim.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = _install_table(present=(*_PIN_AND_BUMP_SHIMS, MASTER_HEALTH_WORKFLOW))
    table[_contents_args(path=MASTER_HEALTH_WORKFLOW)] = _committed(
        text=reconciler_shim_content(owner=_OWNER)
    )

    _ = reconcile_member(
        ctx=_make_context(table=table, calls=calls), member=_MEMBER, log=_wire_log()
    )

    assert "is the canonical reconciler shim" in "".join(capsys.readouterr())
    assert _opened_pull_requests(calls=calls) == []
    assert _put_args(path=MASTER_HEALTH_WORKFLOW) not in _mutating(calls=calls)
    assert _REFS_POST not in _mutating(calls=calls)


def test_wire_fleet_member_reports_a_drifted_shim_rather_than_overwriting_it(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """A shim PRESENT but edited is the failure presence alone cannot see.

    This is the half that makes the discovery worth having. A hand-edited shim
    keeps its path, so a presence-only read takes it for conforming while its
    triggers, its `uses:` target or its `secrets: inherit` may all have been
    changed — and a reconciler that is never invoked fails SILENTLY, which is
    the worst shape for exactly this mechanism: it goes quiet at the moment a
    master is red.

    REPORTED, not repaired. Overwriting a file a repository has committed is a
    wider decision than this item takes, and the remedy the message names —
    delete the file, re-run the wire — reaches the same end through the install
    path that already exists.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = _install_table(present=(*_PIN_AND_BUMP_SHIMS, MASTER_HEALTH_WORKFLOW))
    drifted = reconciler_shim_content(owner=_OWNER).replace("*/5 * * * *", "0 * * * *")
    table[_contents_args(path=MASTER_HEALTH_WORKFLOW)] = _committed(text=drifted)

    _ = reconcile_member(
        ctx=_make_context(table=table, calls=calls), member=_MEMBER, log=_wire_log()
    )

    reported = "".join(capsys.readouterr())
    assert "has DRIFTED from the canonical" in reported
    assert "re-running wire-fleet-member" in reported
    assert _opened_pull_requests(calls=calls) == []
    assert _put_args(path=MASTER_HEALTH_WORKFLOW) not in _mutating(calls=calls)


def test_a_shim_present_but_unreadable_is_not_reported_as_drift(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """Can't-read is never reported as different — the `livespec-dev-tooling-6ge` rule.

    Treating bytes this run could not read as bytes that DIFFER would accuse
    every member a scoped token cannot see into, for a condition that is a fact
    about the token rather than about the repository. The paired clause is what
    makes the negative one mean something: the path must still be NAMED as
    unreadable, so a step that silently did nothing at all cannot pass here.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = _install_table(present=(*_PIN_AND_BUMP_SHIMS, MASTER_HEALTH_WORKFLOW))

    _ = reconcile_member(
        ctx=_make_context(table=table, calls=calls), member=_MEMBER, log=_wire_log()
    )

    reported = "".join(capsys.readouterr())
    assert "DRIFTED" not in reported
    assert f"{MASTER_HEALTH_WORKFLOW} unreadable" in reported
    assert _opened_pull_requests(calls=calls) == []


def test_the_reconciler_shim_carries_no_fleet_conformance_obligation_row() -> None:
    """The provisioning is wire-fleet-member's own step, and that is a DECISION.

    A `workflow-master-health-reconcile` obligation row convicting a missing
    shim is correct only once every member carries one. Registered before that,
    it reds the central lane for the whole fleet — and the FIRST repository it
    reds is this one, whose own `check-fleet-conformance --member-ci` leg reads
    its own rows. Measured on draft pull request #2477, where `own_failing_rows`
    was exactly that row against ten members including this repository.

    Enforcement is a separate child of plan `red-master-self-healing`; this item
    is provisioning only. The assertion is kept so re-registering the row is a
    deliberate act with a failing test in front of it rather than an accident.
    """
    assert [row.row_id for row in OBLIGATION_ROWS if "master-health" in row.row_id] == []
