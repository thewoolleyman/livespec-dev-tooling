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
