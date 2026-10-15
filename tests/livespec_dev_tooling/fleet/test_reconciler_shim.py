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

AND THE WORKFLOW'S TWO JOINS WITH THE DECISION CORE ARE ASSERTED AGAINST THE
CORE ITSELF, never against a list restated here. The reusable workflow is the
GATHERER on the far side of the seam `master_health_state` names, so it owes the
decision exactly the recording the decision reads and must perform exactly the
steps the decision can choose. Both obligations are invisible to a YAML linter
and both have already drifted once: child C1's calibration slice
(`livespec-dev-tooling-zdqnr2`) added two configuration fields and two
per-commit fields to the recording and added a sixth step kind
(`STEP_CLOSE_REVERT`), and a gatherer frozen at the older shapes fails CLOSED on
every tick — writing no step, reddening the job, healing nothing — while every
structural assertion about it still passes. So the recorded-state keys are
compared against `dataclasses.fields` of the state vocabulary, and the performed
step kinds against the `STEP_*` constants the decision module exports.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import fields
from pathlib import Path

from _gh_railway import lift_gh

from livespec_dev_tooling.cross_repo import master_health_reconcile
from livespec_dev_tooling.cross_repo.master_health_state import (
    MasterCommit,
    ReconcileConfig,
)
from livespec_dev_tooling.fleet import _reconciler_shim
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
_REPO_ROOT = Path(__file__).resolve().parents[3]

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

_COMMENT_LINE = re.compile(r"^\s*#")
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


def _reusable_workflow_body() -> str:
    """The canonical reusable reconciler workflow body, or a failure naming its absence.

    Resolved through the module object with `getattr` rather than imported at
    module top ON PURPOSE: at the Red moment of this assertion's cycle the name
    does not exist yet, and a top-level import would make that Red a COLLECTION
    error — which proves only unimportability, never that the behaviour is
    unimplemented.
    """
    body = getattr(_reconciler_shim, "REUSABLE_RECONCILER_BODY", None)

    assert isinstance(body, str), (
        "_reconciler_shim carries no REUSABLE_RECONCILER_BODY — the canonical "
        "reusable reconciler workflow body is the artifact this row distributes"
    )
    return body


def _runs_on_values(*, body: str) -> tuple[str, ...]:
    """Every `runs-on:` value in `body`, with comment lines stripped first.

    Comments are stripped because this workflow EXPLAINS at length why
    self-hosted capacity is the wrong place for a reconciler, and a raw
    substring scan would match the explanation. It is the same correctness point
    the shipped `self_hosted_routing` check records about its own parser:
    parsing the structure beats grepping the text.
    """
    return tuple(
        line.split("runs-on:", 1)[1].strip()
        for line in body.splitlines()
        if "runs-on:" in line and not _COMMENT_LINE.match(line)
    )


def test_the_runs_on_reader_ignores_the_workflow_s_own_explanation() -> None:
    """The hosted-runner assertion is only as strong as the reader underneath it."""
    assert _runs_on_values(
        body="# runs-on: local-ci would be wrong here\n    runs-on: ubuntu-latest\n"
    ) == ("ubuntu-latest",)


def test_the_reusable_reconciler_workflow_runs_on_github_hosted_runners() -> None:
    """HOSTED runners, and the requirement is load-bearing rather than a default.

    The k3s pool the fleet's other gating jobs run on can itself BE the failure
    the reconciler is healing, and a reconciler queued against a broken pool
    never runs — at exactly the moment it is needed. Asserting the WHOLE set of
    `runs-on` values rather than the presence of one is what makes a second job
    added later on fleet capacity fail here.
    """
    assert _runs_on_values(body=_reusable_workflow_body()) == ("ubuntu-latest",)


def test_the_reusable_reconciler_workflow_authenticates_with_the_fleet_app_token() -> None:
    """The fleet GitHub App token, not `github.token`, and for two distinct reasons.

    A pull request opened or merged with `GITHUB_TOKEN` does NOT trigger CI, and
    this workflow's whole purpose is to open a revert whose own CI must speak
    before it may land — so with `github.token` the revert would sit forever
    with no verdict. The App installation token also carries the admin-level
    access the auto-merge mutation needs, which `github-actions[bot]` lacks
    regardless of declared `permissions:` (the finding `auto-enable-merge.yml`
    records).
    """
    body = _reusable_workflow_body()

    assert "actions/create-github-app-token@v3" in body
    assert "client-id: ${{ secrets.APP_ID }}" in body
    assert "private-key: ${{ secrets.APP_PRIVATE_KEY }}" in body
    assert "GH_TOKEN: ${{ steps.app-token.outputs.token }}" in body
    assert "${{ github.token }}" not in body


def test_the_reusable_reconciler_workflow_delegates_every_decision_to_the_pure_core() -> None:
    """The workflow gathers and performs; it decides nothing.

    `master_health_state`'s docstring puts the gathering here and the decision
    in the pure modules, so the workflow must reach the step through the
    adapter rather than branching on forge state itself. It is `workflow_call`
    only — the shim owns the triggers.
    """
    body = _reusable_workflow_body()

    assert "workflow_call:" in body
    assert "python3 -m livespec_dev_tooling.cross_repo.master_health_step" in body
    assert "--state" in body
    assert "--step-out" in body


def _committed_matches(*, path: Path, canonical: str) -> bool | None:
    """Whether `path` holds `canonical`; None when `path` does not exist."""
    return path.read_text(encoding="utf-8") == canonical if path.is_file() else None


def test_the_committed_reusable_workflow_is_byte_identical_to_the_canonical_body(
    *, tmp_path: Path
) -> None:
    """The join that stops the Python source of truth and the committed file drifting.

    The body is authored in Python because a FACTORY branch may not create or
    modify anything under `.github/workflows/` — the dispatch credential carries
    no `workflows` grant and `check-no-workflow-edits` enforces the boundary — so
    the committed workflow lands maintainer-side from that text.

    The comparator is therefore proven against files that DO exist (an identical
    one and an edited one) and then applied to the committed path, where
    `is not False` is the real gate: absent is the boundary's own state and
    passes, DIFFERENT fails from the moment a copy lands.
    """
    canonical = _reusable_workflow_body()
    landed = tmp_path / "landed.yml"
    _ = landed.write_text(canonical, encoding="utf-8")
    drifted = tmp_path / "drifted.yml"
    _ = drifted.write_text(f"{canonical}# a hand edit\n", encoding="utf-8")

    assert _committed_matches(path=landed, canonical=canonical) is True
    assert _committed_matches(path=drifted, canonical=canonical) is False
    assert (
        _committed_matches(path=_REPO_ROOT / REUSABLE_RECONCILER_WORKFLOW, canonical=canonical)
        is not False
    )


def _recorded_state_keys(*, body: str) -> frozenset[str]:
    """Every key the workflow's recording step writes into `state.json`.

    Read off the ONE `jq -n` program that composes the recording, not off the
    whole body: the per-read `gh api --jq` filters above it build intermediate
    files whose keys are that read's vocabulary rather than the recording's, and
    scanning them too would report a union nothing ever wrote.
    """
    program = body.partition("jq -n ")[2].partition("> state.json")[0]
    return frozenset(re.findall(r"(?m)^\s*(\w+):", program))


def _performed_step_kinds(*, body: str) -> frozenset[str]:
    """Every step kind the workflow's `case` dispatches on, excluding its default.

    The `*)` arm is deliberately NOT collected. It is the arm that reds the job
    on a kind this workflow does not recognise, so counting it would let it
    stand in for the coverage this reader exists to measure.
    """
    dispatch = body.partition('case "${kind}" in')[2].partition("esac")[0]
    return frozenset(re.findall(r"(?m)^\s*([a-z][a-z-]*)\)$", dispatch))


def test_the_recording_and_dispatch_readers_see_only_their_own_region() -> None:
    """Both join assertions are only as strong as the readers underneath them.

    The recording reader must not pick up an intermediate read's keys, and the
    dispatch reader must not count the default arm — proven here on samples
    carrying exactly those traps, so a vacuous frozenset cannot masquerade as
    agreement with the core below.
    """
    body = (
        "gh api x --jq '{ decoy: .y }' > runs.json\n"
        "jq -n '{\n  target_branch: $branch,\n  commits: [ $c[] | {\n"
        "    sha: .sha\n  } ]\n}' > state.json\n"
    )

    assert _recorded_state_keys(body=body) == frozenset({"target_branch", "commits", "sha"})

    dispatch = 'case "${kind}" in\n  none)\n    :\n    ;;\n  *)\n    exit 1\n    ;;\nesac\n'

    assert _performed_step_kinds(body=dispatch) == frozenset({"none"})


def test_the_recording_carries_exactly_what_the_decision_reads() -> None:
    """The gatherer's output shape IS the decision's input shape, field for field.

    This is the assertion the drift of `livespec-dev-tooling-zdqnr2` needed and
    did not have. A recording short one field fails CLOSED in the adapter — no
    step written, the job red, nothing healed — and a recording carrying a field
    the decision retired is a read nobody consumes. Both are silent in YAML and
    both are caught here, because the expected set is projected from
    `ReconcileConfig` and `MasterCommit` rather than restated.

    The two names that are NOT dataclass fields are the recording's own
    vocabulary and are listed for that reason: the issue TITLES travel (the
    adapter owns the title convention, so it derives
    `open_needs_attention_episodes` from them), and `revert_pull_request` is
    recorded as a whole object whose own keys the adapter parses separately.
    """
    expected = (
        {field.name for field in fields(ReconcileConfig)}
        | {field.name for field in fields(MasterCommit)}
        | {"head_sha", "rerun_outcome", "commits", "revert_pull_request"}
        | {"needs_attention_issue_titles"}
    )

    assert _recorded_state_keys(body=_reusable_workflow_body()) == expected


def test_the_workflow_performs_every_step_the_decision_can_choose() -> None:
    """Every `STEP_*` the core can answer has an arm, and no arm is orphaned.

    A step kind with no arm falls to the default and reds the job on a decision
    the reconciler reached correctly — which is how `STEP_CLOSE_REVERT`, the
    ending 25% of measured episodes take, would have turned the commonest happy
    path into a failing workflow. Equality rather than containment, so an arm
    for a kind the core no longer emits fails here too.
    """
    kinds = {
        value
        for name, value in vars(master_health_reconcile).items()
        if name.startswith("STEP_") and isinstance(value, str)
    }

    assert kinds, "no STEP_* constants found — the comparison would pass vacuously"
    assert _performed_step_kinds(body=_reusable_workflow_body()) == kinds


def test_the_revert_step_carries_the_hold_rebump_label_the_decision_computed() -> None:
    """A reverted pin bump must hold the bump shim, or the pin comes straight back.

    `hold_rebump_label` is `None` for every culprit that is not a pin bump, so
    the workflow reads one field rather than re-deriving the rule: the label is
    the JOIN with the bump shim that must honour it, and a revert opened without
    it is re-bumped on the next freshness tick.
    """
    body = _reusable_workflow_body()

    assert "hold_rebump_label" in body
