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

import base64
import importlib
import json
import re
from pathlib import Path
from typing import Protocol, cast

from test_reconcile import make_context, ok

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._contract_rows import (
    OBLIGATION_ROWS,
    REPO_CLASSES,
    rows_for,
)
from livespec_dev_tooling.fleet._reconcile_shims import (
    SHIM_BRANCH,
    reconcile_shim_workflows,
)
from livespec_dev_tooling.fleet._reconciler_shim import (
    RECONCILER_WORKFLOW,
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
_FLEET_PACKAGE = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "fleet"
_ROW_ID = "workflow-master-health-reconcile"

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
_RUNS_ON = re.compile(r"^\s*runs-on: (?P<label>\S+)$", re.MULTILINE)
_CALL_SECRET = re.compile(r"^      (?P<secret>[A-Z_]+):")

# The pinned action that mints the fleet App installation token, and the
# expression that proves the minted token is the one the reconcile step
# actually carries. Minting a token and then leaving the step on
# `github.token` is a live failure mode: the workflow looks authenticated and
# behaves as though it is not.
_APP_TOKEN_ACTION = "uses: actions/create-github-app-token@v3"
_MINTED_TOKEN = "${{ steps.app-token.outputs.token }}"


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


class _ReusableReconcilerModule(Protocol):
    """The surface `_reusable_reconciler` publishes to this test module."""

    def reusable_reconciler_workflow(self) -> str: ...


def _reusable() -> str:
    """The canonical reusable reconciler workflow body.

    Resolved through `importlib` behind a genuine assertion on the module's
    PATH, following the sibling `test_charters._charters_module` precedent: a
    top-level import of a module a slice has not written yet dies at COLLECTION
    with zero assertions run, which is a Red that proves only unimportability.
    """
    module_path = _FLEET_PACKAGE / "_reusable_reconciler.py"
    assert module_path.is_file(), (
        "the canonical reusable reconciler workflow body must live in the fleet "
        "package: a factory branch cannot write .github/workflows/, so holding "
        "the bytes here is what keeps their properties assertable before the "
        "workflow file itself lands maintainer-side"
    )
    module = cast(
        "_ReusableReconcilerModule",
        importlib.import_module("livespec_dev_tooling.fleet._reusable_reconciler"),
    )
    return module.reusable_reconciler_workflow()


def _declared_call_secrets(*, source: str) -> dict[str, str]:
    """Each secret the `workflow_call` wire declares, mapped to its own body.

    Scoped to the region between the `workflow_call` secrets key and `jobs:`,
    so a `with:` key elsewhere in the file cannot be mistaken for a declared
    secret.
    """
    region = source.split("\n    secrets:\n", 1)[1].split("\njobs:", 1)[0]
    declared: dict[str, str] = {}
    name = ""
    for line in region.splitlines():
        match = _CALL_SECRET.match(line)
        if match is None:
            declared[name] = f"{declared[name]}{line}\n"
            continue
        name = match.group("secret")
        declared[name] = ""
    return declared


def test_the_reusable_reconciler_runs_on_github_hosted_runners() -> None:
    """Hosted capacity is a CORRECTNESS requirement here, not a cost preference.

    The reconciler exists to heal a red master, and "the self-hosted k3s runner
    pool is down" is one of the failures that reddens one. A reconciler queued
    against the broken pool cannot run at the exact moment it is most needed,
    and the episode then sits red with its own healer stuck in the queue behind
    the outage. Asserted over EVERY `runs-on:` in the file so a later job added
    to this workflow cannot quietly reintroduce the dependency.
    """
    source = _reusable()
    labels = _RUNS_ON.findall(source)

    assert labels, "the reusable reconciler must declare where it runs"
    assert set(labels) == {
        "ubuntu-latest"
    }, f"every job must run on GitHub-hosted capacity; found runs-on={labels}"
    assert "self-hosted" not in source
    assert "CI_RUNNER_LABELS" not in source, (
        "reading the self-hosted routing variable would reintroduce exactly the "
        "pool dependency this workflow is placed outside of"
    )


def test_the_reusable_reconciler_authenticates_with_the_fleet_github_app_token() -> None:
    """`GITHUB_TOKEN` cannot work here, so the App token is load-bearing.

    A pull request created with the default `GITHUB_TOKEN` does NOT trigger
    workflow runs. The reconciler releases a revert on the evidence of the
    revert's OWN CI being green, so under `GITHUB_TOKEN` that CI never starts,
    the evidence never arrives, and the self-healing path stalls on every
    episode — silently, because a revert waiting on a run that will never exist
    looks exactly like a revert waiting on a slow run.
    """
    source = _reusable()

    assert _APP_TOKEN_ACTION in source
    declared = _declared_call_secrets(source=source)
    for secret in ("APP_ID", "APP_PRIVATE_KEY"):
        assert secret in declared, secret
        assert "required: true" in declared[secret], secret
        assert f"secrets.{secret}" in source, secret
    assert _MINTED_TOKEN in source, (
        "the reconcile step must carry the MINTED token; a step left on "
        "`github.token` mints the App token and then does not use it"
    )
    assert "GH_TOKEN: ${{ github.token }}" not in source


def test_the_reusable_reconciler_is_callable_at_the_path_the_shim_names() -> None:
    """The `uses:` path IS the identifier, so the trigger and the wire must agree.

    A reusable workflow that loses its `workflow_call` trigger still EXISTS at
    the path a consumer's `uses:` names, so the reference resolves and then
    fails at run time with nothing in this repository going red.
    """
    assert "\non:\n  workflow_call:\n" in _reusable()
    assert REUSABLE_RECONCILER_WORKFLOW.endswith("/reusable-master-health-reconcile.yml")
    assert f"uses: {_OWNER}/livespec-dev-tooling/{REUSABLE_RECONCILER_WORKFLOW}@" in _shim()


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_REPO = "repos/acme/widget"
_TREE: tuple[str, ...] = ("api", f"{_REPO}/git/trees/master?recursive=1")
_BRANCH_PROBE: tuple[str, ...] = ("api", f"{_REPO}/git/ref/heads/{SHIM_BRANCH}")
_MASTER_REF: tuple[str, ...] = ("api", f"{_REPO}/git/ref/heads/master")
_REFS_POST: tuple[str, ...] = ("api", f"{_REPO}/git/refs", "--method", "POST", "--input", "-")
_PULLS_POST: tuple[str, ...] = ("api", f"{_REPO}/pulls", "--method", "POST", "--input", "-")
_RECEIVING_SHIMS = [BUMP_PIN_WORKFLOW, PIN_FRESHNESS_WORKFLOW, RELEASE_DISPATCH_WORKFLOW]


def _put(*, path: str) -> tuple[str, ...]:
    return ("api", f"{_REPO}/contents/{path}", "--method", "PUT", "--input", "-")


def _shim_table(*, present: list[str]) -> dict[tuple[str, ...], GhResult]:
    """A canned forge for `widget` whose master tree carries exactly `present`.

    Every shim PUT is canned so a missing write shows up as an UNWRITTEN path
    in the recorded calls rather than as a reconcile failure — the two are
    different findings, and only the first is what these assertions are about.
    """
    entries = [{"path": path, "mode": "100644"} for path in present]
    table: dict[tuple[str, ...], GhResult] = {
        _TREE: ok(payload={"tree": entries, "truncated": False}),
        _BRANCH_PROBE: GhResult(returncode=1, stdout="", stderr="Not Found"),
        _MASTER_REF: ok(payload={"object": {"sha": "abc123"}}),
        _REFS_POST: ok(payload={}),
        _PULLS_POST: ok(payload={"number": 11}),
    }
    for path in [*_RECEIVING_SHIMS, RECONCILER_WORKFLOW]:
        table[_put(path=path)] = ok(payload={})
    return table


def _written(*, calls: list[tuple[tuple[str, ...], str | None]], path: str) -> str:
    """The decoded content `calls` wrote to `path`; EMPTY when nothing did.

    Empty-on-absence rather than `None`-on-absence so the helper carries no
    branch of its own. A canonical shim body is never empty, so `assert
    _written(...)` separates "wrote nothing" from "wrote something" without an
    `if` whose other arm only one of these two tests could ever reach — and an
    arm no test reaches is an uncovered line in a helper written to prove
    coverage of someone else's.
    """
    bodies = [stdin for args, stdin in calls if args == _put(path=path) and stdin is not None]
    return "".join(base64.b64decode(json.loads(body)["content"]).decode("utf-8") for body in bodies)


def test_wire_fleet_member_writes_the_canonical_reconciler_shim_when_it_is_missing() -> None:
    """A member lacking the shim gets the canonical bytes, not an approximation.

    Asserted as BYTE EQUALITY against `reconciler_shim_content` rather than as
    a spot-check on a trigger line, because the conformance row that judges the
    installed shim compares against those same bytes: a reconcile that writes
    something merely similar would install a shim its own row then reports as
    drifted, on every member, forever.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    ctx = make_context(table=_shim_table(present=_RECEIVING_SHIMS), calls=calls)

    outcome = reconcile_shim_workflows(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowPass), outcome
    written = _written(calls=calls, path=RECONCILER_WORKFLOW)
    assert written, (
        "wire-fleet-member wrote no reconciler shim at all — the shim is not in "
        "the canonical set the reconcile provisions"
    )
    assert written == reconciler_shim_content(owner="acme")


def test_a_second_wire_run_after_the_shim_landed_leaves_the_member_unchanged() -> None:
    """Idempotency ACROSS runs, which is the property an operator relies on.

    The first run is asserted to have written the shim before the second run's
    silence is read as idempotency: without that guard the second half passes
    just as well against a reconcile that never provisions the shim at all, and
    a vacuous idempotency proof is worse than none because it reads as one.

    Each run gets a FRESH context, so the quiet comes from the forge state the
    first run produced rather than from the per-run once-marker — the marker
    only dedupes within a single wire invocation.
    """
    first_calls: list[tuple[tuple[str, ...], str | None]] = []
    first = reconcile_shim_workflows(
        ctx=make_context(table=_shim_table(present=_RECEIVING_SHIMS), calls=first_calls),
        member=_MEMBER,
    )

    assert isinstance(first, RowPass), first
    assert _written(calls=first_calls, path=RECONCILER_WORKFLOW), (
        "the first run must write the reconciler shim, or the second run's "
        "quiet is proving nothing"
    )

    second_calls: list[tuple[tuple[str, ...], str | None]] = []
    second = reconcile_shim_workflows(
        ctx=make_context(
            table=_shim_table(present=[*_RECEIVING_SHIMS, RECONCILER_WORKFLOW]),
            calls=second_calls,
        ),
        member=_MEMBER,
    )

    assert isinstance(second, RowPass), second
    writes = [args for args, _stdin in second_calls if "--method" in args]
    assert writes == [], f"a second run must leave the repository unchanged; it issued {writes}"


class _ReconcilerRowModule(Protocol):
    """The surface `_rows_reconciler_shim` publishes to this test module."""

    RECONCILER_SHIM_HINT: str

    def assert_reconciler_shim(self, *, ctx: FleetContext, member: FleetMember) -> RowOutcome: ...


def _row_module() -> _ReconcilerRowModule:
    """The obligation-row module, behind a genuine assertion on its path."""
    module_path = _FLEET_PACKAGE / "_rows_reconciler_shim.py"
    assert module_path.is_file(), (
        "the reconciler-shim obligation row must live in its own module beside "
        "the sibling row families"
    )
    return cast(
        "_ReconcilerRowModule",
        importlib.import_module("livespec_dev_tooling.fleet._rows_reconciler_shim"),
    )


def _shim_file(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"{_REPO}/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _row_table(
    *,
    present: list[str],
    body: str | None,
    truncated: bool = False,
) -> dict[tuple[str, ...], GhResult]:
    """A canned forge serving `widget`'s tree and, when `body` is given, the shim."""
    entries = [{"path": path, "mode": "100644"} for path in present]
    table: dict[tuple[str, ...], GhResult] = {
        _TREE: ok(payload={"tree": entries, "truncated": truncated})
    }
    for text in [body] if body is not None else []:
        table[_shim_file(path=RECONCILER_WORKFLOW)] = GhResult(returncode=0, stdout=text, stderr="")
    return table


def _row_outcome(*, table: dict[tuple[str, ...], GhResult]) -> RowOutcome:
    return _row_module().assert_reconciler_shim(
        ctx=make_context(table=table, calls=[]), member=_MEMBER
    )


def test_a_member_missing_the_reconciler_shim_fails_the_conformance_row() -> None:
    """Absence is a FINDING, and the message names the path an operator must fix."""
    outcome = _row_outcome(table=_row_table(present=_RECEIVING_SHIMS, body=None))

    assert isinstance(outcome, RowFinding), outcome
    assert outcome.severity == "error"
    assert RECONCILER_WORKFLOW in outcome.message
    assert "widget" in outcome.message


def test_a_member_whose_reconciler_shim_drifted_fails_the_conformance_row() -> None:
    """A shim that differs from canonical is as broken as one that is absent.

    Presence alone is not the obligation: a shim edited by hand — a dropped
    trigger, a coarsened cron, a redirected `uses:` — still satisfies a
    presence check while reconciling nothing, and that is the failure mode this
    row exists for. The sibling pin-and-bump rows check presence only, so this
    is a deliberate strengthening rather than a copy of them.
    """
    drifted = reconciler_shim_content(owner=_OWNER).replace(
        "- cron: '*/5 * * * *'", "- cron: '0 * * * *'"
    )
    outcome = _row_outcome(
        table=_row_table(present=[*_RECEIVING_SHIMS, RECONCILER_WORKFLOW], body=drifted)
    )

    assert isinstance(outcome, RowFinding), outcome
    assert RECONCILER_WORKFLOW in outcome.message


def test_a_member_carrying_the_canonical_reconciler_shim_passes() -> None:
    outcome = _row_outcome(
        table=_row_table(
            present=[*_RECEIVING_SHIMS, RECONCILER_WORKFLOW],
            body=reconciler_shim_content(owner=_OWNER),
        )
    )

    assert isinstance(outcome, RowPass), outcome


def test_a_shim_whose_pinned_ref_the_bump_automation_rewrote_is_not_drift() -> None:
    """The one difference that is NOT drift, and the fleet depends on it.

    `wire-fleet-member` installs the shim at the bootstrap `@master` ref and
    the bump-pin automation rewrites that ref to a release tag — BY DESIGN, per
    the pin-and-bump contract. A byte-identity comparison would therefore
    report every correctly-wired member as drifted from the moment the first
    pin bump lands: red fleet-wide, for conformance to a ratified mechanism.
    So the comparison normalises the pinned ref away and compares everything
    else exactly.
    """
    bumped = reconciler_shim_content(owner=_OWNER).replace(
        "reconcile.yml@master", "reconcile.yml@v1.97.2"
    )
    assert "@v1.97.2" in bumped, "the fixture must actually carry a bumped ref"

    outcome = _row_outcome(
        table=_row_table(present=[*_RECEIVING_SHIMS, RECONCILER_WORKFLOW], body=bumped)
    )

    assert isinstance(outcome, RowPass), outcome


def test_an_unreadable_tree_skips_rather_than_reporting_the_shim_absent() -> None:
    """Can't-read is never absent — a permission-limited token must not red the fleet."""
    outcome = _row_outcome(table={})

    assert isinstance(outcome, RowSkip), outcome


def test_a_truncated_tree_cannot_prove_the_shim_absent() -> None:
    outcome = _row_outcome(table=_row_table(present=_RECEIVING_SHIMS, body=None, truncated=True))

    assert isinstance(outcome, RowSkip), outcome


def test_a_shim_present_in_the_tree_but_unreadable_skips() -> None:
    """Listed-but-unreadable is a READ failure, not drift.

    Reporting it as drift would put a member's conformance at the mercy of a
    transient contents-API failure, and the remedy an operator would read off
    the finding — rewrite the shim — is not the remedy for a failed read.
    """
    outcome = _row_outcome(
        table=_row_table(present=[*_RECEIVING_SHIMS, RECONCILER_WORKFLOW], body=None)
    )

    assert isinstance(outcome, RowSkip), outcome


def test_the_conformance_row_binds_every_repo_class_and_shares_the_shim_reconcile() -> None:
    """Every fleet repository carries the shim, so the row narrows to nothing.

    It also shares `reconcile_shim_workflows` with the pin-and-bump rows rather
    than carrying a reconcile of its own: the once-marker inside that function
    dedupes per MEMBER, so a second provisioning path would open a second shim
    pull request against the same member in the same wire run.
    """
    for repo_class in REPO_CLASSES:
        row_ids = {row.row_id for row in rows_for(repo_class=repo_class)}
        assert _ROW_ID in row_ids, repo_class

    row = next(row for row in OBLIGATION_ROWS if row.row_id == _ROW_ID)
    assert row.obligation_type == "committed-file"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.reconcile is reconcile_shim_workflows
    assert row.manual_hint == _row_module().RECONCILER_SHIM_HINT
