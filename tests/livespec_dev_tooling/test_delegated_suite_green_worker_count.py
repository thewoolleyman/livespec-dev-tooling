"""Acceptance coverage for suite-green worker selection after delegation."""

from __future__ import annotations

from pathlib import Path

import pytest

__all__: list[str] = []


def test_delegated_suite_green_uses_declared_job_parallelism_not_host_cpu_count(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 64-CPU committing host must not give a six-worker Job ``-n 16``."""
    from livespec_dev_tooling import commit_replay_delegate as replay

    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n" "delegated_commit_tests = true\n" "gate_parallelism = 6\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(replay, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(replay, "_staged_tree_hash", lambda **_kwargs: "a" * 40)

    def remote(**kwargs: object) -> replay.ReplayVerdict:
        captured.update(kwargs)
        return replay.ReplayVerdict(local=False, reason="delegated")

    monkeypatch.setattr(replay, "_run_remote", remote)

    # The suite builder has already derived this from the committing host's
    # 64 CPUs.  Delegation must replace it with the Job's declared value.
    _ = replay.run_replay(
        repo_root=tmp_path,
        pytest_argv=["pytest", "-q", "-n", "16"],
    )

    assert captured["pytest_argv"][-2:] == ("-n", "6")
