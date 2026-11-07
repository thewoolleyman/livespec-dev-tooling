"""The incident observer is registered on every leaf job `ci-green` needs, not the aggregate.

Work-item livespec-dev-tooling-hudte3 (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm; research note 006, blocker P0-2). The
observer acts only on a `workflow_job` callback whose job name is in the
registration's `required_jobs`, and the registration takes that list from the
released-installation manifest, which the `incident_observer` role renders from
`incident_observer_required_jobs`. With the aggregate alone in that list the
revert waited for `ci-green`, and `ci-green` (`if: always()` over every gating
job) concludes only after the whole run. The list is therefore every leaf job
and matrix leg `ci-green` needs, spelled as the `workflow_job` event reports it,
plus `ci-green` itself as the backstop for a run that fails the aggregate
through a conclusion no leaf callback acts on (a cancelled leg).

The spelling rule is GitHub's: a job reports under its `name:`, or its job id
when `name:` is absent, and a matrix job named `${{ matrix.target }}` reports
one job per `target` leg. Measured on master run 42316488005 (2026-11-06),
whose job list was check-lint, check-format, check-types,
check-fleet-conformance, incident-ci, check-python-batch, check-metadata-batch,
check-per-file-coverage, check-red-green-replay,
check-check-coverage-incremental, check-coverage, export-telemetry, ci-green.

The committed workflow and the committed role list are compared here, so a job
added to or removed from `ci-green`'s `needs:` without the matching role change
fails this repository's normal test run and names the job. Each drift shape is
also exercised against a mutated copy of the committed workflow.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from livespec_dev_tooling._incident_observer_types import (
    JobCallback,
    ObserverRegistration,
    RecoveryIntent,
)
from livespec_dev_tooling.incident_observer import admit_observer, handle_job_callback

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "incident_observer"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_AGGREGATE = "ci-green"
_ROLE_KEY = "incident_observer_required_jobs"
_MATRIX_NAME = "${{ matrix.target }}"
_SECRET = b"job-universe-fixture"


def _committed_workflow() -> dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _declared_jobs() -> list[str]:
    defaults = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))
    return list(defaults[_ROLE_KEY])


def _reported_names(*, job_id: str, job: dict[str, Any]) -> list[str]:
    """The names GitHub's `workflow_job` event reports for one workflow job."""
    name = str(job.get("name", job_id))
    if name == _MATRIX_NAME:
        return [str(target) for target in job["strategy"]["matrix"]["target"]]
    assert "${{" not in name, (
        f"job {job_id} reports under the templated name {name!r}, which this "
        "universe cannot spell; teach _reported_names its legs"
    )
    return [name]


def _workflow_universe(workflow: dict[str, Any]) -> list[str]:
    """Every leaf and matrix leg the aggregate needs, then the aggregate itself."""
    jobs: dict[str, dict[str, Any]] = workflow["jobs"]
    aggregate = jobs[_AGGREGATE]
    needs = aggregate["needs"]
    needed = [needs] if isinstance(needs, str) else list(needs)
    leaves = [
        name for job_id in needed for name in _reported_names(job_id=job_id, job=jobs[job_id])
    ]
    return [*leaves, str(aggregate.get("name", _AGGREGATE))]


def _drift(*, universe: list[str], declared: list[str]) -> list[str]:
    """Name every job the role list is missing, carries extra, or repeats."""
    missing = [job for job in universe if job not in declared]
    extra = [job for job in declared if job not in universe]
    repeated = sorted({job for job in declared if declared.count(job) > 1})
    return [
        *(f"missing from {_ROLE_KEY}: {job} (ci-green needs it)" for job in missing),
        *(f"extra in {_ROLE_KEY}: {job} (ci-green does not need it)" for job in extra),
        *(f"repeated in {_ROLE_KEY}: {job}" for job in repeated),
    ]


def _leaves() -> list[str]:
    return [job for job in _workflow_universe(_committed_workflow()) if job != _AGGREGATE]


# --- DoD bullet 1: the registration names every leaf, not the aggregate alone ---


def test_the_registered_universe_is_every_ci_green_leaf_not_the_aggregate_alone() -> None:
    declared = _declared_jobs()
    leaves = _leaves()
    assert leaves, "ci-green needs no leaf job"
    missing = [job for job in leaves if job not in declared]
    assert not missing, f"the observer registration omits the leaves {missing}"
    assert set(declared) - {_AGGREGATE}, "the registration relies on ci-green alone"
    # The role passes the list, entry for entry, to the manifest renderer, and
    # `POST /arm` copies the manifest's list into the registration.
    tasks = _TASKS.read_text(encoding="utf-8")
    assert (
        f"({_ROLE_KEY} | map('regex_replace', '^', '--required-job=') | list)" in tasks
    ), "the role no longer renders its required-job list into the manifest"


@pytest.mark.parametrize(
    ("job_id", "job", "expected"),
    [
        (
            "lint",
            {"name": _MATRIX_NAME, "strategy": {"matrix": {"target": ["a", "b"]}}},
            ["a", "b"],
        ),
        ("gate", {"name": "check-gate"}, ["check-gate"]),
        ("unnamed", {}, ["unnamed"]),
    ],
)
def test_names_are_spelled_as_the_workflow_job_event_reports_them(job_id, job, expected) -> None:
    assert _reported_names(job_id=job_id, job=job) == expected


def test_an_unspellable_templated_name_fails_by_job() -> None:
    with pytest.raises(AssertionError, match="job weird"):
        _ = _reported_names(job_id="weird", job={"name": "${{ matrix.os }}"})


# --- DoD bullet 2: any one failing leaf recovers at once; the run continues ---


def _registration() -> ObserverRegistration:
    return ObserverRegistration(
        repository="thewoolleyman/livespec-dev-tooling",
        incident_item_id="livespec-dev-tooling-incident",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="recovery-controller",
        phase="repair",
        head_sha="a" * 40,
        run_id=42316488005,
        required_jobs=tuple(_declared_jobs()),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical-verified-receipt",
    )


def _callback(
    *, registration: ObserverRegistration, job_id: int, name: str, conclusion: str
) -> JobCallback:
    body = json.dumps(
        {
            "action": "completed",
            "repository": {"full_name": registration.repository},
            "workflow_job": {
                "id": job_id,
                "run_id": registration.run_id,
                "head_sha": registration.head_sha,
                "head_branch": registration.branch,
                "name": name,
                "conclusion": conclusion,
                "status": "completed",
            },
        }
    ).encode()
    return JobCallback(
        body=body,
        signature="sha256=" + hmac.new(_SECRET, body, hashlib.sha256).hexdigest(),
        event="workflow_job",
        delivery_id=f"job-{job_id}",
    )


@pytest.mark.parametrize("leaf", _leaves())
def test_a_failing_leaf_recovers_at_once_while_the_run_continues(tmp_path, leaf) -> None:
    registration = _registration()
    assert (
        admit_observer(
            directory=tmp_path,
            registration=registration,
            expected_generation=None,
            authorize_current=lambda value: value == registration,
            released_controller=lambda tag, revision: (tag, revision) == ("v1.2.3", "b" * 40),
        ).status
        == "admitted"
    )
    recovered: list[RecoveryIntent] = []

    def recover(intent: RecoveryIntent) -> str:
        recovered.append(intent)
        return "revert-sha"

    def deliver(job_id: int, name: str, conclusion: str):
        return handle_job_callback(
            directory=tmp_path,
            delivery=_callback(
                registration=registration, job_id=job_id, name=name, conclusion=conclusion
            ),
            webhook_secret=_SECRET,
            recover=recover,
        )

    others = [job for job in _leaves() if job != leaf]
    # A leaf that passes before the failure is no reason to act.
    assert deliver(1, others[0], "success").status == "ignored"
    first = deliver(2, leaf, "failure")
    assert first.status == "completed", f"failing leaf {leaf} did not recover: {first.reason}"
    assert first.reason == "first failing required leaf emitted recovery"
    assert [intent.completion.job_name for intent in recovered] == [leaf]
    # The rest of the run completes; no later job of it repeats the effect,
    # and the aggregate's own failure arrives after the action already exists.
    for offset, other in enumerate(others, start=3):
        later = deliver(offset, other, "failure")
        assert later.reason == "existing immutable action; no duplicate effect"
    aggregate = deliver(99, _AGGREGATE, "failure")
    assert aggregate.reason == "existing immutable action; no duplicate effect"
    assert len(recovered) == 1


# --- DoD bullet 3: drift between ci-green's needs and the role list is named ---


def test_ci_green_needs_and_the_role_list_agree() -> None:
    findings = _drift(universe=_workflow_universe(_committed_workflow()), declared=_declared_jobs())
    assert not findings, "\n".join(findings)


def _mutated(mutate) -> dict[str, Any]:
    workflow = copy.deepcopy(_committed_workflow())
    mutate(workflow["jobs"])
    return workflow


def _add_job(jobs: dict[str, Any]) -> None:
    jobs["check-new-gate"] = {"name": "check-new-gate", "runs-on": "ubuntu-latest"}
    jobs[_AGGREGATE]["needs"] = [*jobs[_AGGREGATE]["needs"], "check-new-gate"]


def _add_leg(jobs: dict[str, Any]) -> None:
    targets = jobs["check-python"]["strategy"]["matrix"]["target"]
    jobs["check-python"]["strategy"]["matrix"]["target"] = [*targets, "check-new-leg"]


def _drop_job(jobs: dict[str, Any]) -> None:
    jobs[_AGGREGATE]["needs"] = [
        job for job in jobs[_AGGREGATE]["needs"] if job != "check-python-batch"
    ]


@pytest.mark.parametrize(
    ("mutate", "finding"),
    [
        (_add_job, f"missing from {_ROLE_KEY}: check-new-gate"),
        (_add_leg, f"missing from {_ROLE_KEY}: check-new-leg"),
        (_drop_job, f"extra in {_ROLE_KEY}: check-python-batch"),
    ],
)
def test_a_needs_change_without_the_role_change_names_the_job(mutate, finding) -> None:
    findings = _drift(universe=_workflow_universe(_mutated(mutate)), declared=_declared_jobs())
    assert any(line.startswith(finding) for line in findings), findings


def test_a_repeated_role_entry_is_named() -> None:
    universe = ["check-a", _AGGREGATE]
    assert _drift(universe=universe, declared=["check-a", "check-a", _AGGREGATE]) == [
        f"repeated in {_ROLE_KEY}: check-a"
    ]


def test_a_scalar_needs_is_one_job() -> None:
    workflow = {"jobs": {_AGGREGATE: {"needs": "only"}, "only": {"name": "only"}}}
    assert _workflow_universe(workflow) == ["only", _AGGREGATE]
