"""Execution coverage for the shared delegated pre-push reuse entry point."""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog
from returns.io import IOFailure, IOSuccess
from returns.result import Failure, Success

from livespec_dev_tooling import pre_push_reuse
from livespec_dev_tooling.check_authority import AuthorityDeclarationMalformed
from livespec_dev_tooling.check_purity import PurityAudit, PurityDeclarationMalformed
from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun, GateCommandResult

_MODULE = Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "pre_push_reuse.py"


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
        raising=False,
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

    monkeypatch.setattr(
        pre_push_reuse,
        "default_gate_command_runner",
        successful_runner,
        raising=False,
    )

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a", "check-b", "check-c"], log=structlog.get_logger("test")
        )
        == 0
    )
    assert invoked == [["just", "check-b"], ["just", "check-c"]]
    assert capsys.readouterr().out == (
        "pre-push reuse: accepted gate Job job-1 for tree tree-1\n"
        "pre-push reuse: skipped 1 member(s) the verdict covered\n"
        "pre-push reuse: running member check-b on the pushing host\n"
        "pre-push reuse: running member check-c on the pushing host\n"
    )


def test_reuse_names_a_member_that_returns_a_failing_status(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A nonzero local member status rejects the push rather than allowing a partial verdict."""
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1"),
        raising=False,
    )
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
        lambda **_kwargs: Success(GateCommandResult(returncode=3, stdout="", stderr="")),
        raising=False,
    )

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a"], log=structlog.get_logger("test")
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "member=check-a" in output
    assert "pre-push reuse: skipped 0 member(s) the verdict covered\n" in output


def test_reuse_prints_the_skipped_count_before_a_failing_member_refuses_the_push(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A covered member is counted even when a later host member fails."""
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1", "check-a"),
        raising=False,
    )
    monkeypatch.setattr(pre_push_reuse, "_host_members", lambda **_kwargs: ())
    monkeypatch.setattr(
        pre_push_reuse,
        "default_gate_command_runner",
        lambda **_kwargs: Success(GateCommandResult(returncode=3, stdout="", stderr="")),
        raising=False,
    )

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a", "check-b"], log=structlog.get_logger("test")
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "pre-push reuse: running member check-b on the pushing host\n" in output
    assert "pre-push reuse: skipped 1 member(s) the verdict covered\n" in output


def test_reuse_names_a_member_that_cannot_start(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A local invocation failure refuses the push and keeps the member name visible."""
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1"),
        raising=False,
    )
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
        raising=False,
    )

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a"], log=structlog.get_logger("test")
        )
        == 1
    )
    assert "member=check-a" in capsys.readouterr().out


def test_reuse_runs_an_authorization_member_even_when_the_verdict_covered_it(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An external authorization remains a pushing-host decision for a reused verdict."""
    invoked: list[list[str]] = []
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1", "check-a", "check-b"),
        raising=False,
    )
    monkeypatch.setattr(
        pre_push_reuse.check_purity, "audit_check_purity", lambda **_kwargs: _audit()
    )
    monkeypatch.setattr(
        pre_push_reuse.check_authority,
        "repository_authority_members",
        lambda **_kwargs: IOSuccess(("check-a",)),
    )

    def successful_runner(**kwargs: object) -> Success[GateCommandResult]:
        invoked.append(kwargs["argv"])
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))

    monkeypatch.setattr(
        pre_push_reuse,
        "default_gate_command_runner",
        successful_runner,
        raising=False,
    )

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a", "check-b"], log=structlog.get_logger("test")
        )
        == 0
    )
    assert invoked == [["just", "check-a"], ["just", "check-b"]]


@pytest.mark.parametrize(
    ("purity", "authority"),
    [
        (
            IOFailure(
                PurityDeclarationMalformed(target="check-a", value="bad", reason="bad purity")
            ),
            IOSuccess(()),
        ),
        (
            _audit(),
            IOFailure(
                AuthorityDeclarationMalformed(target="check-a", value="bad", reason="bad authority")
            ),
        ),
    ],
)
def test_reuse_refuses_a_malformed_member_declaration(
    *,
    monkeypatch: pytest.MonkeyPatch,
    purity: object,
    authority: object,
) -> None:
    """An unreadable host-selection declaration cannot narrow a reused verdict."""
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1", "check-a"),
        raising=False,
    )
    monkeypatch.setattr(pre_push_reuse.check_purity, "audit_check_purity", lambda **_kwargs: purity)
    monkeypatch.setattr(
        pre_push_reuse.check_authority,
        "repository_authority_members",
        lambda **_kwargs: authority,
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
    monkeypatch.setattr(pre_push_reuse, "accepted_lines", lambda **_kwargs: None, raising=False)

    assert (
        pre_push_reuse.run_pre_push_reuse(
            cwd=Path(), targets=["check-a"], log=structlog.get_logger("test")
        )
        == pre_push_reuse.CONTINUE_WITH_OWN_GATE
    )
    assert (
        pre_push_reuse.run_pre_push_command(
            command=pre_push_reuse.PRE_PUSH_EVIDENCE,
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


def test_reuse_refuses_an_empty_consumer_check_set(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """An accepted verdict cannot stand in for a caller that names no members."""
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1", "check-a"),
        raising=False,
    )

    assert (
        pre_push_reuse.run_pre_push_reuse(cwd=Path(), targets=[], log=structlog.get_logger("test"))
        == 1
    )


def test_pre_push_evidence_reuses_a_qualifying_verdict(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The public command owns the host-side half of an accepted verdict."""
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1", "check-a"),
        raising=False,
    )
    monkeypatch.setattr(pre_push_reuse, "_host_members", lambda **_kwargs: ())
    monkeypatch.setattr(
        pre_push_reuse,
        "default_gate_command_runner",
        lambda **_kwargs: Success(GateCommandResult(returncode=0, stdout="", stderr="")),
    )

    assert (
        pre_push_reuse.run_pre_push_command(
            command=pre_push_reuse.PRE_PUSH_EVIDENCE,
            cwd=Path(),
            targets=["check-a"],
            log=structlog.get_logger("test"),
        )
        == 0
    )
    assert capsys.readouterr().out == (
        "pre-push reuse: accepted gate Job job-1 for tree tree-1\n"
        "pre-push reuse: skipped 1 member(s) the verdict covered\n"
    )


def test_pre_push_evidence_runs_an_uncovered_member(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The documented public command executes the host half of a reused verdict."""
    invoked: list[list[str]] = []
    monkeypatch.setattr(
        pre_push_reuse,
        "accepted_lines",
        lambda **_kwargs: ("job-1", "tree-1", "check-a"),
        raising=False,
    )
    monkeypatch.setattr(pre_push_reuse, "_host_members", lambda **_kwargs: ())

    def successful_runner(**kwargs: object) -> Success[GateCommandResult]:
        invoked.append(kwargs["argv"])
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))

    monkeypatch.setattr(pre_push_reuse, "default_gate_command_runner", successful_runner)

    assert (
        pre_push_reuse.run_pre_push_command(
            command=pre_push_reuse.PRE_PUSH_EVIDENCE,
            cwd=Path(),
            targets=["check-a", "check-b"],
            log=structlog.get_logger("test"),
        )
        == 0
    )
    assert invoked == [["just", "check-b"]]
    assert "running member check-b" in capsys.readouterr().out


def test_module_re_import_with_vendor_in_sys_path() -> None:
    """Re-importing with the vendor directory present covers the path guard's false arm."""
    import importlib.util

    first = importlib.util.spec_from_file_location("pre_push_reuse_first_import", str(_MODULE))
    assert first is not None and first.loader is not None
    first_module = importlib.util.module_from_spec(first)
    _ = first.loader.exec_module(first_module)

    second = importlib.util.spec_from_file_location("pre_push_reuse_second_import", str(_MODULE))
    assert second is not None and second.loader is not None
    second_module = importlib.util.module_from_spec(second)
    _ = second.loader.exec_module(second_module)

    assert callable(first_module.run_pre_push_reuse)
    assert callable(second_module.run_pre_push_reuse)
