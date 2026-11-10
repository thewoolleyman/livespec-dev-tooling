"""A reusable-check-matrix leg omits only for an authorized incident, and says so.

Work-item livespec-dev-tooling-hlxbsv, the independent review of
livespec-dev-tooling#3966 (issuecomment-6757586369). Driven end to end through
the module's process entry point, `main()`, with the runner's environment, the
event payload file and the caller's workflow files on disk, exactly as the
reusable workflow's decision step runs it:

- F1: an omission needs the caller's `incident-ci` result `success`, the
  `expedited-incident-response` label on the event payload's pull request, a
  head repository equal to this repository (a fork omits nothing), and caller
  workflows that wire both inputs only from `incident-ci`'s guarded output;
  `--check-callers` refuses a literal list or a repository variable;
- F2: an omitted leg prints a `::notice` annotation;
- F4: a `pull_request_target` event omits nothing and reads nothing;
- F5: a caller value cannot inject a workflow command through a newline;
- F6: a slug run-check cannot run (kebab case) is never omitted.

Each case sits beside its negative control: the fully authorized leg, which
omits.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_matrix_omission

__all__: list[str] = []

_REPOSITORY = "owner/repo"
_LIST = '["check-heading-coverage", "check-per-file-coverage"]'
_GUARDED = (
    "      incident-omitted: ${{ needs.incident-ci.result == 'success' && "
    "needs.incident-ci.outputs.omitted || '[]' }}\n"
)
_CALLER = (
    "jobs:\n  shared:\n    needs: [incident-ci]\n"
    "    uses: thewoolleyman/livespec-dev-tooling/.github/workflows/"
    "reusable-check-matrix.yml@v1.191.0\n    with:\n"
    "      checks: '[\"heading_coverage\"]'\n"
    + _GUARDED
    + "      incident-ci-result: ${{ needs.incident-ci.result }}\n"
)


def _payload(*, labels=("expedited-incident-response",), head=_REPOSITORY):
    return {
        "pull_request": {
            "labels": [{"name": name} for name in labels],
            "head": {"repo": {"full_name": head}},
            "base": {"repo": {"full_name": _REPOSITORY}},
        }
    }


def _run(tmp_path: Path, monkeypatch, capsys, **overrides):
    """One decision-step run; returns (exit code, `omit` written, printed lines)."""
    workspace = tmp_path / "workspace"
    (workspace / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    caller = overrides.pop("caller", _CALLER)
    (workspace / ".github" / "workflows" / "ci.yml").write_text(caller, encoding="utf-8")
    event = tmp_path / "event.json"
    event.write_text(json.dumps(overrides.pop("payload", _payload())), encoding="utf-8")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    environ = {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_REPOSITORY": _REPOSITORY,
        "GITHUB_WORKSPACE": str(workspace),
        "GITHUB_OUTPUT": str(output),
        "INCIDENT_OMITTED": _LIST,
        "INCIDENT_CI_RESULT": "success",
        "MATRIX_CHECK": "heading_coverage",
        **overrides,
    }
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["incident_matrix_omission"])
    code = incident_matrix_omission.main()
    captured = capsys.readouterr()
    return code, output.read_text(encoding="utf-8"), (captured.out + captured.err).splitlines()


def test_an_authorized_incident_omits_and_annotates_the_leg(tmp_path, monkeypatch, capsys):
    code, omit, lines = _run(tmp_path, monkeypatch, capsys)
    assert (code, omit) == (0, "omit=true\n")
    assert any(line.startswith("::notice title=omitted-by-incident-policy::") for line in lines)


@pytest.mark.parametrize(
    "overrides",
    [
        {"payload": _payload(head="fork/repo")},
        {"payload": _payload(labels=())},
        {"payload": _payload(labels=("question",))},
        {"INCIDENT_CI_RESULT": "failure"},
        {"INCIDENT_CI_RESULT": ""},
        {
            "caller": _CALLER.replace(
                _GUARDED, "      incident-omitted: '[\"check-heading-coverage\"]'\n"
            )
        },
        {"caller": _CALLER.replace(_GUARDED, "      incident-omitted: ${{ vars.OMITTED }}\n")},
        {"caller": "jobs: {}\n"},
    ],
)
def test_an_unauthorized_pull_request_omits_nothing(tmp_path, monkeypatch, capsys, overrides):
    code, omit, lines = _run(tmp_path, monkeypatch, capsys, **overrides)
    assert (code, omit) == (0, "omit=false\n")
    assert any(line.startswith("::warning::incident-omission-unauthorized:") for line in lines)
    assert not any(line.startswith("::notice") for line in lines)


def test_a_pull_request_target_event_omits_nothing(tmp_path, monkeypatch, capsys):
    code, omit, lines = _run(tmp_path, monkeypatch, capsys, GITHUB_EVENT_NAME="pull_request_target")
    assert (code, omit) == (0, "omit=false\n")
    assert lines[-1].endswith("the incident-omitted input is not read")


def test_a_kebab_slug_run_check_cannot_run_is_never_omitted(tmp_path, monkeypatch, capsys):
    code, omit, lines = _run(tmp_path, monkeypatch, capsys, MATRIX_CHECK="check-heading-coverage")
    assert (code, omit) == (0, "omit=false\n")
    assert any(line.startswith("::warning::incident-omission-refused-leg:") for line in lines)


def test_a_caller_value_cannot_inject_a_workflow_command(tmp_path, monkeypatch, capsys):
    raw = json.dumps(["x\n::error title=spoof::check-lint passed", "check-heading-coverage"])
    code, omit, lines = _run(
        tmp_path, monkeypatch, capsys, INCIDENT_OMITTED=raw, MATRIX_CHECK="lint\n::error::spoof"
    )
    assert (code, omit) == (0, "omit=false\n")
    assert not any(line.startswith("::error") for line in lines)
    assert len(lines) == 3


@pytest.mark.parametrize(
    ("caller", "code"),
    [
        (_CALLER, 0),
        (_CALLER.replace(_GUARDED, "      incident-omitted: '[\"check-coverage\"]'\n"), 1),
        (_CALLER.replace(_GUARDED, "      incident-omitted: ${{ vars.OMITTED }}\n"), 1),
        (
            _CALLER.replace(
                "${{ needs.incident-ci.result }}", "${{ vars.INCIDENT_CI_RESULT || 'success' }}"
            ),
            1,
        ),
    ],
)
def test_check_callers_refuses_any_wiring_but_incident_ci(
    tmp_path, monkeypatch, capsys, caller, code
):
    workflow = tmp_path / "ci.yml"
    workflow.write_text(caller, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["incident_matrix_omission", "--check-callers", str(workflow)])
    assert incident_matrix_omission.main() == code
    assert (capsys.readouterr().err != "") == bool(code)
