"""Consumer-tier: the Kueue admission wait of a delegated gate Job.

Covers the two scenarios in `SPECIFICATION/scenarios.md` that the "Admission wait"
bullet of the delegated pre-push gate contract in `SPECIFICATION/contracts.md`
governs: a Job suspended awaiting Kueue admission does not spend the poll budget,
and a Job never admitted within the admission bound ends the run without a verdict
and is deleted.

NOTHING HERE REACHES A CLUSTER. The gate client's only door to the world is its
`GateCommandRunner`, so a canned runner IS the cluster, and the sleeper is a no-op,
so the bounds are exercised as poll counts and never as elapsed time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from returns.result import Success

from livespec_dev_tooling.gate_credential import GATES_KUBECONFIG_ENV, GATES_WRAPPER
from livespec_dev_tooling.gate_remote_delegate import run_delegated_gate
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_request import GateRunRequest
from livespec_dev_tooling.gate_remote_verdict import GATE_NO_VERDICT, GATE_PASSED

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RENDERER = Path("/opt/gates/render-gate-job.sh")
_JOB = "gate-widget-7f2qd"
_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n"
_CREATED = json.dumps({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB}})
_SUSPENDED = json.dumps({"spec": {"suspend": True}, "status": {}})
_RUNNING = json.dumps({"spec": {"suspend": False}, "status": {}})
_COMPLETE = json.dumps(
    {
        "spec": {"suspend": False},
        "status": {"conditions": [{"type": "Complete", "status": "True"}]},
    }
)


class _KueueCluster:
    """A cluster whose Job stays suspended for `suspended_polls` reads, then runs."""

    def __init__(self, *, suspended_polls: int, running_polls: int) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self.reads = 0
        self._suspended_polls = suspended_polls
        self._running_polls = running_polls

    def __call__(
        self, *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        _ = (cwd, stdin, stream)
        self.argvs.append(tuple(argv))
        return Success(GateCommandResult(returncode=0, stdout=self._answer(argv=argv), stderr=""))

    def _answer(self, *, argv: list[str]) -> str:
        if argv[0] == GATES_WRAPPER:
            if "create" in argv:
                return _CREATED
            if "get" in argv and "job" in argv:
                return self._read_job()
            return ""
        if "rev-parse" in argv:
            return f"{_TREE}\n"
        if argv[0] == str(_RENDERER):
            return _MANIFEST
        return ""

    def _read_job(self) -> str:
        self.reads += 1
        if self.reads <= self._suspended_polls:
            return _SUSPENDED
        if self.reads <= self._suspended_polls + self._running_polls:
            return _RUNNING
        return _COMPLETE

    def issued(self, *, needle: str) -> list[tuple[str, ...]]:
        return [argv for argv in self.argvs if needle in argv]


def _no_sleep(*, seconds: float) -> None:
    _ = seconds


def _a_delegating_host(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "widget"
    repo.mkdir()
    _ = (repo / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_gate = true\n", encoding="utf-8"
    )
    credential = tmp_path / "gates.kubeconfig"
    _ = credential.write_text("kind: Config\napiVersion: v1\n", encoding="utf-8")
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(credential))
    return repo


def _bounds() -> tuple[int, int]:
    request = GateRunRequest(
        repo_root=Path("/repo"), mirror_url="ssh://m/r.git", manifest="", gate_ref="refs/gates/t"
    )
    return request.admission_poll_budget(), request.poll_budget()


def test_a_jobs_kueue_admission_wait_does_not_consume_its_poll_budget(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: a delegated gate Job's Kueue admission wait does not consume its poll budget.

    The Job is suspended for most of the admission bound and then runs for most of
    the poll budget. The two together are more reads than the poll budget alone
    allows, so a client that charged the queue time to the poll budget would give
    up on this Job; the client reports the Job's green verdict instead.
    """
    repo = _a_delegating_host(tmp_path=tmp_path, monkeypatch=monkeypatch)
    admission_polls, poll_budget = _bounds()
    suspended, running = admission_polls - 10, poll_budget - 10
    assert suspended + running > poll_budget
    cluster = _KueueCluster(suspended_polls=suspended, running_polls=running)

    verdict = run_delegated_gate(
        repo_root=repo, renderer=_RENDERER, runner=cluster, sleeper=_no_sleep
    )

    assert verdict.state == GATE_PASSED
    assert verdict.refuses_push is False
    assert cluster.reads == suspended + running + 1
    assert not cluster.issued(needle="delete")


def test_a_job_never_admitted_within_the_admission_bound_ends_without_a_verdict_and_is_deleted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: a delegated gate Job never admitted within the admission bound ends without a verdict.

    The Job is suspended past the admission bound. The run has no verdict, its
    output names the Job and says that it was not admitted, the push is refused,
    and the client deletes the Job before it returns. The wait ends at the
    admission bound, well short of what the poll budget would have allowed.
    """
    repo = _a_delegating_host(tmp_path=tmp_path, monkeypatch=monkeypatch)
    admission_polls, poll_budget = _bounds()
    assert admission_polls < poll_budget
    cluster = _KueueCluster(suspended_polls=poll_budget * 2, running_polls=0)

    verdict = run_delegated_gate(
        repo_root=repo, renderer=_RENDERER, runner=cluster, sleeper=_no_sleep
    )

    assert verdict.state == GATE_NO_VERDICT
    assert verdict.refuses_push is True
    assert _JOB in verdict.detail
    assert "not admitted" in verdict.detail
    assert cluster.reads == admission_polls
    deletes = cluster.issued(needle="delete")
    assert len(deletes) == 1
    assert deletes[0][-3:] == ("delete", "job", _JOB)
