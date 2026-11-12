"""Execution coverage for the shared delegated pre-push reuse entry point."""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog
from returns.io import IOSuccess
from returns.result import Failure, Success

from livespec_dev_tooling import pre_push_reuse
from livespec_dev_tooling.check_purity import PurityAudit
from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun, GateCommandResult


def _audit() -> IOSuccess[PurityAudit]:
    """A check set whose live and pure members demonstrate the selection rule."""
    return IOSuccess(
        PurityAudit(tree_pure=("check-a", "check-c"), world_reading=("check-b",), undeclared=())
    )


def test_reuse_runs_uncovered_and_live_members_then_reports_skips(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A covered world-reading member still runs alongside an uncovered pure one."""
    invoked: list[list[str]] = []
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1", "check-a", "check-b"),
    )
    monkeypatch.setattr(
        pre_push_reuse.check_purity, "audit_check_purity", lambda **_kwargs: _audit()
    )
    monkeypatch.setattr(
        pre_push_reuse.check_authority,
        "repository_authority_members",
        lambda **_kwargs: IOSuccess(()),
    )

    def successful_runner(**kwargs: object) -> Success[GateCommandResult]:
        invoked.append(kwargs["argv"])
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))

    monkeypatch.setattr(pre_push_reuse, "default_gate_command_runner", successful_runner)

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a", "check-b", "check-c"], log=structlog.get_logger("test")
        )
        == 0
    )
    assert invoked == [["just", "check-b"], ["just", "check-c"]]
    assert capsys.readouterr().out == (
        "pre-push reuse: accepted gate Job job-1 for tree tree-1\n"
        "pre-push reuse: running member check-b on the pushing host\n"
        "pre-push reuse: running member check-c on the pushing host\n"
        "pre-push reuse: skipped 1 member(s) the verdict covered\n"
    )


def test_reuse_names_a_member_that_cannot_run(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A local member failure rejects the push rather than allowing a partial verdict."""
    monkeypatch.setattr(pre_push_reuse, "accepted_lines", lambda **_kwargs: ("job-1", "tree-1"))
    monkeypatch.setattr(
        pre_push_reuse.check_purity, "audit_check_purity", lambda **_kwargs: _audit()
    )
    monkeypatch.setattr(
        pre_push_reuse.check_authority,
        "repository_authority_members",
        lambda **_kwargs: IOSuccess(()),
    )
    monkeypatch.setattr(
        pre_push_reuse,
        "default_gate_command_runner",
        lambda **_kwargs: Failure(GateCommandNotRun(argv=("just", "check-a"), detail="missing")),
    )

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a"], log=structlog.get_logger("test")
        )
        == 1
    )


def test_no_evidence_requests_the_normal_gate_and_keeps_evidence_protocol_empty(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A miss performs neither host checks nor a gate Job itself."""
    monkeypatch.setattr(pre_push_reuse, "accepted_lines", lambda **_kwargs: None)

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a"], log=structlog.get_logger("test")
        )
        == pre_push_reuse.CONTINUE_WITH_OWN_GATE
    )
    assert (
        pre_push_reuse.run_pre_push_command(
            command=pre_push_reuse.PRE_PUSH_REUSE,
            cwd=Path(),
            targets=["check-a"],
            log=structlog.get_logger("test"),
        )
        == pre_push_reuse.CONTINUE_WITH_OWN_GATE
    )
    assert (
        pre_push_reuse.run_pre_push_command(
            command=pre_push_reuse.PRE_PUSH_EVIDENCE,
            cwd=Path(),
            targets=[],
            log=structlog.get_logger("test"),
        )
        == 1
    )
    assert capsys.readouterr().out == ""
