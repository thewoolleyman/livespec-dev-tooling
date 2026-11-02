"""Operational branches of the delegated pre-commit hook seam."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

__all__: list[str] = []


def _module() -> object:
    """Load the module through the public package namespace."""
    return importlib.import_module("livespec_dev_tooling.pre_commit_delegate")


def _enabled_repo(*, root: Path) -> None:
    """Configure one repository that selects pre-commit delegation."""
    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )


def test_unreadable_staged_tree_falls_back_to_the_local_aggregate(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-commit hook must keep gating when it cannot name its index tree."""
    module = _module()
    _enabled_repo(root=tmp_path)
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "")

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.tree_hash is None
    assert "staged tree could not be read" in verdict.reason


def test_malformed_opt_in_and_git_publication_helpers_fail_closed_to_local(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed opt-in and unreadable git commands never authorise delegation."""
    from returns.result import Failure, Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun, GateCommandResult
    from livespec_dev_tooling.gate_remote_verdict import GATE_NO_VERDICT, GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text("[tool.livespec_dev_tooling\n", encoding="utf-8")

    assert module.run_pre_commit(repo_root=tmp_path).local is True
    _enabled_repo(root=tmp_path)
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Failure(
            GateCommandNotRun(argv=("render",), detail="renderer unavailable")
        ),
    )

    monkeypatch.setattr(
        module,
        "default_gate_command_runner",
        lambda **_kwargs: Success(
            GateCommandResult(returncode=0, stdout="a" * 40 + "\n", stderr="")
        ),
    )
    assert module.run_pre_commit(repo_root=tmp_path).local is True

    calls = 0

    def tree_then_uncommittable(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            return Success(GateCommandResult(returncode=0, stdout="a" * 40 + "\n", stderr=""))
        return Failure(GateCommandNotRun(argv=("git",), detail="not found"))

    monkeypatch.setattr(module, "default_gate_command_runner", tree_then_uncommittable)
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Success(
            GateRunRequest(
                repo_root=tmp_path,
                mirror_url="mirror",
                manifest="manifest",
                gate_ref="refs/gates/tree",
            )
        ),
    )
    assert module.run_pre_commit(repo_root=tmp_path).local is True

    monkeypatch.setattr(
        module,
        "default_gate_command_runner",
        lambda **_kwargs: Success(
            GateCommandResult(returncode=0, stdout="a" * 40 + "\n", stderr="")
        ),
    )
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=GATE_NO_VERDICT,
            detail="no verdict",
            token_written=False,
            tree_hash="a" * 40,
        ),
    )
    assert module.run_pre_commit(repo_root=tmp_path).local is True

    monkeypatch.setattr(
        module,
        "default_gate_command_runner",
        lambda **_kwargs: Failure(GateCommandNotRun(argv=("git",), detail="not found")),
    )
    assert module.run_pre_commit(repo_root=tmp_path).local is True


def test_unsubmitted_or_uncommittable_tree_falls_back_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither renderer refusal nor a missing source commit may refuse a commit."""
    from returns.result import Failure, Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_invocation import GateStepFailed

    module = _module()
    _enabled_repo(root=tmp_path)
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Failure(
            GateStepFailed(step="render", argv=(), returncode=1, detail="renderer refused")
        ),
    )

    refused = module.run_pre_commit(repo_root=tmp_path)

    assert refused.local is True
    assert refused.tree_hash == "a" * 40
    assert "could not be submitted" in refused.reason

    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Success(
            GateRunRequest(
                repo_root=tmp_path,
                mirror_url="mirror",
                manifest="manifest",
                gate_ref="refs/gates/tree",
            )
        ),
    )
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "")

    uncommittable = module.run_pre_commit(repo_root=tmp_path)

    assert uncommittable.local is True
    assert "could not be committed" in uncommittable.reason


def test_a_matching_failed_job_refuses_the_commit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A red verdict for the actual staged tree remains a refusal."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_FAILED, GateVerdict

    module = _module()
    _enabled_repo(root=tmp_path)
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Success(
            GateRunRequest(
                repo_root=tmp_path,
                mirror_url="mirror",
                manifest="manifest",
                gate_ref="refs/gates/tree",
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=GATE_FAILED,
            detail="failed member check-lint",
            token_written=False,
            job_name="gate-pre-commit-1",
            tree_hash="a" * 40,
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is False
    assert verdict.exit_status == 1
    assert verdict.job_name == "gate-pre-commit-1"


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("local", 75),
        ("passed", 0),
        ("failed", 1),
    ],
)
def test_main_narrates_the_selected_route(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verdict: str,
    expected: int,
) -> None:
    """The shell receives a distinct local-fallback exit status and narration."""
    module = _module()
    routes = {
        "local": module.PreCommitVerdict(local=True, reason="gates kubeconfig is not readable"),
        "passed": module.PreCommitVerdict(
            local=False,
            reason="passed",
            job_name="gate-pre-commit-1",
            tree_hash="a" * 40,
            exit_status=0,
        ),
        "failed": module.PreCommitVerdict(
            local=False,
            reason="failed",
            job_name="gate-pre-commit-1",
            tree_hash="a" * 40,
            exit_status=1,
        ),
    }
    monkeypatch.setattr(module, "run_pre_commit", lambda **_kwargs: routes[verdict])
    monkeypatch.setattr("sys.argv", ["pre_commit_delegate.py", "run"])

    assert module.main() == expected

    output = capsys.readouterr().err
    if verdict == "local":
        assert "GATED_LOCALLY" in output
    else:
        assert "gate-pre-commit-1" in output


def test_main_is_silent_for_a_repository_that_did_not_opt_in(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default local path keeps hook output unchanged."""
    module = _module()
    monkeypatch.setattr(
        module,
        "run_pre_commit",
        lambda **_kwargs: module.PreCommitVerdict(
            local=True,
            reason="delegated_pre_commit is not enabled",
        ),
    )
    monkeypatch.setattr("sys.argv", ["pre_commit_delegate.py", "run"])

    assert module.main() == 75
    assert capsys.readouterr().err == ""
