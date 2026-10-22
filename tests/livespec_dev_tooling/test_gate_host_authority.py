"""The authority-declaring members a delegated push runs on the PUSHING HOST.

The "What the delegated gate runs" bullet of `SPECIFICATION/contracts.md`, in
its delegated pre-push gate section (ratified v082): "The pre-push gate runs it
on the pushing host, with the pushing host's own credentials, against the same
committed tree, before or beside submitting the Job."

WHY BEFORE, AND WHY THROUGH THE SAME SEAM. The members run through the gate
client's own `GateCommandRunner`, which is what lets this file watch a whole
delegated push with no cluster, no mirror and no host touched — and it is the
same seam the cluster steps use, so "the member ran on the pushing host" is
asserted as an INVOCATION in the pushing worktree rather than inferred from a
message. Running them before the Job is submitted is the contract's own
"before or beside": the authority half is the cheap half, and a push that
reaches the cluster has already had its authority read here.

WHAT IS RECORDED IS WHAT THE HOST ANSWERED, per member, including the two
non-answers. A member that EXITED non-zero and a member that could not be RUN
at all are kept apart in the record because the delegated gate's whole
discipline is that a plumbing fault and a real refusal are different facts; and
a declaration the host cannot READ is recorded against the member it names,
never dropped, because a dropped declaration reads as "this member needs no
authority" — which is how the member gets handed back to a pod holding none.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from returns.result import Failure, Success

from livespec_dev_tooling.gate_credential import GATES_WRAPPER
from livespec_dev_tooling.gate_remote_delegate import run_delegated_gate
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandNotRun,
    GateCommandOutcome,
    GateCommandResult,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "_gate_host_authority.py"
_MODULE_NAME = "livespec_dev_tooling._gate_host_authority"

# The empty tree's hash — a real git object name, and the one every canned
# `rev-parse HEAD^{tree}` below answers with.
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RENDERER = Path("/opt/gates/render-gate-job.sh")
_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n"
_CREATED = '{"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": "gate-widget-7f2qd"}}'

# A Job that has reported no condition yet — what a real poll gets while Kueue
# is still admitting the gate — and then the one condition that means the gated
# aggregate exited zero inside the pod. No gate is terminal on its first poll,
# so answering in this order is what exercises the run's wait at all.
_JOB_ADMITTING = '{"status": {}}'
_JOB_COMPLETE = '{"status": {"conditions": [{"type": "Complete", "status": "True"}]}}'

# The repository-private member that declares it reads a ledger-held
# authorization, and the one beside it that declares none.
_DECLARING = "check-widget-approval"
_UNDECLARED = "check-widget-lint"


class _CannedHost:
    """Every command one delegated push issues, answered without a world.

    `member_result` is what `just <member>` answers on the pushing host; a
    `GateCommandNotRun` there is the member that could not be RUN at all, which
    the seam keeps apart from one that ran and exited non-zero.
    """

    def __init__(self, *, member_result: GateCommandOutcome | None = None) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self.cwds: list[Path] = []
        self._member_result = member_result
        self._polls = 0

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (stdin, stream)
        self.argvs.append(tuple(argv))
        self.cwds.append(cwd)
        if argv[0] == "just":
            return self._member_result or Success(
                GateCommandResult(returncode=0, stdout="", stderr="")
            )
        if argv[0] == GATES_WRAPPER:
            return Success(
                GateCommandResult(returncode=0, stdout=self._cluster(argv=tuple(argv)), stderr="")
            )
        if "rev-parse" in argv:
            return Success(GateCommandResult(returncode=0, stdout=f"{_TREE}\n", stderr=""))
        if argv[0] == str(_RENDERER):
            return Success(GateCommandResult(returncode=0, stdout=_MANIFEST, stderr=""))
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))

    def _cluster(self, *, argv: tuple[str, ...]) -> str:
        """The submit's created object, the poll sequence, else nothing.

        Only a POLL advances the sequence. Counting every cluster command would
        let the submit consume the not-admitted-yet answer, and the first poll
        would then read a terminal condition — quietly removing the wait a
        delegated push actually performs.
        """
        if "create" in argv:
            return _CREATED
        if "get" not in argv:
            return ""
        self._polls += 1
        return _JOB_ADMITTING if self._polls == 1 else _JOB_COMPLETE

    def issued(self, *, needle: str) -> list[tuple[str, ...]]:
        """Every command whose argv carries `needle`."""
        return [argv for argv in self.argvs if needle in argv]


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned — the run's only source of time."""
    _ = seconds


def _nothing(**_kwargs: object) -> None:
    """The outcome emitter, canned: a test reads a verdict without a receiver."""


def _ran_on_the_host(*, repo_root: Path, runner: _CannedHost) -> Any:
    """The per-member records one pushing host produced, imported here not at module scope."""
    module = importlib.import_module(_MODULE_NAME)
    return module.run_host_authority_members(repo_root=repo_root, tree_hash=_TREE, runner=runner)


def _a_delegating_repo(*, repo_root: Path, inventory: tuple[str, ...]) -> None:
    """A clone whose check inventory holds exactly `inventory`."""
    _ = (repo_root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_gate = true\n", encoding="utf-8"
    )
    _ = (repo_root / "check-targets.txt").write_text(
        "# Canonical check inventory for `just check`.\n"
        + "".join(f"{line}\n" for line in inventory),
        encoding="utf-8",
    )


def test_a_delegated_push_runs_each_authority_declaring_member_on_the_pushing_host(
    *, tmp_path: Path
) -> None:
    """Scenario Then: the pre-push gate runs that member on the pushing host, at HEAD's tree.

    THREE things in one invocation list, and the third is what makes the first
    two mean anything. The declaring member is invoked as the aggregate invokes
    it, `just <member>`. It is invoked in the PUSHING WORKTREE — the cwd the
    gate client read `HEAD^{tree}` in — which is what "against the same
    committed tree" reduces to on a host, since the worktree's HEAD is the tree
    the Job was handed. And the member declaring NO authority is NOT invoked
    here: it stays in the Job, where the whole aggregate runs, so the exception
    moves exactly one member rather than draining the cluster one member at a
    time.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} must exist to run a member on this host"

    repo = tmp_path / "widget"
    repo.mkdir()
    _a_delegating_repo(
        repo_root=repo, inventory=(f"{_DECLARING}  # authority: ledger", _UNDECLARED)
    )
    host = _CannedHost()

    _ = run_delegated_gate(
        repo_root=repo, renderer=_RENDERER, runner=host, sleeper=_no_sleep, emit=_nothing
    )

    assert host.issued(needle=_DECLARING) == [("just", _DECLARING)]
    assert host.issued(needle=_UNDECLARED) == []
    member_at = host.argvs.index(("just", _DECLARING))
    assert host.cwds[member_at] == repo
    assert _TREE in host.issued(needle="--tree-hash")[0]


def test_each_member_the_pushing_host_ran_is_recorded_with_what_it_answered(
    *, tmp_path: Path
) -> None:
    """A member that exited non-zero and one that could not be run are different facts.

    Both refuse a push, and they are still recorded apart: `returncode` is the
    real exit code for a member that RAN and `None` for one that never did,
    which is the same discrimination `GateStepFailed` keeps for every other step
    of a delegated gate. Collapsing them would make an absent `just` read as a
    member's own refusal, and an operator would go looking for an authorization
    problem that is really an install problem.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} must exist to record what a member answered"

    repo = tmp_path / "widget"
    repo.mkdir()
    _a_delegating_repo(repo_root=repo, inventory=(f"{_DECLARING}  # authority: ledger",))

    passed = _ran_on_the_host(repo_root=repo, runner=_CannedHost())
    refused = _ran_on_the_host(
        repo_root=repo,
        runner=_CannedHost(
            member_result=Success(
                GateCommandResult(returncode=3, stdout="", stderr="no approval label")
            )
        ),
    )
    unrunnable = _ran_on_the_host(
        repo_root=repo,
        runner=_CannedHost(
            member_result=Failure(
                GateCommandNotRun(argv=("just", _DECLARING), detail="just not on PATH")
            )
        ),
    )

    assert [(run.member, run.returncode) for run in passed] == [(_DECLARING, 0)]
    assert passed[0].tree_hash == _TREE
    assert [(run.member, run.returncode) for run in refused] == [(_DECLARING, 3)]
    assert refused[0].detail == "no approval label"
    assert [(run.member, run.returncode) for run in unrunnable] == [(_DECLARING, None)]
    assert unrunnable[0].detail == "just not on PATH"


def test_a_declaration_the_pushing_host_cannot_read_is_recorded_against_its_member(
    *, tmp_path: Path
) -> None:
    """A malformed declaration is the named member's own non-answer, never a dropped row.

    The fail-closed direction, and the only one that is safe: a registry the
    host cannot read must not resolve to "no member needs the pushing host",
    because that answer puts every authority-reading member back inside a pod
    that holds no authority — the state this exception exists to end. So the
    unreadable declaration arrives as a record for the member it names, with no
    exit code, because nothing ran.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} must exist to record an unreadable declaration"

    repo = tmp_path / "widget"
    repo.mkdir()
    _a_delegating_repo(repo_root=repo, inventory=(f"{_DECLARING}  # authority: beads",))
    host = _CannedHost()

    recorded = _ran_on_the_host(repo_root=repo, runner=host)

    assert [(run.member, run.returncode) for run in recorded] == [(_DECLARING, None)]
    assert "ledger" in recorded[0].detail
    assert host.issued(needle="just") == []
