"""Incident label events restart CI on the head; reusable-check-matrix honors omission on PRs only.

Work-item livespec-dev-tooling-6xyc42 (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm), carrying what livespec-dev-tooling-egy3ri
left undone. `SPECIFICATION/contracts.md`, in its expedited incident execution
contract, requires that "Head and mode changes MUST invalidate stale verdicts", and its
scenario requires that "label events reconcile mode before permitting merge".
The live behaviour is host-captured (a real label event and the runs it starts
exist only on the forge), so this file holds the workflow SHAPE as rules:

- **An incident label event restarts CI on the current head.**
  `.github/workflows/incident-label-ci.yml` triggers on `labeled` and
  `unlabeled`, reads the PR's current head through an authenticated forge read,
  picks the newest pull_request run of `ci.yml` on that head, cancels it if it
  has not finished, and re-runs it. The re-run's `incident-ci` job reads the
  labels afresh, so its `ci-green` replaces the earlier verdict: the expedited
  aggregate after the label is added, every member executed after it is
  removed.
- **A non-incident label event runs nothing.** Every job of that workflow is
  skipped at the job level unless the event's label IS the incident label, and
  `ci.yml` itself still does not trigger on label events. Approval, merge-hold
  and do-not-merge labels therefore start no CI run and allocate no runner.
- **reusable-check-matrix omits only on a pull request.** Its optional
  `incident-omitted` input carries the caller's passed incident aggregate's
  `omitted` list. A leg whose slug is in that list runs an explicit
  `omitted-by-incident-policy` step instead of the setup and the check; every
  other leg runs its check. The one guard expression tests
  `github.event_name == 'pull_request'` first, so a master push runs every
  requested check whatever omission input it receives.

Each rule is exercised twice, as the sibling `test_incident_ci_workflow_wiring`
does: against the committed workflow (expecting silence) and against a copy
mutated to break exactly that rule (expecting the finding).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

__all__: list[str] = []


_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_LABEL_WORKFLOW = _WORKFLOWS / "incident-label-ci.yml"
_CI_YML = _WORKFLOWS / "ci.yml"
_MATRIX = _WORKFLOWS / "reusable-check-matrix.yml"

_INCIDENT_LABEL_TEST = "github.event.label.name == 'expedited-incident-response'"
_LABEL_TYPES = frozenset({"labeled", "unlabeled"})

# The forge reads and writes the restart must make, in this order.
_HEAD_READ = """gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}" --jq '.head.sha'"""
_RUN_ON_HEAD = "actions/workflows/ci.yml/runs?event=pull_request&head_sha=${head}"
_CANCEL = '/actions/runs/${run_id}/cancel"'
_RERUN = '/actions/runs/${run_id}/rerun"'

# The one expression that decides a reusable-matrix omission. The event test
# comes first: no other event can reach the omission list.
_OMISSION = (
    "github.event_name == 'pull_request' && "
    "contains(fromJSON(inputs.incident-omitted || '[]'), matrix.check)"
)
_OMIT_STEP_IF = "${{ " + _OMISSION + " }}"
_RUN_STEP_IF = "${{ !(" + _OMISSION + ") }}"
_OMIT_STEP_PREFIX = "omitted-by-incident-policy"
_OMIT_STEP_NAME_TAIL = "(per the caller's released incident CI aggregate)\n"
_CHECK_ACTIONS = ("/.github/actions/setup", "/.github/actions/run-check")


def _map(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _seq(*, value: object) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def _load(*, source: str) -> dict[str, Any]:
    # BaseLoader keeps every scalar a string, so the bare key `on` stays "on"
    # rather than becoming the boolean True, and `false` stays "false".
    return _map(value=yaml.load(source, Loader=yaml.BaseLoader))  # noqa: S506


def _triggers(*, workflow: dict[str, Any]) -> dict[str, Any]:
    return _map(value=workflow.get("on"))


def label_workflow_findings(*, source: str) -> list[str]:
    """Every way the label workflow fails to restart CI on an incident label event only."""
    workflow = _load(source=source)
    findings: list[str] = []
    triggers = _triggers(workflow=workflow)
    if set(triggers) != {"pull_request"}:
        findings.append("the label workflow triggers on something other than pull_request")
    types = frozenset(
        str(t) for t in _seq(value=_map(value=triggers.get("pull_request")).get("types"))
    )
    if types != _LABEL_TYPES:
        findings.append("the label workflow does not trigger on exactly labeled and unlabeled")
    if workflow.get("permissions") != {}:
        findings.append("the label workflow grants workflow-level permissions")
    jobs = _map(value=workflow.get("jobs"))
    scripts: list[str] = []
    for name, raw_job in jobs.items():
        job = _map(value=raw_job)
        if _INCIDENT_LABEL_TEST not in str(job.get("if", "")):
            findings.append(f"job {name} runs on a non-incident label event")
        scripts.extend(
            str(_map(value=step).get("run", "")) for step in _seq(value=job.get("steps"))
        )
    script = "\n".join(scripts)
    if _HEAD_READ not in script:
        findings.append("the restart does not read the current head from the forge")
    if _RUN_ON_HEAD not in script:
        findings.append("the restart does not select the pull_request CI run on the current head")
    if _RERUN not in script:
        findings.append("the restart does not re-run the CI run")
    elif _CANCEL not in script or script.index(_CANCEL) > script.index(_RERUN):
        findings.append("the restart does not cancel an unfinished CI run before re-running it")
    return findings


def ci_label_trigger_findings(*, source: str) -> list[str]:
    """ci.yml must not start its full matrix on every label event."""
    pull_request = _map(value=_triggers(workflow=_load(source=source)).get("pull_request"))
    types = {str(t) for t in _seq(value=pull_request.get("types"))}
    if types & _LABEL_TYPES:
        return ["ci.yml starts its full matrix on every label event"]
    return []


def matrix_findings(*, source: str) -> list[str]:
    """Every way reusable-check-matrix fails the incident omission wiring."""
    workflow = _load(source=source)
    findings: list[str] = []
    call = _map(value=_triggers(workflow=workflow).get("workflow_call"))
    omitted = _map(value=_map(value=call.get("inputs")).get("incident-omitted"))
    declared = (omitted.get("required"), omitted.get("type"), omitted.get("default"))
    if declared != ("false", "string", "[]"):
        findings.append("the incident-omitted input is not an optional string defaulting to '[]'")
    check_job = _map(value=_map(value=workflow.get("jobs")).get("check"))
    steps = [_map(value=step) for step in _seq(value=check_job.get("steps"))]
    reports = [
        step
        for step in steps
        if str(step.get("name", "")).startswith(_OMIT_STEP_PREFIX)
        and step.get("if") == _OMIT_STEP_IF
    ]
    if len(reports) != 1:
        findings.append("no single omitted-by-incident-policy step carries the canonical guard")
    for step in steps:
        uses = str(step.get("uses", ""))
        if uses.endswith(_CHECK_ACTIONS) and step.get("if") != _RUN_STEP_IF:
            findings.append(
                f"step {step.get('name')} is not guarded by the incident omission guard"
            )
    return findings


def _mutated(*, source: str, old: str, new: str) -> str:
    """Replace exactly one occurrence, so a mutation never lands twice or nowhere."""
    assert source.count(old) == 1, old
    return source.replace(old, new)


def test_committed_label_workflow_restarts_ci_on_incident_label_events_only() -> None:
    assert label_workflow_findings(source=_LABEL_WORKFLOW.read_text(encoding="utf-8")) == []


def test_committed_ci_yml_does_not_trigger_on_label_events() -> None:
    assert ci_label_trigger_findings(source=_CI_YML.read_text(encoding="utf-8")) == []


def test_committed_reusable_matrix_omits_only_through_the_guard() -> None:
    assert matrix_findings(source=_MATRIX.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "    types: [labeled, unlabeled]\n",
            "    types: [labeled]\n",
            "the label workflow does not trigger on exactly labeled and unlabeled",
        ),
        (
            "    types: [labeled, unlabeled]\n",
            "    types: [labeled, unlabeled]\n  push:\n    branches: [master]\n",
            "the label workflow triggers on something other than pull_request",
        ),
        (
            "\npermissions: {}\n",
            "\npermissions:\n  actions: write\n",
            "the label workflow grants workflow-level permissions",
        ),
        (
            f"    if: ${{{{ {_INCIDENT_LABEL_TEST} && ",
            "    if: ${{ ",
            "job restart-ci-on-head runs on a non-incident label event",
        ),
        (
            "--jq '.head.sha'",
            "--jq '.base.sha'",
            "the restart does not read the current head from the forge",
        ),
        (
            "runs?event=pull_request&head_sha=${head}",
            "runs?head_sha=${head}",
            "the restart does not select the pull_request CI run on the current head",
        ),
        (
            '/rerun"',
            '/rerun-failed-jobs"',
            "the restart does not re-run the CI run",
        ),
        (
            '/cancel"',
            '/approve"',
            "the restart does not cancel an unfinished CI run before re-running it",
        ),
    ],
)
def test_each_label_workflow_rule_has_a_negative_control(
    *, old: str, new: str, expected: str
) -> None:
    source = _mutated(source=_LABEL_WORKFLOW.read_text(encoding="utf-8"), old=old, new=new)
    assert expected in label_workflow_findings(source=source)


def test_the_ci_label_trigger_rule_has_a_negative_control() -> None:
    source = _mutated(
        source=_CI_YML.read_text(encoding="utf-8"),
        old="\n  pull_request:\n  push:\n",
        new="\n  pull_request:\n    types: [opened, synchronize, reopened, labeled, unlabeled]\n  push:\n",
    )
    assert ci_label_trigger_findings(source=source) == [
        "ci.yml starts its full matrix on every label event"
    ]


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "        default: '[]'\n",
            "        default: '[\"check-lint\"]'\n",
            "the incident-omitted input is not an optional string defaulting to '[]'",
        ),
        (
            _OMIT_STEP_NAME_TAIL + "        if: ${{ github.event_name == 'pull_request' && ",
            _OMIT_STEP_NAME_TAIL + "        if: ${{ ",
            "no single omitted-by-incident-policy step carries the canonical guard",
        ),
        (
            "      - name: Run check\n        if: ${{ !(github.event_name == 'pull_request' && ",
            "      - name: Run check\n        if: ${{ !(",
            "step Run check is not guarded by the incident omission guard",
        ),
        (
            "      - name: Setup toolchain\n        if: " + _RUN_STEP_IF + "\n",
            "      - name: Setup toolchain\n",
            "step Setup toolchain is not guarded by the incident omission guard",
        ),
    ],
)
def test_each_matrix_rule_has_a_negative_control(*, old: str, new: str, expected: str) -> None:
    source = _mutated(source=_MATRIX.read_text(encoding="utf-8"), old=old, new=new)
    assert expected in matrix_findings(source=source)
