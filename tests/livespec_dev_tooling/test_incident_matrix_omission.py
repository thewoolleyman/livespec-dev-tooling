"""A reusable-check-matrix leg omits only an allowlisted member, only on a pull request.

Work-item livespec-dev-tooling-hlxbsv (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm), finding 4 of the independent review of
livespec-dev-tooling#3911. `incident_matrix_omission` is what each leg of
`.github/workflows/reusable-check-matrix.yml` asks before it runs its check.
Each rule is proved here with a negative control beside it:

- only a coverage or spec member can be omitted: a listed `check-lint` runs;
- the input must be a JSON array of strings: a JSON string is refused, so
  `"check-coverage-incremental"` can never omit `check-coverage` by substring;
- a master push (any non-pull_request event, pull_request_target included)
  omits nothing and reads nothing;
- a pull request with no incident list omits nothing;
- only an authorized incident omits: the caller's incident-ci result is
  `success`, the payload's pull request carries the incident label and comes
  from this repository, and the caller wires both inputs only from incident-ci;
- only a module slug run-check can run is omitted, and every caller value is
  JSON-quoted before it is printed.

The allowlist itself is compared with what the incident controller defers for
the coverage or spec policy reason over the packaged inventory, so a
classification change fails here by name.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
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
    GUARDED_OMITTED,
    GUARDED_RESULT,
    OMITTABLE_MEMBERS,
    IncidentAuthority,
    caller_wiring_findings,
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


_REPOSITORY = "owner/repo"
_CALLER = (
    f"      incident-omitted: {GUARDED_OMITTED}\n" f"      incident-ci-result: {GUARDED_RESULT}\n"
)
_PAYLOAD = {
    "pull_request": {
        "labels": [{"name": "question"}, {"name": "expedited-incident-response"}],
        "head": {"repo": {"full_name": _REPOSITORY}},
        "base": {"repo": {"full_name": _REPOSITORY}},
    }
}
_AUTHORIZED = IncidentAuthority(
    payload=_PAYLOAD,
    repository=_REPOSITORY,
    incident_ci_result="success",
    workflows=(("ci.yml", _CALLER),),
)


def _decide(*, event_name=_PR, raw=_ALL_SIX, check="heading_coverage", authority=_AUTHORIZED):
    return decide(event_name=event_name, raw=raw, check=check, authority=authority)


def _pull_request(**fields):
    return {"pull_request": {**_PAYLOAD["pull_request"], **fields}}


@pytest.mark.parametrize(
    ("check", "member"),
    [
        ("heading_coverage", "check-heading-coverage"),
        ("check_coverage_incremental", "check-check-coverage-incremental"),
        ("coverage", "check-coverage"),
        ("lint", "check-lint"),
        ("check-heading-coverage", None),
        ("Heading_coverage", None),
        ("heading_coverage\n", None),
        ("", None),
    ],
)
def test_only_a_module_slug_run_check_can_run_names_a_member(check, member):
    assert leg_member(check=check) == member


@pytest.mark.parametrize("check", ["heading_coverage", "per_file_coverage", "coverage"])
def test_an_allowlisted_listed_leg_is_omitted_and_annotated(check):
    decision = _decide(check=check)
    assert (decision.code, decision.omit) == (0, True)
    assert decision.lines == (
        f"::notice title=omitted-by-incident-policy::\"{check}\" (check-{check.replace('_', '-')})"
        " was not executed; the caller's passed incident CI aggregate defers it for this pull "
        "request",
    )
    # Negative control: the same leg is not omitted when the list does not name it.
    unlisted = _decide(raw='["check-no-todo-registry"]', check=check)
    assert (unlisted.code, unlisted.omit) == (0, False)


def test_a_listed_member_outside_the_allowlist_is_refused_and_runs():
    raw = '["check-lint", "check-types", "check-heading-coverage"]'
    lint = _decide(raw=raw, check="lint")
    assert (lint.code, lint.omit) == (0, False)
    assert lint.lines == (
        '::warning::incident-omission-refused: "check-lint" is not a coverage or spec member, '
        "so it is never omitted and runs wherever it is a leg",
        '::warning::incident-omission-refused: "check-types" is not a coverage or spec member, '
        "so it is never omitted and runs wherever it is a leg",
        'incident-omission: "lint" runs',
    )
    # Negative control: the allowlisted member in the same list is omitted.
    assert _decide(raw=raw, check="heading_coverage").omit is True


def test_a_kebab_slug_is_refused_and_never_omitted():
    decision = _decide(check="check-heading-coverage")
    assert (decision.code, decision.omit) == (0, False)
    assert decision.lines == (
        '::warning::incident-omission-refused-leg: "check-heading-coverage" is not a module '
        "slug run-check can run, so it is never omitted",
        'incident-omission: "check-heading-coverage" runs',
    )
    # Negative control: its module slug is omitted.
    assert _decide(check="heading_coverage").omit is True


def test_every_caller_value_is_quoted_so_no_newline_reaches_the_log():
    raw = json.dumps(["x\n::error title=spoof::y%0A", "check-heading-coverage"])
    decision = _decide(raw=raw, check="lint\n::error::z")
    printed = "\n".join(decision.lines)
    assert decision.omit is False
    assert len(printed.splitlines()) == len(decision.lines) == 3
    assert not any(line.startswith("::error") for line in printed.splitlines())
    assert decision.lines[-1] == 'incident-omission: "lint\\n::error::z" runs'
    assert '"x\\n::error title=spoof::y%250A"' in printed
    # Negative control: a plain name prints as itself, quoted.
    assert '"check-lint"' in _decide(raw='["check-lint"]', check="lint").lines[0]


@pytest.mark.parametrize(
    ("authority", "reason"),
    [
        (replace(_AUTHORIZED, incident_ci_result="failure"), 'incident-ci result is "failure"'),
        (replace(_AUTHORIZED, incident_ci_result=""), 'incident-ci result is ""'),
        (replace(_AUTHORIZED, payload=None), "does not carry the expedited-incident-response"),
        (replace(_AUTHORIZED, payload={"pull_request": "x"}), "does not carry the expedited"),
        (replace(_AUTHORIZED, payload=_pull_request(labels="x")), "does not carry the expedited"),
        (
            replace(_AUTHORIZED, payload=_pull_request(labels=[{"name": "question"}, "x"])),
            "does not carry the expedited",
        ),
        (
            replace(_AUTHORIZED, payload=_pull_request(head={"repo": {"full_name": "fork/repo"}})),
            'head repository is not "owner/repo"',
        ),
        (
            replace(_AUTHORIZED, payload=_pull_request(head={"repo": None})),
            'head repository is not "owner/repo"',
        ),
        (
            replace(_AUTHORIZED, payload=_pull_request(base={"repo": {"full_name": "other/x"}})),
            'head repository is not "owner/repo"',
        ),
        (replace(_AUTHORIZED, repository="other/repo"), 'head repository is not "other/repo"'),
        (
            replace(
                _AUTHORIZED,
                repository="",
                payload=_pull_request(
                    head={"repo": {"full_name": ""}}, base={"repo": {"full_name": ""}}
                ),
            ),
            'head repository is not ""',
        ),
        (replace(_AUTHORIZED, workflows=()), "do not wire incident-omitted only from incident-ci"),
        (
            replace(_AUTHORIZED, workflows=(("ci.yml", "      incident-omitted: '[]'\n"),)),
            "do not wire incident-omitted only from incident-ci",
        ),
        (
            replace(
                _AUTHORIZED,
                workflows=(("ci.yml", _CALLER), ("x.yml", "  incident-ci-result: success\n")),
            ),
            "do not wire incident-omitted only from incident-ci",
        ),
    ],
)
def test_an_unauthorized_requested_omission_is_refused_and_runs(authority, reason):
    decision = _decide(authority=authority)
    assert (decision.code, decision.omit) == (0, False)
    assert decision.lines[0].startswith("::warning::incident-omission-unauthorized: ")
    assert reason in decision.lines[0]
    assert decision.lines[-1] == 'incident-omission: "heading_coverage" runs'
    # Negative control: the authorized incident omits the same leg.
    assert _decide().omit is True


def test_an_unrequested_leg_never_consults_the_authority():
    decision = _decide(
        raw='["check-no-todo-registry"]', authority=replace(_AUTHORIZED, payload=None)
    )
    assert decision.lines == ('incident-omission: "heading_coverage" runs',)


@pytest.mark.parametrize(
    "line",
    [
        f"      incident-omitted: {GUARDED_OMITTED}",
        f"      incident-omitted: '{GUARDED_OMITTED}'",
        f'      incident-omitted: "{GUARDED_OMITTED}"',
        f"      incident-ci-result: {GUARDED_RESULT}",
        "      incident-omitted:",
        "      incident-ci-result:",
        "#     incident-omitted: '[\"check-coverage\"]'",
        "        INCIDENT_OMITTED: ${{ inputs.incident-omitted }}",
    ],
)
def test_the_guarded_wiring_and_declarations_are_not_findings(line):
    assert caller_wiring_findings(workflows=(("ci.yml", line),)) == []


@pytest.mark.parametrize(
    "line",
    [
        "      incident-omitted: '[\"check-coverage\"]'",
        "      incident-omitted: ${{ vars.OMITTED }}",
        "      incident-omitted: ${{ needs.incident-ci.outputs.omitted }}",
        "      incident-omitted: >-",
        "      incident-omitted: '",
        "      incident-ci-result: success",
        "      incident-ci-result: ${{ vars.RESULT }}",
        f"    with: {{incident-omitted: {GUARDED_OMITTED}}}",
    ],
)
def test_any_other_wiring_is_a_finding(line):
    findings = caller_wiring_findings(workflows=(("ci.yml", "jobs:\n" + line),))
    assert len(findings) == 1
    assert findings[0].startswith("ci.yml:2: incident-")
    assert "is not wired from the incident-ci job's guarded output" in findings[0]


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
    decision = _decide(raw=raw, check="coverage")
    assert (decision.code, decision.omit) == (1, False)
    assert decision.lines[0].startswith("::error::incident-omitted-malformed:")
    # Negative control: the same member as a JSON array is a well-formed omission.
    assert _decide(raw='["check-coverage"]', check="coverage").omit is True


def test_a_json_string_is_never_a_substring_test():
    # A JSON string would make GitHub's contains() a substring test.
    assert _decide(raw='"check-coverage-incremental"', check="coverage").code == 1
    # Negative control: as an array element it matches only itself.
    array = _decide(raw='["check-coverage-incremental"]', check="coverage")
    assert (array.code, array.omit) == (0, False)


@pytest.mark.parametrize(
    "event_name", ["push", "merge_group", "workflow_dispatch", "pull_request_target", ""]
)
@pytest.mark.parametrize("raw", [_ALL_SIX, '"check-coverage"', "{"])
def test_a_master_push_runs_every_check_whatever_the_input(event_name, raw):
    for check in ("heading_coverage", "per_file_coverage", "lint"):
        decision = _decide(event_name=event_name, raw=raw, check=check)
        assert (decision.code, decision.omit) == (0, False)
        assert decision.lines == (
            f'incident-omission: "{event_name}" event; "{check}" runs, and the '
            "incident-omitted input is not read",
        )
    # Negative control: the same well-formed input on a pull request omits.
    assert _decide().omit is True


@pytest.mark.parametrize("raw", ["[]", "", "  "])
def test_a_non_incident_pull_request_omits_nothing(raw):
    for check in ("heading_coverage", "per_file_coverage", "check-coverage", "lint"):
        decision = _decide(raw=raw, check=check)
        assert (decision.code, decision.omit, decision.lines) == (
            0,
            False,
            (f'incident-omission: "{check}" runs',),
        )
    # Negative control: a populated list on the same event omits.
    assert _decide(check="coverage").omit is True


def _workspace(tmp_path: Path) -> Path:
    workflows = tmp_path / "workspace" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    _ = (workflows / "ci.yml").write_text("jobs:\n" + _CALLER, encoding="utf-8")
    _ = (workflows / "notes.txt").write_text("incident-omitted: '[]'\n", encoding="utf-8")
    return workflows.parents[1]


def test_main_publishes_the_decision_and_writes_nothing_when_refused(tmp_path: Path, capsys):
    output = tmp_path / "github_output"
    event = tmp_path / "event.json"
    _ = event.write_text(json.dumps(_PAYLOAD), encoding="utf-8")
    base = {
        "GITHUB_OUTPUT": str(output),
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_REPOSITORY": _REPOSITORY,
        "GITHUB_WORKSPACE": str(_workspace(tmp_path)),
        "INCIDENT_CI_RESULT": "success",
        "MATRIX_CHECK": "heading_coverage",
    }
    omitted = incident_matrix_omission.main(
        argv=[], environ={**base, "GITHUB_EVENT_NAME": _PR, "INCIDENT_OMITTED": _ALL_SIX}
    )
    ran = incident_matrix_omission.main(
        argv=[], environ={**base, "GITHUB_EVENT_NAME": "push", "INCIDENT_OMITTED": _ALL_SIX}
    )
    first = capsys.readouterr()
    refused = incident_matrix_omission.main(
        argv=[],
        environ={**base, "GITHUB_EVENT_NAME": _PR, "INCIDENT_OMITTED": '"check-heading-coverage"'},
    )
    second = capsys.readouterr()
    assert (omitted, ran, refused) == (0, 0, 1)
    assert output.read_text(encoding="utf-8") == "omit=true\nomit=false\n"
    assert first.out.startswith("::notice title=omitted-by-incident-policy::")
    assert second.err.startswith("::error::incident-omitted-malformed:")
    assert second.out == ""


@pytest.mark.parametrize("event", ["", "missing.json", "bad.json"])
def test_an_unreadable_payload_or_workspace_authorizes_nothing(tmp_path: Path, capsys, event):
    _ = (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    code = incident_matrix_omission.main(
        argv=[],
        environ={
            "GITHUB_EVENT_NAME": _PR,
            "GITHUB_EVENT_PATH": str(tmp_path / event) if event else "",
            "GITHUB_REPOSITORY": _REPOSITORY,
            "INCIDENT_CI_RESULT": "success",
            "INCIDENT_OMITTED": _ALL_SIX,
            "MATRIX_CHECK": "heading_coverage",
        },
    )
    assert code == 0
    assert "::warning::incident-omission-unauthorized:" in capsys.readouterr().out


def test_main_reads_the_process_environment(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_NAME", _PR)
    monkeypatch.setenv("INCIDENT_OMITTED", "[]")
    monkeypatch.setenv("MATRIX_CHECK", "lint")
    monkeypatch.setattr(sys, "argv", ["incident_matrix_omission"])
    assert incident_matrix_omission.main() == 0
    assert capsys.readouterr().out == 'incident-omission: "lint" runs\n'


def test_check_callers_scans_the_workflows_directory_by_default(tmp_path, monkeypatch, capsys):
    workspace = _workspace(tmp_path)
    monkeypatch.chdir(workspace)
    assert incident_matrix_omission.main(argv=["--check-callers"]) == 0
    _ = (workspace / ".github" / "workflows" / "bad.yaml").write_text(
        "  incident-omitted: ${{ vars.OMITTED }}\n", encoding="utf-8"
    )
    assert incident_matrix_omission.main(argv=["--check-callers"]) == 1
    assert "bad.yaml:1: incident-omitted is not wired" in capsys.readouterr().err


def test_this_repository_wires_no_caller_but_incident_ci(capsys):
    root = Path(__file__).resolve().parents[2] / ".github" / "workflows"
    paths = sorted(str(p) for p in root.glob("*.yml"))
    assert incident_matrix_omission.main(argv=["--check-callers", *paths]) == 0
    assert capsys.readouterr().err == ""
