"""Consumer-tier scenario: a default-branch push routes to the master runner target."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github/workflows/ci.yml"
_HOSTED = ("ubuntu-latest",)
_EXPRESSION = re.compile(r"^\$\{\{\s*fromJSON\((?P<body>.+)\)\s*\}\}$")
_PUSH_GUARDED = re.compile(r"^github\.event_name == 'push' && vars\.(?P<name>[A-Z_]+)$")
_VARIABLE = re.compile(r"^vars\.(?P<name>[A-Z_]+)$")
_LITERAL = re.compile(r"^'(?P<json>\[.*\])'$")
_MASTER = '["livespec-dev-master-k3s"]'
_SHARED = '["livespec-dev-tooling-k3s"]'


def _terms(*, runs_on: str) -> list[str]:
    """The `||`-joined terms inside a job's `fromJSON(...)` runs-on expression."""
    match = _EXPRESSION.match(runs_on.strip())
    assert match is not None, f"runs-on is not a fromJSON expression: {runs_on!r}"
    return [term.strip() for term in match.group("body").split("||")]


def _resolve(*, runs_on: str, event: str, variables: dict[str, str]) -> list[str]:
    """Evaluate one runs-on expression the way the Actions expression engine does.

    `a && b` yields `b` when `a` holds and a falsy value otherwise; `x || y`
    yields the first truthy term. An unset repository variable is the empty
    string, which is falsy.
    """
    for term in _terms(runs_on=runs_on):
        guarded = _PUSH_GUARDED.match(term)
        variable = _VARIABLE.match(term)
        literal = _LITERAL.match(term)
        if guarded is not None:
            value = variables.get(guarded.group("name"), "") if event == "push" else ""
        elif variable is not None:
            value = variables.get(variable.group("name"), "")
        elif literal is not None:
            value = literal.group("json")
        else:
            pytest.fail(f"unrecognised runs-on term {term!r} in {runs_on!r}")
        if value:
            return json.loads(value)
    pytest.fail(f"runs-on resolved to no runner: {runs_on!r}")


def _gating_runs_on() -> dict[str, str]:
    """Each self-hosted-routable gating job (a `needs:` of `ci-green`) with its runs-on."""
    jobs = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    gating = jobs["ci-green"]["needs"]
    routed = {
        name: str(jobs[name]["runs-on"]) for name in gating if jobs[name]["runs-on"] not in _HOSTED
    }
    assert routed, "no gating job of ci.yml routes to a self-hosted target"
    return routed


def test_a_push_runs_every_gating_job_on_the_master_target() -> None:
    """With the master variable set, a push resolves every gating job to it."""
    variables = {"CI_RUNNER_LABELS_MASTER": _MASTER, "CI_RUNNER_LABELS": _SHARED}
    for job, runs_on in _gating_runs_on().items():
        assert _resolve(runs_on=runs_on, event="push", variables=variables) == json.loads(
            _MASTER
        ), job


def test_a_pull_request_runs_every_gating_job_on_the_shared_target() -> None:
    """A pull-request run at the same time resolves every gating job to `CI_RUNNER_LABELS`."""
    variables = {"CI_RUNNER_LABELS_MASTER": _MASTER, "CI_RUNNER_LABELS": _SHARED}
    for job, runs_on in _gating_runs_on().items():
        assert _resolve(runs_on=runs_on, event="pull_request", variables=variables) == json.loads(
            _SHARED
        ), job


def test_a_push_falls_back_to_the_shared_target_when_the_master_variable_is_deleted() -> None:
    """With `CI_RUNNER_LABELS_MASTER` deleted, the next push resolves to `CI_RUNNER_LABELS`."""
    variables = {"CI_RUNNER_LABELS": _SHARED}
    for job, runs_on in _gating_runs_on().items():
        assert _resolve(runs_on=runs_on, event="push", variables=variables) == json.loads(
            _SHARED
        ), job


def test_the_last_term_of_every_gating_runs_on_is_a_github_hosted_literal() -> None:
    """With no variable set at all, every gating job lands on a GitHub-hosted runner."""
    for job, runs_on in _gating_runs_on().items():
        assert _LITERAL.match(_terms(runs_on=runs_on)[-1]) is not None, job
        assert _resolve(runs_on=runs_on, event="push", variables={}) == ["ubuntu-latest"], job
