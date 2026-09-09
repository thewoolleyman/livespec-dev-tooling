"""The delegated gate client's cluster plumbing — R4.S7a.

Every test here runs against a STUBBED cluster: the client's only reach into the
world is its `GateCommandRunner` seam, so a canned runner is the whole host and
the whole cluster. No process is spawned, no mirror is pushed to, no manifest
reaches an API server, and no ref is created anywhere.

TWO PROPERTIES ARE LOAD-BEARING and each is here because its absence would be
SILENT.

The first is the ref cleanup. One gated push creates one ref, and nothing in the
protocol removes it; the mirror's hourly sweep is the SECOND collector precisely
because a client that dies between the push and the verdict leaves its ref
behind. So the deletion is asserted on the success path, on a step that failed,
on a step that RAISED, and on the wait giving up — an orphan ref raises no error
anywhere and is visible only as unbounded growth weeks later.

The second is that this slice does NOT adjudicate. A `Failed` gate comes back
here as an ordinary SUCCESS carrying the terminal state it read, because
deciding pass from fail — and writing the green token on a pass — is S7b's job.
A client that quietly folded "the Job failed" into its own failure track would
leave S7b nothing to interpret and would make a plumbing fault and a red tree
indistinguishable, which is the one distinction the delegation has to keep.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from returns.pipeline import is_successful
from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_client import GateRunRequest, run_gate
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandNotRun,
    GateCommandOutcome,
    GateCommandResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__: list[str] = []


_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_MIRROR = "cwoolley@poweredge-xubuntu:/var/cache/ci-runner/gates-mirror/widget.git"
_JOB = "gate-widget-4b825dc642cb"
_MANIFEST = f"apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: {_JOB}\n"
_REQUEST = GateRunRequest(
    repo_root=Path("/repo"),
    mirror_url=_MIRROR,
    manifest=_MANIFEST,
    job_name=_JOB,
)


def _job_status(*, state: str) -> str:
    """One `kubectl get job --output json` payload, as the API server shapes it.

    A Job that has not finished carries its conditions with `status: "False"` —
    the field is PRESENT and negative rather than absent, so a reader that tests
    only for the type's presence would call a running gate terminal.
    """
    finished = state in {"Complete", "Failed"}
    return json.dumps(
        {"status": {"conditions": [{"type": state, "status": str(finished)}]}},
    )


@dataclass(frozen=True, kw_only=True)
class _Invocation:
    kind: str
    argv: tuple[str, ...]
    stdin: str | None
    stream: bool


def _kind_of(*, argv: Sequence[str]) -> str:
    """Name the plumbing step one argv belongs to, for the assertions below."""
    if "rev-parse" in argv:
        return "read-tree"
    if "--delete" in argv:
        return "delete-ref"
    if "push" in argv:
        return "push-ref"
    if "create" in argv:
        return "submit-job"
    if "logs" in argv:
        return "stream-logs"
    return "get-job"


class _StubCluster:
    """The whole world the client can reach, canned.

    `job_states` is read one poll at a time and its LAST entry repeats, so
    `("Suspended", "Suspended", "Complete")` is a gate that finishes on the third
    poll and `("Suspended",)` is one that never finishes at all.
    """

    def __init__(
        self,
        *,
        job_states: Iterable[str] = ("Complete",),
        fails: Iterable[str] = (),
        never_runs: Iterable[str] = (),
        raises: str | None = None,
        job_status_payload: str | None = None,
    ) -> None:
        self.calls: list[_Invocation] = []
        self.naps: list[float] = []
        self._states = list(job_states)
        self._fails = frozenset(fails)
        self._never_runs = frozenset(never_runs)
        self._raises = raises
        self._job_status_payload = job_status_payload

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = cwd
        kind = _kind_of(argv=argv)
        self.calls.append(_Invocation(kind=kind, argv=tuple(argv), stdin=stdin, stream=stream))
        if kind == self._raises:
            raise RuntimeError("the host went away mid-run")
        if kind in self._never_runs:
            return Failure(GateCommandNotRun(argv=tuple(argv), detail=f"{argv[0]} not on PATH"))
        if kind in self._fails:
            return Success(GateCommandResult(returncode=1, stdout="", stderr=f"{kind} refused\n"))
        return Success(GateCommandResult(returncode=0, stdout=self._stdout(kind=kind), stderr=""))

    def sleep(self, *, seconds: float) -> None:
        self.naps.append(seconds)

    @property
    def kinds(self) -> list[str]:
        return [call.kind for call in self.calls]

    def only(self, *, kind: str) -> _Invocation:
        matches = [call for call in self.calls if call.kind == kind]
        assert len(matches) == 1, f"expected exactly one {kind}, saw {len(matches)}"
        return matches[0]

    def _stdout(self, *, kind: str) -> str:
        if kind == "read-tree":
            return f"{_TREE}\n"
        if kind == "get-job":
            return self._job_status_payload or _job_status(state=self._next_state())
        return ""

    def _next_state(self) -> str:
        if len(self._states) > 1:
            return self._states.pop(0)
        return self._states[0]


def test_the_tree_under_test_is_pushed_to_the_mirror_at_a_ref_named_for_its_tree_hash() -> None:
    """One value names the pushed tree, the served ref, and later the token."""
    cluster = _StubCluster()
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert is_successful(outcome)
    assert cluster.only(kind="read-tree").argv == ("git", "rev-parse", "HEAD^{tree}")
    assert cluster.only(kind="push-ref").argv == (
        "git",
        "push",
        _MIRROR,
        f"HEAD:refs/gates/{_TREE}",
    )
    assert outcome.unwrap().tree_hash == _TREE


def test_the_rendered_job_is_submitted_to_the_cluster_on_stdin() -> None:
    """The manifest is submitted as rendered — this slice does not re-shape it."""
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    submit = cluster.only(kind="submit-job")
    assert submit.stdin == _MANIFEST
    assert submit.argv == ("kubectl", "--namespace", "gates", "create", "--filename", "-")


def test_the_terminal_state_is_awaited_before_the_logs_are_streamed() -> None:
    """A gate is polled until it finishes; the wait is what bounds the return."""
    cluster = _StubCluster(job_states=("Suspended", "Suspended", "Complete"))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert is_successful(outcome)
    assert cluster.kinds == [
        "read-tree",
        "push-ref",
        "submit-job",
        "get-job",
        "get-job",
        "get-job",
        "stream-logs",
        "delete-ref",
    ]
    assert cluster.naps == [_REQUEST.poll_interval_seconds, _REQUEST.poll_interval_seconds]
    assert outcome.unwrap().terminal_state == "Complete"


def test_the_logs_are_streamed_rather_than_captured() -> None:
    """Capturing is exactly what would swallow the log the operator is owed.

    A captured child writes into this process instead of the terminal, so the
    property the log step exists for would be silently absent while every
    assertion about "the command ran" still passed.
    """
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    logs = cluster.only(kind="stream-logs")
    assert logs.stream is True
    assert logs.argv == (
        "kubectl",
        "--namespace",
        "gates",
        "logs",
        f"job/{_JOB}",
        "--all-containers",
        "--follow",
    )


def test_a_failed_gate_comes_back_as_a_raw_terminal_state_rather_than_a_verdict() -> None:
    """S7b decides pass from fail; this slice reports what the cluster said."""
    cluster = _StubCluster(job_states=("Failed",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert is_successful(outcome)
    assert outcome.unwrap().terminal_state == "Failed"
    assert outcome.unwrap().job_name == _JOB


def test_a_non_zero_log_stream_exit_does_not_fail_the_run() -> None:
    """The log stream's exit code is OBSERVATIONAL — it echoes the gate's own."""
    cluster = _StubCluster(fails=("stream-logs",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert is_successful(outcome)
    assert outcome.unwrap().logs_returncode == 1


def test_the_gate_ref_is_deleted_on_the_success_path() -> None:
    """The client is the FIRST collector; the mirror's sweep is the second."""
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert cluster.kinds[-1] == "delete-ref"
    assert cluster.only(kind="delete-ref").argv == (
        "git",
        "push",
        "--delete",
        _MIRROR,
        f"refs/gates/{_TREE}",
    )


def test_the_gate_ref_is_deleted_when_a_step_fails() -> None:
    """A refused submit still owns the ref it pushed a moment earlier."""
    cluster = _StubCluster(fails=("submit-job",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "submit-gate-job"
    assert outcome.failure().returncode == 1
    assert "delete-ref" in cluster.kinds


def test_the_gate_ref_is_deleted_when_a_step_raises() -> None:
    """The path no `Result` covers: a bug, or a host that vanished mid-run."""
    cluster = _StubCluster(raises="get-job")
    with pytest.raises(RuntimeError):
        _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert cluster.kinds[-1] == "delete-ref"


def test_a_gate_that_never_reaches_a_terminal_state_fails_rather_than_polling_forever() -> None:
    """Giving up is a plumbing failure, and it still owns its ref."""
    cluster = _StubCluster(job_states=("Suspended",))
    request = dataclasses.replace(_REQUEST, poll_timeout_seconds=30.0)
    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "await-gate-terminal"
    assert outcome.failure().returncode is None
    assert cluster.kinds.count("get-job") == 3
    assert cluster.kinds[-1] == "delete-ref"


def test_a_job_the_cluster_will_not_report_on_fails_the_wait() -> None:
    """A read that cannot be made is not a gate that has not finished yet."""
    cluster = _StubCluster(fails=("get-job",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "await-gate-terminal"
    assert outcome.failure().detail == "get-job refused\n"


def test_an_unreadable_job_status_fails_the_wait_rather_than_being_guessed() -> None:
    """Neither "finished" nor "still running" may be inferred from nonsense."""
    cluster = _StubCluster(job_status_payload="<html>gateway timeout</html>")
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "await-gate-terminal"
    assert "unreadable job status" in outcome.failure().detail


def test_the_run_fails_when_its_own_ref_cannot_be_deleted() -> None:
    """An orphan ref is reported rather than swallowed by a successful gate."""
    cluster = _StubCluster(fails=("delete-ref",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "delete-gate-ref"


def test_nothing_is_submitted_when_the_ref_could_not_be_pushed() -> None:
    """No ref was created, so there is nothing to collect and nothing to gate."""
    cluster = _StubCluster(fails=("push-ref",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "push-gate-ref"
    assert cluster.kinds == ["read-tree", "push-ref"]


def test_a_tree_hash_that_cannot_be_read_stops_before_the_mirror_is_touched() -> None:
    """`returncode=None` is what says there was no exit code at all."""
    cluster = _StubCluster(never_runs=("read-tree",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "read-tree-hash"
    assert outcome.failure().returncode is None
    assert cluster.kinds == ["read-tree"]
