"""The incident matrix decision reads foreign JSON only through the strict incident decoder.

Work-item livespec-dev-tooling-hlxbsv. `incident_strict_json.strict_json` is the
one decoder every incident-path read of foreign text uses (the master rule
`test_no_incident_module_decodes_foreign_json_outside_the_strict_decoder`).
Python's `json.loads` lets the LAST spelling of a duplicate key win, so an event
payload that repeats `pull_request` could carry an authorized pull request past
a reader that saw the first. Both foreign reads of the decision, the
`incident-omitted` input and the event payload, now refuse that ambiguity, and
each refusal fails closed: a refused input fails the leg, and a refused payload
authorizes nothing. Each case sits beside its authorized negative control.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_matrix_omission
from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.incident_matrix_call_site import GUARDED_OMITTED, GUARDED_RESULT

__all__: list[str] = []

_REPOSITORY = "owner/repo"
_CALLER_PATH = ".github/workflows/ci.yml"
_CALLER = (
    "jobs:\n  incident-ci:\n    runs-on: ubuntu-latest\n  shared:\n    needs: [incident-ci]\n"
    "    uses: thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@v1\n"
    "    with:\n"
    f"      incident-omitted: {GUARDED_OMITTED}\n      incident-ci-result: {GUARDED_RESULT}\n"
)
_AUTHORIZED_PR = (
    '{"labels": [{"name": "expedited-incident-response"}], '
    '"head": {"repo": {"full_name": "owner/repo"}}, '
    '"base": {"repo": {"full_name": "owner/repo"}, "sha": "' + "b" * 40 + '"}}'
)
_UNLABELED_PR = _AUTHORIZED_PR.replace('{"name": "expedited-incident-response"}', "")


def _run(tmp_path: Path, *, payload: str, raw: str = '["check-heading-coverage"]'):
    """One decision-step run with a payload file of exactly these bytes."""
    workflows = tmp_path / "workspace" / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / "ci.yml").write_text(_CALLER, encoding="utf-8")
    event = tmp_path / "event.json"
    event.write_text(payload, encoding="utf-8")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    code = incident_matrix_omission.main(
        argv=[],
        environ={
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event),
            "GITHUB_REPOSITORY": _REPOSITORY,
            "GITHUB_WORKSPACE": str(workflows.parents[1]),
            "GITHUB_OUTPUT": str(output),
            "CALLER_WORKFLOW_REF": f"{_REPOSITORY}/{_CALLER_PATH}@refs/pull/7/merge",
            "INCIDENT_CI_RESULT": "success",
            "INCIDENT_OMITTED": raw,
            "MATRIX_CHECK": "heading_coverage",
        },
        read=Mock(return_value=GhRead(returncode=0, stdout=_CALLER, stderr="")),
    )
    return code, output.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        '{"pull_request": ' + _UNLABELED_PR + ', "pull_request": ' + _AUTHORIZED_PR + "}",
        '{"pull_request": '
        + _AUTHORIZED_PR.replace('"labels": [', '"labels": [], "labels": [')
        + "}",
        '{"pull_request": ' + _AUTHORIZED_PR + ', "n": NaN}',
        '{"pull_request": ' + _AUTHORIZED_PR + ', "n": 1e999}',
    ],
    ids=["duplicate-pull-request", "duplicate-labels", "nan", "overflowing-exponent"],
)
def test_an_ambiguous_payload_authorizes_nothing(tmp_path, payload):
    facts = [
        _run(tmp_path / "authorized", payload='{"pull_request": ' + _AUTHORIZED_PR + "}")
        == (0, "omit=true\n"),
        _run(tmp_path / "ambiguous", payload=payload) == (0, "omit=false\n"),
    ]
    assert all(facts), facts


@pytest.mark.parametrize(
    "raw",
    ['["check-heading-coverage", ' + '"x", ' * 14000 + '"y"]'],
    ids=["over-the-strict-decoder-bound"],
)
def test_an_input_beyond_the_strict_bound_fails_the_leg(tmp_path, raw):
    facts = [
        len(raw.encode("utf-8")) > 65536,
        _run(tmp_path / "bounded", payload='{"pull_request": ' + _AUTHORIZED_PR + "}")[1]
        == "omit=true\n",
        _run(tmp_path / "unbounded", payload='{"pull_request": ' + _AUTHORIZED_PR + "}", raw=raw)
        == (1, ""),
    ]
    assert all(facts), facts
