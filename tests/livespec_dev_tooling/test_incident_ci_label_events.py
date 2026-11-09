"""Incident label events hold ci-green and restart CI on the head; nothing else reacts.

Work-item livespec-dev-tooling-6xyc42 (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm), carrying what livespec-dev-tooling-egy3ri
left undone. `SPECIFICATION/contracts.md`, in its expedited incident execution
contract, requires that "Head and mode changes MUST invalidate stale verdicts",
and its scenario requires that "label events reconcile mode before permitting
merge". The live behaviour is host-captured (a real label event and the runs it
starts exist only on the forge), so this file holds the workflow SHAPE as exact
rules, because each rule here is a security or merge-safety property:

- **Only an incident label event of a same-repository PR acts.** The trigger
  set, the job set and the job's `if:` are pinned exactly, so a widened
  condition (`|| true`), a dropped fork guard or an added trigger is a finding.
- **Only incident label events share a concurrency group.** A non-incident
  label in the same edit must never cancel an incident restart in flight.
- **Least privilege, no injection.** The workflow grants nothing; the job holds
  exactly `actions: write`, `checks: write` and `pull-requests: read`, and no
  `run:` script interpolates an expression (`${{ ... }}`) of any kind.
- **The restart holds ci-green before anything else, and again before the
  re-run.** It selects the newest pull_request CI run of THIS PR (by number) on
  the current head, stops green when none is listed yet, posts an in-progress
  `ci-green` check run, cancels and waits for an unfinished run with a real
  bound, holds again, and re-runs.
- **auto-enable-merge cannot race the hold.** Its gate skips the unlabeled
  event of the incident label, and `ci.yml` still does not trigger on labels.

Each rule is exercised twice, as the sibling `test_incident_ci_workflow_wiring`
does: against the committed workflow (expecting silence) and against a copy
mutated to break exactly that rule (expecting the finding).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

__all__: list[str] = []


_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_LABEL_WORKFLOW = _WORKFLOWS / "incident-label-ci.yml"
_CI_YML = _WORKFLOWS / "ci.yml"
_AUTO_MERGE = _WORKFLOWS / "auto-enable-merge.yml"

_JOB = "restart-ci-on-head"
_LABEL_TYPES = frozenset({"labeled", "unlabeled"})
_INCIDENT_LABEL_TEST = "github.event.label.name == 'expedited-incident-response'"
_FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"
_JOB_IF = "${{ " + _INCIDENT_LABEL_TEST + " && " + _FORK_GUARD + " }}"
_GROUP_KEY = "${{ " + _INCIDENT_LABEL_TEST + " && 'incident' || github.run_id }}"
_CONCURRENCY = {
    "group": "incident-label-ci-${{ github.event.pull_request.number }}-" + _GROUP_KEY,
    "cancel-in-progress": "true",
}
_JOB_PERMISSIONS = {"actions": "write", "checks": "write", "pull-requests": "read"}
_EXPRESSION = "${{"

# The forge reads and writes the restart must make.
_HEAD_READ = """gh api "repos/${repo}/pulls/${PR_NUMBER}" --jq '.head.sha'"""
_RUNS_ON_HEAD = "actions/workflows/ci.yml/runs?event=pull_request&head_sha=${head}"
_SELECT_BY_PR = "select(any(.pull_requests[]; .number == (env.PR_NUMBER | tonumber)))"
_NO_RUN = re.compile(r'if \[ -z "\$run_id" \]; then\n(?P<body>(?:.*\n)*?)[ ]*fi\n')
_HOLD_POST = '-X POST "repos/${repo}/check-runs"'
_HOLD_FIELDS = '-f name=ci-green -f head_sha="$head" -f status=in_progress'
_HOLD_CALL = "\nhold_ci_green\n"
_CANCEL = '/actions/runs/${run_id}/cancel"'
_RERUN = '/actions/runs/${run_id}/rerun"'
_LOOP_HEAD = r"for _ in \$\(seq 1 (?P<bound>\d+)\); do\n"
_LOOP_TAIL = r'(?P<body>(?:.*\n)*?)[ ]*done\n[ ]*if \[ "\$status" != "completed" \]; then\n'
_LOOP_AFTER = r"(?P<after>(?:.*\n)*?)[ ]*fi\n"
_WAIT_LOOP = re.compile(_LOOP_HEAD + _LOOP_TAIL + _LOOP_AFTER)
_LOOP_BREAK = '[ "$status" = "completed" ] && break'

_AUTO_MERGE_SKIP = "&& !(github.event.action == 'unlabeled' && " + _INCIDENT_LABEL_TEST + ")"


def _map(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _seq(*, value: object) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def _load(*, source: str) -> dict[str, Any]:
    # BaseLoader keeps every scalar a string, so the bare key `on` stays "on"
    # rather than becoming the boolean True, and `true` stays "true".
    return _map(value=yaml.load(source, Loader=yaml.BaseLoader))  # noqa: S506


def _triggers(*, workflow: dict[str, Any]) -> dict[str, Any]:
    return _map(value=workflow.get("on"))


def _workflow_findings(*, workflow: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    triggers = _triggers(workflow=workflow)
    types = frozenset(
        str(t) for t in _seq(value=_map(value=triggers.get("pull_request")).get("types"))
    )
    if set(triggers) != {"pull_request"} or types != _LABEL_TYPES:
        findings.append("the label workflow does not trigger on exactly labeled/unlabeled PRs")
    if workflow.get("permissions") != {}:
        findings.append("the label workflow grants workflow-level permissions")
    if workflow.get("concurrency") != _CONCURRENCY:
        findings.append("the concurrency group is not keyed to incident label events only")
    return findings


def _job_findings(*, jobs: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if set(jobs) != {_JOB}:
        findings.append(f"the label workflow's jobs are not exactly {_JOB}")
    job = _map(value=jobs.get(_JOB))
    if job.get("if") != _JOB_IF:
        findings.append(f"job {_JOB} is not gated on exactly the incident label and the fork guard")
    if job.get("permissions") != _JOB_PERMISSIONS:
        findings.append(f"job {_JOB} holds permissions other than {_JOB_PERMISSIONS}")
    return findings


def _script_findings(*, script: str) -> list[str]:
    findings: list[str] = []
    if _EXPRESSION in script:
        findings.append("a run: script interpolates an expression")
    if _HEAD_READ not in script:
        findings.append("the restart does not read the current head from the forge")
    if _RUNS_ON_HEAD not in script or _SELECT_BY_PR not in script:
        findings.append("the restart does not select THIS PR's pull_request CI run on the head")
    no_run = _NO_RUN.search(script)
    if no_run is None or "exit 0" not in no_run.group("body"):
        findings.append("a PR with no CI run listed yet does not stop green")
    if _HOLD_POST not in script or _HOLD_FIELDS not in script:
        findings.append("the hold is not an in-progress ci-green check run on the head")
    wait = _WAIT_LOOP.search(script)
    if (
        wait is None
        or int(wait.group("bound")) < 1
        or _LOOP_BREAK not in wait.group("body")
        or "exit 1" not in wait.group("after")
    ):
        findings.append("the restart does not wait, bounded, for an unfinished run to stop")
    calls = [match.start() for match in re.finditer(re.escape(_HOLD_CALL), script)]
    if _RERUN not in script or _CANCEL not in script:
        findings.append("the restart does not cancel and re-run the CI run")
    elif not calls or calls[0] > script.index(_CANCEL):
        findings.append("ci-green is not held before the run is touched")
    elif wait is None or not any(wait.end() < call < script.index(_RERUN) for call in calls):
        findings.append("ci-green is not held again between the wait and the re-run")
    return findings


def label_workflow_findings(*, source: str) -> list[str]:
    """Every way the label workflow departs from its pinned, merge-safe shape."""
    workflow = _load(source=source)
    jobs = _map(value=workflow.get("jobs"))
    scripts = [
        str(_map(value=step).get("run", ""))
        for job in jobs.values()
        for step in _seq(value=_map(value=job).get("steps"))
    ]
    return [
        *_workflow_findings(workflow=workflow),
        *_job_findings(jobs=jobs),
        *_script_findings(script="\n".join(scripts)),
    ]


def ci_label_trigger_findings(*, source: str) -> list[str]:
    """ci.yml must not start its full matrix on every label event."""
    pull_request = _map(value=_triggers(workflow=_load(source=source)).get("pull_request"))
    types = {str(t) for t in _seq(value=pull_request.get("types"))}
    if types & _LABEL_TYPES:
        return ["ci.yml starts its full matrix on every label event"]
    return []


def auto_merge_findings(*, source: str) -> list[str]:
    """auto-enable-merge must not arm on the incident label's unlabeled event."""
    jobs = _map(value=_load(source=source).get("jobs"))
    gate = str(_map(value=jobs.get("enable-auto-merge")).get("if", ""))
    if _AUTO_MERGE_SKIP not in gate:
        return ["auto-enable-merge arms on the incident label's unlabeled event"]
    return []


def _mutated(*, source: str, old: str, new: str) -> str:
    """Replace exactly one occurrence, so a mutation never lands twice or nowhere."""
    assert source.count(old) == 1, old
    return source.replace(old, new)


def test_committed_label_workflow_holds_and_restarts_on_incident_label_events_only() -> None:
    assert label_workflow_findings(source=_LABEL_WORKFLOW.read_text(encoding="utf-8")) == []


def test_committed_ci_yml_does_not_trigger_on_label_events() -> None:
    assert ci_label_trigger_findings(source=_CI_YML.read_text(encoding="utf-8")) == []


def test_committed_auto_enable_merge_skips_the_incident_unlabeled_event() -> None:
    assert auto_merge_findings(source=_AUTO_MERGE.read_text(encoding="utf-8")) == []


_TRIGGERS = "the label workflow does not trigger on exactly labeled/unlabeled PRs"
_GATE = f"job {_JOB} is not gated on exactly the incident label and the fork guard"
_WAIT = "the restart does not wait, bounded, for an unfinished run to stop"


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("    types: [labeled, unlabeled]\n", "    types: [labeled]\n", _TRIGGERS),
        (
            "    types: [labeled, unlabeled]\n",
            "    types: [labeled, unlabeled]\n  pull_request_target:\n",
            _TRIGGERS,
        ),
        (
            "\npermissions: {}\n",
            "\npermissions:\n  actions: write\n",
            "the label workflow grants workflow-level permissions",
        ),
        (
            "concurrency:\n  group: " + _CONCURRENCY["group"] + "\n  cancel-in-progress: true\n",
            "",
            "the concurrency group is not keyed to incident label events only",
        ),
        (
            "-" + _GROUP_KEY + "\n",
            "\n",
            "the concurrency group is not keyed to incident label events only",
        ),
        (
            "  restart-ci-on-head:\n",
            "  restart-ci-on-head:\n    name: x\n  second:\n",
            f"the label workflow's jobs are not exactly {_JOB}",
        ),
        ("== github.repository }}\n", "== github.repository || true }}\n", _GATE),
        (" && " + _FORK_GUARD + " }}", " }}", _GATE),
        (
            "      pull-requests: read\n",
            "      pull-requests: write\n      contents: write\n",
            f"job {_JOB} holds permissions other than {_JOB_PERMISSIONS}",
        ),
        (
            "          set -euo pipefail\n",
            '          set -euo pipefail\n          echo "${{ github.event.pull_request.title }}"\n',
            "a run: script interpolates an expression",
        ),
        (
            "--jq '.head.sha'",
            "--jq '.base.sha'",
            "the restart does not read the current head from the forge",
        ),
        (
            _SELECT_BY_PR,
            "select(true)",
            "the restart does not select THIS PR's pull_request CI run on the head",
        ),
        (
            "\n            exit 0\n",
            "\n            exit 1\n",
            "a PR with no CI run listed yet does not stop green",
        ),
        (
            "status=in_progress",
            "status=completed -f conclusion=success",
            "the hold is not an in-progress ci-green check run on the head",
        ),
        ("$(seq 1 60)", "$(seq 1 0)", _WAIT),
        ('[ "$status" = "completed" ] && break', "true", _WAIT),
        ('ci-green stays held"\n              exit 1\n', 'ci-green stays held"\n', _WAIT),
        (
            '/rerun"',
            '/rerun-failed-jobs"',
            "the restart does not cancel and re-run the CI run",
        ),
        (
            "          hold_ci_green\n          status=",
            "          status=",
            "ci-green is not held before the run is touched",
        ),
        (
            "          hold_ci_green\n          gh api -X POST",
            "          gh api -X POST",
            "ci-green is not held again between the wait and the re-run",
        ),
    ],
)
def test_each_label_workflow_rule_has_a_negative_control(
    *, old: str, new: str, expected: str
) -> None:
    source = _mutated(source=_LABEL_WORKFLOW.read_text(encoding="utf-8"), old=old, new=new)
    assert expected in label_workflow_findings(source=source)


def test_a_wait_loop_that_is_gone_entirely_is_a_finding() -> None:
    source = _LABEL_WORKFLOW.read_text(encoding="utf-8")
    start = source.index("            for _ in $(seq 1 60); do\n")
    end = source.index("          hold_ci_green\n          gh api -X POST")
    findings = label_workflow_findings(source=source[:start] + source[end:])
    assert _WAIT in findings
    assert "ci-green is not held again between the wait and the re-run" in findings


def test_the_ci_label_trigger_rule_has_a_negative_control() -> None:
    source = _mutated(
        source=_CI_YML.read_text(encoding="utf-8"),
        old="\n  pull_request:\n  push:\n",
        new="\n  pull_request:\n    types: [opened, synchronize, reopened, labeled, unlabeled]\n  push:\n",
    )
    assert ci_label_trigger_findings(source=source) == [
        "ci.yml starts its full matrix on every label event"
    ]


def test_the_auto_merge_skip_rule_has_a_negative_control() -> None:
    source = _mutated(
        source=_AUTO_MERGE.read_text(encoding="utf-8"),
        old="      " + _AUTO_MERGE_SKIP + "\n",
        new="",
    )
    assert auto_merge_findings(source=source) == [
        "auto-enable-merge arms on the incident label's unlabeled event"
    ]
