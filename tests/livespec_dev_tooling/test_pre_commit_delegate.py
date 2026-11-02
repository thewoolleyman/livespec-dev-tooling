"""Delegated pre-commit aggregate decisions."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parents[2] / "livespec_dev_tooling" / "pre_commit_delegate.py"

__all__: list[str] = []


def _module() -> object:
    """Import the seam only after the Red assertion has run."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module("livespec_dev_tooling.pre_commit_delegate")


def test_an_absent_pre_commit_opt_in_runs_locally(*, tmp_path: Path) -> None:
    """A repository must explicitly opt in before its pre-commit gate delegates."""
    module = _module()

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.reason == "delegated_pre_commit is not enabled"


def test_an_unreadable_gates_kubeconfig_runs_the_pre_commit_gate_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An opted-in repository without the host credential retains its local gate."""
    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: False)

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.reason == "gates kubeconfig is not readable"


def test_a_credentialed_pre_commit_delegates_the_staged_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Job receives a commit wrapping the index tree and its check recipe."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    request = GateRunRequest(
        repo_root=tmp_path,
        mirror_url="mirror",
        manifest="manifest",
        gate_ref="refs/gates/tree",
    )
    captured: dict[str, object] = {}

    def build(**kwargs: object) -> object:
        captured.update(kwargs)
        return Success(request)

    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "gate_remote_request", build)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=GATE_PASSED,
            detail="the Job passed",
            token_written=True,
            job_name="gate-pre-commit-1",
            tree_hash="a" * 40,
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert captured["tree_hash"] == "a" * 40
    assert captured["check_suite"] == ("check-pre-commit",)
    assert verdict.local is False
    assert verdict.job_name == "gate-pre-commit-1"
    assert verdict.tree_hash == "a" * 40
    assert verdict.exit_status == 0


@pytest.mark.parametrize(
    "remote",
    [
        {"state": "NO_VERDICT", "tree_hash": None},
        {"state": "PASSED", "tree_hash": "b" * 40},
    ],
)
def test_an_absent_or_wrong_tree_cluster_outcome_gates_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: dict[str, str | None]
) -> None:
    """Only a verdict naming the staged tree may keep the local aggregate out."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
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
            state=remote["state"],
            detail="the cluster could not provide the staged-tree verdict",
            token_written=False,
            tree_hash=remote["tree_hash"],
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.exit_status is None
    assert verdict.tree_hash == "a" * 40
