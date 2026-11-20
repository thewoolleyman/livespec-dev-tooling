"""Suite-green worker selection must not pre-empt the resource-declaration refusal."""

from __future__ import annotations

from pathlib import Path

import pytest

__all__: list[str] = []


def test_unusable_gate_resource_declaration_still_refuses_a_suite_green_leg(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid declared resource refuses the leg naming the key, never raises."""
    from livespec_dev_tooling import commit_replay_delegate as replay
    from livespec_dev_tooling._gate_remote_assembly import declared_gate_job_resources

    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\ngate_cpu = 0\n",
        encoding="utf-8",
    )
    pushed: list[object] = []
    monkeypatch.delenv("test_nprocs", raising=False)
    monkeypatch.delenv("LIVESPEC_CI_LANE", raising=False)
    monkeypatch.delenv("LIVESPEC_TEST_PARALLELISM", raising=False)
    monkeypatch.setattr(replay, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(replay, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(replay, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        replay,
        "gate_remote_request",
        lambda **kwargs: declared_gate_job_resources(repo_root=kwargs["repo_root"]),
    )
    monkeypatch.setattr(replay, "run_gated_push", lambda **kwargs: pushed.append(kwargs))

    verdict = replay.run_replay(
        repo_root=tmp_path,
        pytest_argv=["pytest", "-q", "-n", "16"],
    )

    assert verdict.refused is True
    assert "gate_cpu" in verdict.reason
    assert pushed == []
