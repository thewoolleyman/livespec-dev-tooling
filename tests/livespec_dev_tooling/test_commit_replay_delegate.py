"""Commit-time replay delegation decisions."""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.commit_replay_delegate import run_replay

__all__: list[str] = []


def test_an_absent_commit_replay_opt_in_runs_locally(*, tmp_path: Path) -> None:
    """A repository must explicitly opt in before a replay leg can delegate."""
    verdict = run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

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
    _ = (tmp_path / "pyproject.toml").write_text(config, encoding="utf-8")

    verdict = run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

    assert verdict.local is True
    assert verdict.reason == reason


def test_an_opted_in_credentialed_host_selects_delegation(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The credentialed opt-in is the only route that may submit a gate Job."""
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "livespec_dev_tooling.commit_replay_delegate.gates_kubeconfig_readable", lambda: True
    )
    verdict = run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

    assert verdict.local is False
    assert verdict.reason == "delegated replay completed"
