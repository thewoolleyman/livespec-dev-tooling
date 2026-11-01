"""Commit-time replay delegation decisions."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parents[2] / "livespec_dev_tooling" / "commit_replay_delegate.py"

__all__: list[str] = []


def _module() -> object:
    """Import the seam only after the Red assertion has run."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module("livespec_dev_tooling.commit_replay_delegate")


def test_an_absent_commit_replay_opt_in_runs_locally(*, tmp_path: Path) -> None:
    """A repository must explicitly opt in before a replay leg can delegate."""
    module = _module()
    verdict = module.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

    assert verdict.local is True
    assert verdict.reason == "delegated_commit_tests is not enabled"


@pytest.mark.parametrize(
    ("config", "reason"),
    [
        (
            "[tool.livespec_dev_tooling]\ndelegated_commit_tests = false\n",
            "delegated_commit_tests is not enabled",
        ),
        (
            "[tool.livespec_dev_tooling]\ndelegated_commit_tests = 'yes'\n",
            "delegated_commit_tests is not enabled",
        ),
        (
            "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
            "gates kubeconfig is not readable",
        ),
    ],
)
def test_an_unavailable_replay_route_runs_locally(
    *, tmp_path: Path, config: str, reason: str
) -> None:
    """Only a literal opt-in on a credentialed host selects delegation."""
    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(config, encoding="utf-8")

    verdict = module.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

    assert verdict.local is True
    assert verdict.reason == reason


def test_a_credentialed_replay_delegates_the_staged_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delegated path carries the index tree, never the current HEAD tree."""
    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    captured: dict[str, object] = {}
    expected = module.ReplayVerdict(
        local=False,
        reason="delegated replay completed",
        job_name="gate-replay-1",
        tree_hash="a" * 40,
        exit_status=0,
        output_checksum="checksum",
    )

    def remote(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_run_remote", remote)

    assert (
        module.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])
        is expected
    )
    assert captured["tree_hash"] == "a" * 40
    assert captured["pytest_argv"] == ["pytest", "tests/test_widget.py"]


def test_an_absent_remote_verdict_is_never_a_pass_or_a_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost Job answer is explicit so the hook can run the leg locally."""
    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(
        module,
        "_run_remote",
        lambda **_kwargs: module.ReplayVerdict(
            local=False,
            reason="the gate Job reached no verdict",
            tree_hash="b" * 40,
        ),
    )

    verdict = module.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

    assert verdict.local is False
    assert verdict.exit_status is None
    assert verdict.job_name is None
    assert verdict.reason == "the gate Job reached no verdict"


def test_a_tree_that_cannot_be_read_returns_an_absent_verdict(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A tree that cannot be read cannot be mistaken for the current HEAD."""
    from returns.result import Failure, Success

    from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun, GateCommandResult

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(
        module,
        "default_gate_command_runner",
        lambda **_kwargs: Success(GateCommandResult(returncode=0, stdout="c" * 40, stderr="")),
    )

    verdict = module.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

    assert verdict.local is False
    assert verdict.tree_hash == "c" * 40
    assert verdict.exit_status is None

    monkeypatch.setattr(
        module,
        "default_gate_command_runner",
        lambda **_kwargs: Failure(GateCommandNotRun(argv=("git",), detail="not found")),
    )

    unavailable = module.run_replay(
        repo_root=tmp_path,
        pytest_argv=["pytest", "tests/test_widget.py"],
    )

    assert unavailable.local is False
    assert unavailable.tree_hash is None
    assert unavailable.exit_status is None
    assert unavailable.reason == "the staged tree could not be read"


def test_a_remote_replay_submits_the_staged_tree_and_reports_the_job(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real gate path receives the index tree, test selection and Job verdict."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    request = GateRunRequest(
        repo_root=tmp_path,
        mirror_url="mirror",
        manifest="manifest",
        gate_ref="refs/gates/a",
    )

    def build(**kwargs: object) -> object:
        captured.update(kwargs)
        return Success(request)

    monkeypatch.setattr(module, "gate_remote_request", build)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "f" * 40)

    def run(**kwargs: object) -> GateVerdict:
        captured["pushed"] = kwargs["request"]
        return GateVerdict(
            state=GATE_PASSED,
            detail="the Job passed",
            token_written=True,
            job_name="gate-replay-1",
            output_checksum="checksum",
        )

    monkeypatch.setattr(module, "run_gated_push", run)

    verdict = module.run_replay(
        repo_root=tmp_path,
        pytest_argv=["pytest", "tests/test_widget.py"],
    )

    assert captured["tree_hash"] == "a" * 40
    assert captured["pytest_argv"] == ("pytest", "tests/test_widget.py")
    pushed = captured["pushed"]
    assert pushed.source_ref == "f" * 40
    assert pushed.capture_output is True
    assert verdict == module.ReplayVerdict(
        local=False,
        reason="the Job passed",
        job_name="gate-replay-1",
        tree_hash="a" * 40,
        exit_status=0,
        output_checksum="checksum",
    )


def test_an_unbuilt_remote_replay_is_an_explicit_no_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A request failure cannot be reported as a red or green Job result."""
    from returns.result import Failure

    from livespec_dev_tooling.gate_remote_invocation import GateStepFailed

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Failure(
            GateStepFailed(step="render", argv=(), returncode=1, detail="renderer refused")
        ),
    )

    verdict = module.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

    assert verdict.local is False
    assert verdict.exit_status is None
    assert verdict.reason == "the gate Job reached no verdict: renderer refused"


def _git_runner(*, calls: list[list[str]], commit_works: bool) -> object:
    """Answer `git write-tree` with one tree and `git commit-tree` with one commit."""
    from returns.result import Failure, Success

    from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun, GateCommandResult

    def run(**kwargs: object) -> object:
        argv = list(kwargs["argv"])
        calls.append(argv)
        if "commit-tree" in argv:
            if not commit_works:
                return Failure(GateCommandNotRun(argv=tuple(argv), detail="not found"))
            return Success(GateCommandResult(returncode=0, stdout="d" * 40 + "\n", stderr=""))
        return Success(GateCommandResult(returncode=0, stdout="a" * 40 + "\n", stderr=""))

    return run


def _opted_in_replay(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, commit_works: bool
) -> tuple[object, list[list[str]], list[object]]:
    """Run one delegated replay against stubbed git and a stubbed gate Job."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []
    pushed: list[object] = []
    request = GateRunRequest(
        repo_root=tmp_path, mirror_url="mirror", manifest="manifest", gate_ref="ref"
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "gate_remote_request", lambda **_kwargs: Success(request))
    monkeypatch.setattr(
        module, "default_gate_command_runner", _git_runner(calls=calls, commit_works=commit_works)
    )

    def run(**kwargs: object) -> GateVerdict:
        pushed.append(kwargs["request"])
        return GateVerdict(state=GATE_PASSED, detail="the Job passed", token_written=True)

    monkeypatch.setattr(module, "run_gated_push", run)
    verdict = module.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])
    return verdict, calls, pushed


def test_the_staged_tree_is_committed_so_the_gate_pushes_it_and_not_head(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate pushes a commit object, so the index tree needs one to be pushed."""
    verdict, calls, pushed = _opted_in_replay(
        monkeypatch=monkeypatch, tmp_path=tmp_path, commit_works=True
    )

    commit_calls = [argv for argv in calls if "commit-tree" in argv]
    assert [argv[-5:-1] for argv in commit_calls] == [["commit-tree", "a" * 40, "-p", "HEAD"]]
    assert [request.source_ref for request in pushed] == ["d" * 40]
    assert [request.capture_output for request in pushed] == [True]
    assert verdict.exit_status == 0


def test_a_staged_tree_that_cannot_be_committed_is_an_explicit_no_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no object to push, nothing is submitted and nothing reads as a verdict."""
    verdict, _calls, pushed = _opted_in_replay(
        monkeypatch=monkeypatch, tmp_path=tmp_path, commit_works=False
    )

    assert pushed == []
    assert verdict.local is False
    assert verdict.exit_status is None
    assert verdict.job_name is None
    assert verdict.tree_hash == "a" * 40
    assert verdict.reason == "the staged tree could not be committed for the gate"
