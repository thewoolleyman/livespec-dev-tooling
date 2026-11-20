"""Edge coverage for delegated suite-green replay worker selection."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from livespec_dev_tooling import commit_replay_delegate as replay

__all__: list[str] = []


def _delegated_suite_argv(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declaration: str = ""
) -> tuple[str, ...]:
    contents = "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\n" + declaration
    _ = (tmp_path / "pyproject.toml").write_text(contents, encoding="utf-8")
    captured: dict[str, tuple[str, ...]] = {}

    def staged_tree_hash(*, repo_root: Path) -> str:
        _ = repo_root
        return "a" * 40

    def remote(
        *,
        repo_root: Path,
        pytest_argv: Sequence[str],
        tree_hash: str,
        resources: tuple[str, ...] | None,
    ) -> replay.ReplayVerdict:
        _ = (repo_root, tree_hash, resources)
        captured["pytest_argv"] = tuple(pytest_argv)
        return replay.ReplayVerdict(local=False, reason="delegated")

    monkeypatch.setattr(replay, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(replay, "_staged_tree_hash", staged_tree_hash)
    monkeypatch.setattr(replay, "_run_remote", remote)
    _ = replay.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "-q", "-n", "16"])
    return captured["pytest_argv"]


def test_delegated_suite_green_uses_the_renderer_default_when_parallelism_is_undeclared(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An undeclared Job uses the renderer's four-worker default, not host CPUs."""

    def renderer(*, repo_root: Path) -> Path:
        _ = repo_root
        return Path(__file__).parents[2] / "ci-runner/k3s/phase2/gates/render-gate-job.sh"

    monkeypatch.setattr(replay, "resolve_renderer", renderer)
    assert _delegated_suite_argv(tmp_path=tmp_path, monkeypatch=monkeypatch)[-2:] == ("-n", "4")


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({"LIVESPEC_TEST_PARALLELISM": "2"}, "2"),
        ({"test_nprocs": "3", "LIVESPEC_TEST_PARALLELISM": "2"}, "3"),
    ],
)
def test_delegated_suite_green_preserves_explicit_worker_count_overrides(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    expected: str,
) -> None:
    """Explicit suite settings outrank the Job-derived count."""
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert _delegated_suite_argv(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        declaration="gate_parallelism = 6\n",
    )[-2:] == ("-n", expected)


def test_local_suite_green_keeps_its_host_derived_worker_count(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A local replay does not replace the suite builder's worker count."""
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_commit_tests = true\ngate_parallelism = 6\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(replay, "gates_kubeconfig_readable", lambda: False)

    verdict = replay.run_replay(repo_root=tmp_path, pytest_argv=["pytest", "-q", "-n", "16"])

    assert verdict.local is True
    assert verdict.reason == "gates kubeconfig is not readable"
