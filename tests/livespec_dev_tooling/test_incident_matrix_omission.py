"""A reusable-check-matrix leg omits only an allowlisted member, only on a pull request.

Work-item livespec-dev-tooling-hlxbsv (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm), finding 4 of the independent review of
livespec-dev-tooling#3911. `incident_matrix_omission` is what each leg of
`.github/workflows/reusable-check-matrix.yml` asks before it runs its check.
Each rule is proved here with a negative control beside it:

- only a coverage or spec member can be omitted: a listed `check-lint` runs;
- the input must be a JSON array of strings: a JSON string is refused, so
  `"check-coverage-incremental"` can never omit `check-coverage` by substring;
- a master push (any non-pull_request event) omits nothing and reads nothing;
- a pull request with no incident list omits nothing.

The allowlist itself is compared with what the incident controller defers for
the coverage or spec policy reason over the packaged inventory, so a
classification change fails here by name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling import incident_matrix_omission
from livespec_dev_tooling.incident_ci_inventory import load_inventory
from livespec_dev_tooling.incident_ci_policy import (
    CiAuthority,
    CiEvent,
    CiPlan,
    CiTrust,
    select_ci_plan,
)
from livespec_dev_tooling.incident_execution import (
    ExecutionContext,
    ExecutionMode,
    Invocation,
    OperationIdentity,
)
from livespec_dev_tooling.incident_matrix_omission import (
    OMITTABLE_MEMBERS,
    decide,
    leg_member,
)

__all__: list[str] = []

_PR = "pull_request"
_OMITTING_REASONS = frozenset({"incident-policy:coverage", "incident-policy:spec"})
_ALL_SIX = (
    '["check-check-coverage-incremental", "check-coverage", "check-heading-coverage", '
    '"check-heading-coverage-debt-register", "check-no-todo-registry", '
    '"check-per-file-coverage"]'
)


def _controller_omitted() -> frozenset[str]:
    """What the incident controller defers for coverage or spec on an expedited PR."""
    event = CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=("expedited-incident-response",),
    )
    identity = OperationIdentity(
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        phase="repair",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="repair-op",
    )
    authority = CiAuthority(
        context=ExecutionContext(
            mode=ExecutionMode.EXPEDITED_REPAIR, invocation=Invocation.ORDINARY, identity=identity
        ),
        generation=1,
        owner="operator:alice",
        pr_number=7,
        receipt_digest="d" * 64,
        observer_arm_id="arm-1",
    )
    plan = select_ci_plan(
        event=event,
        targets=load_inventory(),
        authority=authority,
        trust=CiTrust(current=lambda _authority: True, observer=lambda _authority, _event: True),
        environ={},
    )
    assert isinstance(plan, CiPlan)
    return frozenset(d.name for d in plan.deferred if d.reason in _OMITTING_REASONS)


def test_the_allowlist_is_what_the_controller_defers_for_coverage_or_spec():
    controller = _controller_omitted()
    assert controller == OMITTABLE_MEMBERS
    # Negative control: a fast member the controller runs is not omittable.
    assert "check-lint" not in controller
    assert "check-lint" not in OMITTABLE_MEMBERS


@pytest.mark.parametrize(
    ("check", "member"),
    [
        ("heading_coverage", "check-heading-coverage"),
        ("check_coverage_incremental", "check-check-coverage-incremental"),
        ("check-heading-coverage", "check-heading-coverage"),
        ("lint", "check-lint"),
    ],
)
def test_a_leg_slug_names_its_member_in_either_matrix_form(check, member):
    assert leg_member(check=check) == member


@pytest.mark.parametrize(
    "check", ["heading_coverage", "check-heading-coverage", "per_file_coverage"]
)
def test_an_allowlisted_listed_leg_is_omitted_on_a_pull_request(check):
    decision = decide(event_name=_PR, raw=_ALL_SIX, check=check)
    assert (decision.code, decision.omit) == (0, True)
    assert decision.lines[-1].endswith("is omitted-by-incident-policy")
    # Negative control: the same leg is not omitted when the list does not name it.
    unlisted = decide(event_name=_PR, raw='["check-coverage"]', check=check)
    assert (unlisted.code, unlisted.omit) == (0, False)


def test_a_listed_member_outside_the_allowlist_is_refused_and_runs():
    raw = '["check-lint", "check-types", "check-heading-coverage"]'
    lint = decide(event_name=_PR, raw=raw, check="lint")
    assert (lint.code, lint.omit) == (0, False)
    assert lint.lines == (
        "::warning::incident-omission-refused: check-lint is not a coverage or spec member, "
        "so it is never omitted and runs wherever it is a leg",
        "::warning::incident-omission-refused: check-types is not a coverage or spec member, "
        "so it is never omitted and runs wherever it is a leg",
        "incident-omission: lint runs",
    )
    # Negative control: the allowlisted member in the same list is omitted.
    assert decide(event_name=_PR, raw=raw, check="heading_coverage").omit is True


@pytest.mark.parametrize(
    "raw",
    [
        '"check-coverage-incremental"',
        '"check-heading-coverage"',
        '{"check-coverage": true}',
        "7",
        "null",
        "true",
        '["check-coverage", 1]',
        '[["check-coverage"]]',
        "[NaN]",
        "[check-coverage]",
        "[" * 100000,
    ],
)
def test_an_input_that_is_not_a_json_array_of_strings_is_refused(raw):
    decision = decide(event_name=_PR, raw=raw, check="check-coverage")
    assert (decision.code, decision.omit) == (1, False)
    assert decision.lines[0].startswith("::error::incident-omitted-malformed:")
    # Negative control: the same member as a JSON array is a well-formed omission.
    assert decide(event_name=_PR, raw='["check-coverage"]', check="check-coverage").omit is True


def test_a_json_string_is_never_a_substring_test():
    # A JSON string would make GitHub's contains() a substring test.
    assert decide(event_name=_PR, raw='"check-coverage-incremental"', check="coverage").code == 1
    # Negative control: as an array element it matches only itself.
    array = decide(event_name=_PR, raw='["check-coverage-incremental"]', check="coverage")
    assert (array.code, array.omit) == (0, False)


@pytest.mark.parametrize("event_name", ["push", "merge_group", "workflow_dispatch", ""])
@pytest.mark.parametrize("raw", [_ALL_SIX, '"check-coverage"', "{"])
def test_a_master_push_runs_every_check_whatever_the_input(event_name, raw):
    for check in ("heading_coverage", "per_file_coverage", "lint"):
        decision = decide(event_name=event_name, raw=raw, check=check)
        assert (decision.code, decision.omit) == (0, False)
        assert decision.lines[0].endswith("the incident-omitted input is not read")
    # Negative control: the same well-formed input on a pull request omits.
    assert decide(event_name=_PR, raw=_ALL_SIX, check="heading_coverage").omit is True


@pytest.mark.parametrize("raw", ["[]", "", "  "])
def test_a_non_incident_pull_request_omits_nothing(raw):
    for check in ("heading_coverage", "per_file_coverage", "check-coverage", "lint"):
        decision = decide(event_name=_PR, raw=raw, check=check)
        assert (decision.code, decision.omit, decision.lines) == (
            0,
            False,
            (f"incident-omission: {check} runs",),
        )
    # Negative control: a populated list on the same event omits.
    assert decide(event_name=_PR, raw=_ALL_SIX, check="check-coverage").omit is True


def test_main_publishes_the_decision_and_writes_nothing_when_refused(tmp_path: Path, capsys):
    output = tmp_path / "github_output"
    base = {"GITHUB_OUTPUT": str(output), "MATRIX_CHECK": "heading_coverage"}
    omitted = incident_matrix_omission.main(
        environ={**base, "GITHUB_EVENT_NAME": _PR, "INCIDENT_OMITTED": _ALL_SIX}
    )
    ran = incident_matrix_omission.main(
        environ={**base, "GITHUB_EVENT_NAME": "push", "INCIDENT_OMITTED": _ALL_SIX}
    )
    first = capsys.readouterr()
    refused = incident_matrix_omission.main(
        environ={**base, "GITHUB_EVENT_NAME": _PR, "INCIDENT_OMITTED": '"check-heading-coverage"'}
    )
    second = capsys.readouterr()
    assert (omitted, ran, refused) == (0, 0, 1)
    assert output.read_text(encoding="utf-8") == "omit=true\nomit=false\n"
    assert "is omitted-by-incident-policy" in first.out
    assert second.err.startswith("::error::incident-omitted-malformed:")
    assert second.out == ""


def test_main_reads_the_process_environment(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_NAME", _PR)
    monkeypatch.setenv("INCIDENT_OMITTED", "[]")
    monkeypatch.setenv("MATRIX_CHECK", "lint")
    assert incident_matrix_omission.main() == 0
    assert capsys.readouterr().out == "incident-omission: lint runs\n"
