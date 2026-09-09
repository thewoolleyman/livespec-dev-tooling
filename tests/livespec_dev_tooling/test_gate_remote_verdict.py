"""The delegated gate client's fail-closed verdict and token write — R4.S7b.

Every test here runs against a STUBBED cluster and a STUBBED token writer: the
client's only reach into the world is its `GateCommandRunner` seam, so a canned
runner is the whole host, the whole cluster and the whole `green_token` CLI. No
process is spawned, no manifest reaches an API server, no ref is created, and no
token file is written anywhere.

THE SUBJECT HERE IS THE REFUSAL, NOT THE PASS. One observation authorises a
push — a `Complete` Job over the tree that is still at HEAD, with its token
written — and the suite's weight is on everything else: a red gate, a lost
connection, an API server that cannot be reached, a kubeconfig the server
rejects, a gate that never finished, and a HEAD that moved out from under the
run. Each has to end in a refusal that wrote NOTHING, and the assertion that no
token was written is as load-bearing as the refusal itself: a token is read
later, by a different process, as proof a tree was gated, so a token written on
a shape that never produced a verdict is a fail-open hole that raises no error
at the moment it is created.

The two shapes that pass the gate and STILL refuse — a HEAD that moved, and a
token write that never ran — are the fail-closed direction stated as tests. The
push is authorised by a written token for the GATED tree, never by the verdict
alone, so a client that cannot leave that token behind must not let the push
proceed on the strength of having seen a green one.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_client import GateRunRequest
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandNotRun,
    GateCommandOutcome,
    GateCommandResult,
)
from livespec_dev_tooling.gate_remote_verdict import (
    GATE_FAILED,
    GATE_NO_VERDICT,
    GATE_PASSED,
    run_gated_push,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__: list[str] = []


_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_MOVED_TREE = "9e2f1c8a0d4b6e5f3a7c1d9b8e0f2a4c6d8e0f2a"
_MIRROR = "cwoolley@poweredge-xubuntu:/var/cache/ci-runner/gates-mirror/widget.git"
_JOB = "gate-widget-4b825dc642cb"
_MANIFEST = f"apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: {_JOB}\n"
# A 30s timeout at the default 10s interval buys three polls, so the
# never-finishes case gives up in three stubbed reads rather than 360.
_REQUEST = GateRunRequest(
    repo_root=Path("/repo"),
    mirror_url=_MIRROR,
    manifest=_MANIFEST,
    job_name=_JOB,
    poll_timeout_seconds=30.0,
)
_TOKEN_ARGV = (sys.executable, "-m", "livespec_dev_tooling.green_token", "write")
_READ_TREE_ARGV = ("git", "rev-parse", "HEAD^{tree}")


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned — the client's only source of time."""
    _ = seconds


def _job_status(*, state: str) -> str:
    """One `kubectl get job --output json` payload, as the API server shapes it."""
    finished = state in {"Complete", "Failed"}
    return json.dumps({"status": {"conditions": [{"type": state, "status": str(finished)}]}})


# Marker token → step name, tried IN ORDER: the first marker present in an argv
# names the step, and `get-job` is what is left when none matches. The order is
# load-bearing twice over — the delete argv also carries `push`, and the token
# write is recognised by the INTERPRETER rather than by the module name, because
# "this client shelled out to a python" is a property no cluster step can
# accidentally acquire.
_STEP_MARKERS = (
    (sys.executable, "write-token"),
    ("rev-parse", "read-tree"),
    ("--delete", "delete-ref"),
    ("push", "push-ref"),
    ("create", "submit-job"),
    ("logs", "stream-logs"),
)


def _kind_of(*, argv: Sequence[str]) -> str:
    """Name the step one argv belongs to, for the assertions below."""
    for marker, kind in _STEP_MARKERS:
        if marker in argv:
            return kind
    return "get-job"


@dataclass(frozen=True, kw_only=True)
class _Invocation:
    kind: str
    argv: tuple[str, ...]
    cwd: Path


class _StubCluster:
    """The whole world the client can reach, canned.

    `job_state` is the condition every poll reports, so `"Suspended"` is a gate
    that never finishes at all; a gate that finishes on a LATER poll is S7a's
    concern and is exercised there. `head_trees` is read one `rev-parse` at a
    time and its LAST entry repeats, so `(_TREE, _MOVED_TREE)` is a HEAD that
    moved between the gate's read and the client's confirming re-read, and a
    `None` is a read that never happened at all — the seam's did-not-run track
    rather than a bad answer.
    """

    def __init__(
        self,
        *,
        job_state: str = "Complete",
        head_trees: Iterable[str | None] = (_TREE,),
        refusals: Mapping[str, str] | None = None,
        never_runs: Iterable[str] = (),
    ) -> None:
        self.calls: list[_Invocation] = []
        self._job_state = job_state
        self._head_trees = list(head_trees)
        self._refusals = dict(refusals or {})
        self._never_runs = frozenset(never_runs)

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (stdin, stream)
        kind = _kind_of(argv=argv)
        self.calls.append(_Invocation(kind=kind, argv=tuple(argv), cwd=cwd))
        if kind == "read-tree":
            return self._read_tree(argv=argv)
        if kind in self._never_runs:
            return Failure(GateCommandNotRun(argv=tuple(argv), detail=f"{argv[0]} not on PATH"))
        refusal = self._refusals.get(kind)
        if refusal is not None:
            return Success(GateCommandResult(returncode=1, stdout="", stderr=refusal))
        return Success(GateCommandResult(returncode=0, stdout=self._stdout(kind=kind), stderr=""))

    @property
    def kinds(self) -> list[str]:
        return [call.kind for call in self.calls]

    def only(self, *, kind: str) -> _Invocation:
        matches = [call for call in self.calls if call.kind == kind]
        assert len(matches) == 1, f"expected exactly one {kind}, saw {len(matches)}"
        return matches[0]

    def _read_tree(self, *, argv: list[str]) -> GateCommandOutcome:
        tree = self._head_trees.pop(0) if len(self._head_trees) > 1 else self._head_trees[0]
        if tree is None:
            return Failure(GateCommandNotRun(argv=tuple(argv), detail="git not on PATH"))
        return Success(GateCommandResult(returncode=0, stdout=f"{tree}\n", stderr=""))

    def _stdout(self, *, kind: str) -> str:
        if kind == "get-job":
            return _job_status(state=self._job_state)
        return ""


def test_a_green_gate_writes_the_existing_green_token() -> None:
    """The pass calls the EXISTING CLI — there is no second token format here."""
    cluster = _StubCluster()
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_PASSED
    assert verdict.token_written is True
    assert verdict.refuses_push is False
    write = cluster.only(kind="write-token")
    assert write.argv == _TOKEN_ARGV
    assert write.cwd == _REQUEST.repo_root


def test_the_token_is_written_for_the_same_tree_that_named_the_mirror_ref() -> None:
    """ONE value names the pushed tree, the served ref and the token.

    The write is preceded by a second `rev-parse` for exactly that reason: the
    existing CLI re-derives the tree itself, so what it will key the token on is
    confirmed to still be the gated tree BEFORE it is asked to write.
    """
    cluster = _StubCluster()
    _ = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert cluster.only(kind="push-ref").argv[-1] == f"HEAD:refs/gates/{_TREE}"
    assert [call.argv for call in cluster.calls if call.kind == "read-tree"] == [
        _READ_TREE_ARGV,
        _READ_TREE_ARGV,
    ]
    assert cluster.kinds[-2:] == ["read-tree", "write-token"]


def test_a_failed_job_is_never_a_pass_and_refuses_the_push() -> None:
    """A red gate is a REAL verdict, and the one it reports is a refusal."""
    cluster = _StubCluster(job_state="Failed")
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_FAILED
    assert verdict.refuses_push is True
    assert verdict.token_written is False
    assert "write-token" not in cluster.kinds
    assert _JOB in verdict.detail


def test_a_connection_lost_mid_gate_refuses_the_push() -> None:
    """A poll that cannot be answered is not a gate that has not finished yet."""
    cluster = _StubCluster(
        refusals={"get-job": "error: an error on the server: connection reset by peer\n"},
    )
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_NO_VERDICT
    assert verdict.refuses_push is True
    assert verdict.token_written is False
    assert "write-token" not in cluster.kinds
    assert "connection reset by peer" in verdict.detail


def test_an_unreachable_api_server_refuses_the_push() -> None:
    """Nothing was submitted, so nothing was measured — and nothing is written."""
    cluster = _StubCluster(
        refusals={
            "submit-job": (
                "The connection to the server poweredge-xubuntu:6443 was refused - "
                "did you specify the right host or port?\n"
            ),
        },
    )
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_NO_VERDICT
    assert verdict.refuses_push is True
    assert verdict.token_written is False
    assert "write-token" not in cluster.kinds
    assert "was refused" in verdict.detail


def test_a_rejected_kubeconfig_refuses_the_push() -> None:
    """The gates kubeconfig expires at every poweredge reboot, so this is ROUTINE.

    It is also the shape most likely to be read as "the gate is fine, my
    credential is stale, push anyway" — which is why the client's own answer to
    it is identical to its answer to a red gate, and why the reason survives
    into the verdict rather than being flattened to a bare refusal.
    """
    cluster = _StubCluster(
        refusals={"submit-job": "error: You must be logged in to the server (Unauthorized)\n"},
    )
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_NO_VERDICT
    assert verdict.refuses_push is True
    assert verdict.token_written is False
    assert "write-token" not in cluster.kinds
    assert "Unauthorized" in verdict.detail


def test_a_gate_that_never_reached_a_terminal_state_refuses_the_push() -> None:
    """Giving up on a wait decides nothing, and nothing is exactly what it writes."""
    cluster = _StubCluster(job_state="Suspended")
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_NO_VERDICT
    assert verdict.refuses_push is True
    assert verdict.token_written is False
    assert "write-token" not in cluster.kinds


def test_a_head_that_moved_while_the_gate_ran_gets_no_token() -> None:
    """The verdict belongs to the tree it was measured on, and to no other.

    `green_token write` re-derives `HEAD^{tree}` at write time, minutes after
    the gate started. A HEAD that moved in between — an amend, a rebase, a
    commit in the same worktree — would have it mark a tree GREEN THAT WAS
    NEVER GATED, and the existing skip path would then complete a push with no
    aggregate at all. Nothing errors on that path, which is why the guard is
    here rather than left to the CLI.
    """
    cluster = _StubCluster(head_trees=(_TREE, _MOVED_TREE))
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_PASSED
    assert verdict.token_written is False
    assert verdict.refuses_push is True
    assert "write-token" not in cluster.kinds
    assert _MOVED_TREE in verdict.detail


def test_a_head_tree_that_cannot_be_re_read_gets_no_token() -> None:
    """An unanswerable question is not a matching answer."""
    cluster = _StubCluster(head_trees=(_TREE, None))
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_PASSED
    assert verdict.token_written is False
    assert verdict.refuses_push is True
    assert "write-token" not in cluster.kinds


def test_a_token_write_that_never_ran_leaves_the_push_refused() -> None:
    """A pass the client cannot hand on is not a pass the client may act on."""
    cluster = _StubCluster(never_runs=("write-token",))
    verdict = run_gated_push(request=_REQUEST, runner=cluster, sleeper=_no_sleep)
    assert verdict.state == GATE_PASSED
    assert verdict.token_written is False
    assert verdict.refuses_push is True
    assert cluster.only(kind="write-token").argv == _TOKEN_ARGV
