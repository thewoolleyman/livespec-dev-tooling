"""An expedited incident PR omits coverage and spec work ONLY through the released aggregate.

Work-item livespec-dev-tooling-z3wy33 (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm; maintainer ruling of 2026-11-05). The
`incident-ci` job of `.github/workflows/ci.yml` publishes one job output,
`omitted`, and that output is the only thing that makes another job omit work.
The live behaviour is host-captured (GitHub Actions runs), so this file holds
the workflow's SHAPE, the three guardrails of the ruling as rules over the
workflow text:

- **Omission comes from the released controller's confirmed authority, and from
  nothing else.** `omitted` has exactly one writer, the step that runs the
  released entrance, and that write sits after the released `aggregate` has
  passed. The list is projected out of that aggregate's own JSON. No job reads
  a label, a repository variable or an environment value to decide.
- **An omitted member is reported, never skipped silently, and the required set
  is unchanged.** Each job holding a deferred member still runs, guards the
  member's own steps with the one canonical expression, and carries an
  explicit `omitted-by-incident-policy` report. `ci-green` requires the same
  jobs as before, keeps its failure gate, and repeats the list.
- **Every other run executes the complete normal policy.** A job that reads the
  output can be skipped by nothing: its job-level `if:` is run-status-only, so
  a failed or refused `incident-ci` leaves it running in full. The workflow
  itself sets neither incident flag for any job.

The members the workflow guards are compared with what THIS repository's
incident controller defers for the coverage or spec policy reason over the
packaged inventory, built through the public `incident_ci_policy` API with a
confirmed authority. A classification change therefore fails here by name.

Each rule is exercised twice, as the sibling `test_incident_ci_workflow_wiring`
does: against the committed workflow (expecting silence) and against a copy
mutated to break exactly that rule (expecting the finding).
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from livespec_dev_tooling.incident_ci_inventory import load_inventory
from livespec_dev_tooling.incident_ci_policy import (
    CiAggregate,
    CiAuthority,
    CiEvent,
    CiOutcome,
    CiPlan,
    CiTrust,
    aggregate_ci_results,
    select_ci_plan,
)
from livespec_dev_tooling.incident_execution import (
    ExecutionContext,
    ExecutionMode,
    Invocation,
    OperationIdentity,
)

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_INCIDENT_JOB = "incident-ci"
_GATE_JOB = "ci-green"

# The jobs `ci-green` requires. Identical to the set before this work item:
# branch protection requires only `ci-green`, so this set IS the required set.
_REQUIRED = frozenset(
    {
        "check-python",
        "check-per-file-coverage",
        "check-coverage",
        "check-python-batch",
        "check-fleet-conformance",
        "check-metadata",
        "check-metadata-batch",
        _INCIDENT_JOB,
    }
)
_ALL_JOBS = _REQUIRED | {"export-telemetry", _GATE_JOB}

# The members each job may omit: exactly what the released controller defers
# for the coverage or spec policy reason. `test_the_guarded_members_are_...`
# derives the same mapping from the controller and the packaged inventory.
_OMITTED_BY_JOB = {
    "check-per-file-coverage": {"check-per-file-coverage"},
    "check-coverage": {"check-coverage"},
    "check-metadata": {"check-check-coverage-incremental"},
    "check-metadata-batch": {
        "check-heading-coverage",
        "check-heading-coverage-debt-register",
        "check-no-todo-registry",
    },
}
_OMITTING_REASONS = frozenset({"incident-policy:coverage", "incident-policy:spec"})

# The jobs whose member is a whole step, with the member as the guard names it.
_SINGLE_MEMBER_JOBS = {
    "check-per-file-coverage": "'check-per-file-coverage'",
    "check-coverage": "matrix.target",
    "check-metadata": "matrix.target",
}
_BATCH_JOB = "check-metadata-batch"

# The one expression that decides an omission. It reads the `incident-ci` job's
# result and output and nothing else.
_GUARD = (
    "needs.incident-ci.result == 'success' && "
    "contains(fromJSON(needs.incident-ci.outputs.omitted || '[]'), {member})"
)
_BATCH_ENV = (
    "${{ needs.incident-ci.result == 'success' && needs.incident-ci.outputs.omitted || '' }}"
)
_RUN_STATUS_ONLY = (
    "${{ !cancelled() }}",
    "${{ !cancelled() && needs.check-per-file-coverage.result == 'success' }}",
)

# The entrance step's tail: the released aggregate must pass before the write.
_PASS_CHECK = (
    'if ! aggregate="$("${entrance[@]}" aggregate --repo "$PWD" --reports tmp/incident-ci)"; then\n'
    '  echo "::error::released aggregate did not pass: ${aggregate}"\n'
    "  exit 1\n"
    "fi\n"
)
_WRITE = 'echo "omitted=${omitted}" >> "$GITHUB_OUTPUT"'
_PROJECTION = re.compile(r"-I -c '(import json, sys; [^']*\"deferred\"[^']*)'")

# The batch job's shell test and its per-member wrapper line.
_BATCH_FUNCTION = (
    "omitted_by_incident_policy() {\n"
    '  case "$OMITTED_BY_INCIDENT_POLICY" in\n'
    '    *"\\"$1\\""*) echo "omitted-by-incident-policy: $1 was not executed.'
)
_BATCH_FUNCTION_TAIL = '| tee -a "$GITHUB_STEP_SUMMARY" ;;\n    *) return 1 ;;\n  esac\n}\n'
_WRAPPED = re.compile(
    r'^omitted_by_incident_policy (check-[\w-]+) \|\| just \1 \|\| failed="\$failed \1"$',
    re.MULTILINE,
)

# Both flags share this prefix (`..._REVERT` is the second).
_INCIDENT_FLAG = "EXPEDITED_INCIDENT_RESPONSE"

_GATE_STEP = {
    "name": "All required checks passed",
    "if": "${{ contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled') }}",
    "run": "exit 1",
}
_GATE_REPORT_IF = (
    "${{ needs.incident-ci.result == 'success' && needs.incident-ci.outputs.omitted != '' }}"
)
_GATE_REPORT_ENV = {"OMITTED": "${{ needs.incident-ci.outputs.omitted }}"}


def _released_aggregate() -> dict[str, Any]:
    """The aggregate the entrance prints for a PR whose authority the observer confirms."""
    targets = load_inventory()
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
        targets=targets,
        authority=authority,
        trust=CiTrust(current=lambda _authority: True, observer=lambda _authority, _event: True),
        environ={},
    )
    assert isinstance(plan, CiPlan)
    aggregate = aggregate_ci_results(
        plan=plan,
        current_event=event,
        outcomes=tuple(
            CiOutcome(name=t.name, head_sha=event.head_sha, scope=plan.scope, outcome="passed")
            for t in plan.selected
        ),
        targets=targets,
        observer_arm_admitted=lambda _authority, _event: True,
    )
    assert isinstance(aggregate, CiAggregate)
    return {"status": "passed" if aggregate.successful else "failed", **asdict(aggregate)}


def _projected(*, run: str) -> str:
    """What the workflow's own projection prints for the released aggregate.

    The program is lifted out of the committed step and executed, so the test
    holds what the step computes, not how it is spelled.
    """
    program = "\n".join(_PROJECTION.findall(run))
    printed = io.StringIO()
    aggregate = io.StringIO(json.dumps(_released_aggregate(), sort_keys=True))
    with patch.object(sys, "stdin", aggregate), contextlib.redirect_stdout(printed):
        exec(program, {})  # noqa: S102 — the committed workflow's own one-line program.
    return printed.getvalue().strip()


def _flag_findings(*, source: str) -> list[str]:
    """The workflow sets neither incident flag: no job inherits one from it."""
    if _INCIDENT_FLAG in source:
        return [f"the workflow itself names the {_INCIDENT_FLAG} flag"]
    return []


def _writer_findings(*, jobs: dict[str, Any]) -> list[str]:
    """`omitted` has one writer, after the released aggregate passed, with the right list."""
    findings: list[str] = []
    incident = jobs[_INCIDENT_JOB]
    if incident.get("outputs") != {"omitted": "${{ steps.entrance.outputs.omitted }}"}:
        findings.append(f"job {_INCIDENT_JOB} does not publish exactly the entrance step's output")
    writers = [
        (name, step.get("id"))
        for name, job in jobs.items()
        for step in job["steps"]
        if "omitted=" in step.get("run", "")
    ]
    if writers != [(_INCIDENT_JOB, "entrance")]:
        findings.append(f"`omitted` is written outside the released entrance step: {writers}")
    run = "\n".join(step.get("run", "") for step in incident["steps"])
    if not 0 <= run.find(_PASS_CHECK) < run.find(_WRITE):
        findings.append("`omitted` is not written only after the released aggregate passed")
    expected = sorted(member for members in _OMITTED_BY_JOB.values() for member in members)
    if _projected(run=run) != json.dumps(expected):
        findings.append("the entrance step projects a different omission list")
    return findings


def _bystander_findings(*, jobs: dict[str, Any]) -> list[str]:
    """A job holding no deferred member never reads the omission list."""
    bystanders = _ALL_JOBS - set(_OMITTED_BY_JOB) - {_INCIDENT_JOB, _GATE_JOB}
    return [
        f"job {name} holds no deferred member but references the omission list"
        for name in sorted(bystanders)
        if "omitted" in json.dumps(jobs[name])
    ]


def _gate_findings(*, gate: dict[str, Any]) -> list[str]:
    """`ci-green` requires the same jobs, keeps its gate and repeats the list."""
    findings: list[str] = []
    if set(gate.get("needs", [])) != _REQUIRED or gate.get("if") != "always()":
        findings.append(f"{_GATE_JOB} no longer requires exactly the same jobs on every run")
    steps = gate["steps"]
    if steps[-1] != _GATE_STEP:
        findings.append(f"the failure gate of {_GATE_JOB} changed")
    report = steps[0]
    if (
        len(steps) != 2
        or (report.get("if"), report.get("env")) != (_GATE_REPORT_IF, _GATE_REPORT_ENV)
        or "omitted-by-incident-policy" not in report.get("run", "")
    ):
        findings.append(f"{_GATE_JOB} does not repeat the released omission list")
    return findings


def _job_findings(*, name: str, job: dict[str, Any]) -> list[str]:
    """A job that reads the output needs `incident-ci` and can be skipped by nothing."""
    findings: list[str] = []
    if _INCIDENT_JOB not in job.get("needs", []):
        findings.append(f"job {name} does not read the {_INCIDENT_JOB} job's output")
    if job.get("if") not in _RUN_STATUS_ONLY:
        findings.append(f"job {name} can be skipped, or is conditioned on more than run status")
    return findings


def _does_member_work(*, step: dict[str, Any]) -> bool:
    """Whether a step runs the member or moves its artifact."""
    moves_artifact = step.get("uses", "").startswith(
        ("actions/upload-artifact", "actions/download-artifact")
    )
    return moves_artifact or "just " in step.get("run", "")


def _single_member_findings(*, name: str, job: dict[str, Any], member: str) -> list[str]:
    """The member's steps carry the guard; one explicit report carries its inverse."""
    guard = _GUARD.format(member=member)
    run_if, report_if = "${{ !(" + guard + ") }}", "${{ " + guard + " }}"
    # A step that must also run after a failed step, such as the flake-retry upload, needs
    # !cancelled(). It still carries the same guard, so an omitted member moves no artifact.
    run_after_failure_if = "${{ !cancelled() && !(" + guard + ") }}"
    findings: list[str] = []
    reports = 0
    for step in job["steps"]:
        condition = step.get("if")
        if _does_member_work(step=step):
            if condition not in (run_if, run_after_failure_if):
                findings.append(
                    f"job {name}: step {step['name']!r} does the member's work "
                    f"without the released-aggregate guard"
                )
        elif condition == report_if and "omitted-by-incident-policy" in step.get("run", ""):
            reports += 1
        elif condition is not None:
            findings.append(f"job {name}: step {step['name']!r} carries an unrecognised condition")
    if reports != 1:
        findings.append(f"job {name} does not report an omitted member explicitly, exactly once")
    return findings


def _batch_findings(*, job: dict[str, Any]) -> list[str]:
    """The batch reports exactly the deferred members, line by line, and runs the rest."""
    findings: list[str] = []
    if any("if" in step for step in job["steps"]):
        findings.append(f"job {_BATCH_JOB} conditions a whole step")
    batch = job["steps"][-1]
    if batch.get("env", {}).get("OMITTED_BY_INCIDENT_POLICY") != _BATCH_ENV:
        findings.append(f"job {_BATCH_JOB} reads its omission list from somewhere else")
    run = batch["run"]
    if _BATCH_FUNCTION not in run or _BATCH_FUNCTION_TAIL not in run:
        findings.append(f"job {_BATCH_JOB} tests a member differently from the committed test")
    wrapped = _WRAPPED.findall(run)
    if set(wrapped) != _OMITTED_BY_JOB[_BATCH_JOB] or run.count(
        "omitted_by_incident_policy "
    ) != len(wrapped):
        findings.append(f"job {_BATCH_JOB} wraps a different member set: {sorted(wrapped)}")
    return findings


def omission_findings(*, source: str) -> list[str]:
    """Every way the workflow text fails the incident omission wiring."""
    jobs = yaml.safe_load(source)["jobs"]
    if set(jobs) != _ALL_JOBS:
        return [f"the workflow's job set changed: {sorted(set(jobs) ^ _ALL_JOBS)}"]
    findings = (
        _flag_findings(source=source)
        + _writer_findings(jobs=jobs)
        + _bystander_findings(jobs=jobs)
        + _gate_findings(gate=jobs[_GATE_JOB])
        + _job_findings(name=_BATCH_JOB, job=jobs[_BATCH_JOB])
        + _batch_findings(job=jobs[_BATCH_JOB])
    )
    for name, member in _SINGLE_MEMBER_JOBS.items():
        findings += _job_findings(name=name, job=jobs[name])
        findings += _single_member_findings(name=name, job=jobs[name], member=member)
    return findings


def _mutated(*, source: str, old: str, new: str) -> str:
    """Replace exactly one occurrence, so a mutation never lands twice or nowhere."""
    assert source.count(old) == 1, old
    return source.replace(old, new)


def test_committed_ci_yml_omits_only_through_the_released_aggregate() -> None:
    assert omission_findings(source=_CI_YML.read_text(encoding="utf-8")) == []


def test_the_guarded_members_are_the_ones_the_controller_defers_for_coverage_or_spec() -> None:
    aggregate = _released_aggregate()
    assert aggregate["status"] == "passed"
    assert set(aggregate["passed"]) == {"check-format", "check-lint"}
    job_of = {target.name: target.batch for target in load_inventory()}
    deferred: dict[str, set[str]] = {}
    for deferral in aggregate["deferred"]:
        if deferral["reason"] in _OMITTING_REASONS:
            deferred.setdefault(job_of[deferral["name"]], set()).add(deferral["name"])
    assert deferred == _OMITTED_BY_JOB
    assert {deferral["reason"] for deferral in aggregate["deferred"]} == _OMITTING_REASONS | {
        "incident-policy:unclassified"
    }


_GUARD_OF_PER_FILE_COVERAGE = _GUARD.format(member="'check-per-file-coverage'")


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "\n  export-telemetry:\n",
            "\n  export-telemetry-renamed:\n",
            "the workflow's job set changed: ['export-telemetry', 'export-telemetry-renamed']",
        ),
        (
            'env:\n  UV_HTTP_RETRIES: "5"\n',
            f'env:\n  UV_HTTP_RETRIES: "5"\n  {_INCIDENT_FLAG}_REVERT: "1"\n',
            f"the workflow itself names the {_INCIDENT_FLAG} flag",
        ),
        (
            "      omitted: ${{ steps.entrance.outputs.omitted }}\n",
            "      omitted: ${{ steps.select.outputs.omitted }}\n",
            f"job {_INCIDENT_JOB} does not publish exactly the entrance step's output",
        ),
        (
            '          echo "block=${block}" >> "$GITHUB_OUTPUT"\n',
            '          echo "block=${block}" >> "$GITHUB_OUTPUT"\n'
            '          echo "omitted=[\\"check-coverage\\"]" >> "$GITHUB_OUTPUT"\n',
            "`omitted` is written outside the released entrance step: "
            "[('incident-ci', 'select'), ('incident-ci', 'entrance')]",
        ),
        (
            'aggregate="$("${entrance[@]}" aggregate --repo "$PWD" --reports tmp/incident-ci)"',
            'aggregate="$("${entrance[@]}" plan --repo "$PWD")"',
            "`omitted` is not written only after the released aggregate passed",
        ),
        (
            '"incident-policy:spec"))))\'',
            '"incident-policy:unclassified"))))\'',
            "the entrance step projects a different omission list",
        ),
        (
            "      - name: Run the batched python checks\n        run: |\n",
            "      - name: Run the batched python checks\n"
            "        if: ${{ needs.incident-ci.outputs.omitted == '' }}\n        run: |\n",
            "job check-python-batch holds no deferred member but references the omission list",
        ),
        (
            f"check-metadata-batch, {_INCIDENT_JOB}]\n    if: always()",
            f"{_INCIDENT_JOB}]\n    if: always()",
            f"{_GATE_JOB} no longer requires exactly the same jobs on every run",
        ),
        (
            " || contains(needs.*.result, 'cancelled') }}\n        run: exit 1",
            " }}\n        run: exit 1",
            f"the failure gate of {_GATE_JOB} changed",
        ),
        (
            f"        if: {_GATE_REPORT_IF}\n",
            "        if: ${{ needs.incident-ci.outputs.omitted != '' }}\n",
            f"{_GATE_JOB} does not repeat the released omission list",
        ),
        (
            "    needs: [incident-ci]\n    if: ${{ !cancelled() }}\n    # The same single variable",
            "    if: ${{ !cancelled() }}\n    # The same single variable",
            f"job check-metadata does not read the {_INCIDENT_JOB} job's output",
        ),
        (
            f"    if: {_RUN_STATUS_ONLY[1]}\n",
            "    if: ${{ needs.incident-ci.outputs.omitted == '[]' }}\n",
            "job check-coverage can be skipped, or is conditioned on more than run status",
        ),
        (
            "      - name: Publish .coverage for the check-coverage consumer\n"
            "        if: ${{ !(" + _GUARD_OF_PER_FILE_COVERAGE + ") }}\n",
            "      - name: Publish .coverage for the check-coverage consumer\n"
            "        if: ${{ !contains(github.event.pull_request.labels.*.name, "
            "'expedited-incident-response') }}\n",
            "job check-per-file-coverage: step 'Publish .coverage for the check-coverage "
            "consumer' does the member's work without the released-aggregate guard",
        ),
        (
            "      - name: Publish the flake-retry records for the host-side reader\n"
            "        if: ${{ !cancelled() && !(" + _GUARD_OF_PER_FILE_COVERAGE + ") }}\n",
            "      - name: Publish the flake-retry records for the host-side reader\n"
            "        if: ${{ !cancelled() }}\n",
            "job check-per-file-coverage: step 'Publish the flake-retry records for the "
            "host-side reader' does the member's work without the released-aggregate guard",
        ),
        (
            "      - name: Checkout\n        uses: actions/checkout@v5\n        with:\n"
            "          # Full history for ALL matrix entries",
            "      - name: Checkout\n        if: ${{ vars.LIVESPEC_INCIDENT_OMIT != 'true' }}\n"
            "        uses: actions/checkout@v5\n        with:\n"
            "          # Full history for ALL matrix entries",
            "job check-metadata: step 'Checkout' carries an unrecognised condition",
        ),
        (
            "        if: ${{ " + _GUARD_OF_PER_FILE_COVERAGE + " }}\n",
            "        if: ${{ env.OMITTED_BY_INCIDENT_POLICY == 'true' }}\n",
            "job check-per-file-coverage does not report an omitted member explicitly, "
            "exactly once",
        ),
        (
            "      - name: Run the batched metadata checks\n        env:\n",
            "      - name: Run the batched metadata checks\n"
            "        if: ${{ needs.incident-ci.outputs.omitted == '' }}\n        env:\n",
            f"job {_BATCH_JOB} conditions a whole step",
        ),
        (
            f"          OMITTED_BY_INCIDENT_POLICY: {_BATCH_ENV}\n",
            "          OMITTED_BY_INCIDENT_POLICY: ${{ vars.LIVESPEC_INCIDENT_OMIT }}\n",
            f"job {_BATCH_JOB} reads its omission list from somewhere else",
        ),
        (
            "              *) return 1 ;;\n",
            "              *) return 0 ;;\n",
            f"job {_BATCH_JOB} tests a member differently from the committed test",
        ),
        (
            "omitted_by_incident_policy check-no-todo-registry || just check-no-todo-registry",
            "just check-no-todo-registry",
            f"job {_BATCH_JOB} wraps a different member set: "
            "['check-heading-coverage', 'check-heading-coverage-debt-register']",
        ),
        (
            "          just check-shell-quality ||",
            "          omitted_by_incident_policy check-shell-quality || true ||",
            f"job {_BATCH_JOB} wraps a different member set: ['check-heading-coverage', "
            "'check-heading-coverage-debt-register', 'check-no-todo-registry']",
        ),
    ],
)
def test_each_rule_has_a_negative_control(*, old: str, new: str, expected: str) -> None:
    source = _mutated(source=_CI_YML.read_text(encoding="utf-8"), old=old, new=new)
    assert expected in omission_findings(source=source)
