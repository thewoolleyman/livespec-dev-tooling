"""Unit tests for delegated commit-msg replay execution."""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []


def test_opted_in_eligible_hosts_delegate_the_staged_replay(monkeypatch, tmp_path: Path) -> None:
    """The commit hook delegates only after both opt-in and host eligibility."""
    module_path = Path("livespec_dev_tooling/commit_replay_delegate.py")
    assert module_path.is_file()
    delegate = importlib.import_module("livespec_dev_tooling.commit_replay_delegate")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(delegate, "gates_kubeconfig_readable", lambda: True)
    expected = delegate.ReplayVerdict(
        returncode=1,
        output="pytest output",
        job_name="gate-widget-1",
        tree_hash="a" * 40,
        delegated=True,
    )
    monkeypatch.setattr(delegate, "_run_remote", lambda **_kwargs: expected)

    actual = delegate.run_replay(
        repo_root=tmp_path,
        pytest_argv=("-q", "tests/test_example.py"),
        tree_hash="a" * 40,
    )

    assert actual == expected
