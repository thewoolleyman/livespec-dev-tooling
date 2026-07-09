"""Outside-in tests for `livespec_dev_tooling/checks/partition_completeness.py`.

The partition-completeness meta-check is PR4 of the `fleet-check-coverage`
thread. It compares the git-derived first-party Python universe against the
consumer's semantic role declarations. During Phase 0 it emits WARN-only
diagnostics so the fleet receives a worklist without a red-out.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PARTITION_COMPLETENESS = (
    _REPO_ROOT / "livespec_dev_tooling" / "checks" / "partition_completeness.py"
)


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path."""
    spec = importlib.util.spec_from_file_location(
        "partition_completeness_under_test",
        str(_PARTITION_COMPLETENESS),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run `git` with a hermetic env so `git ls-files` sees fixture files."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _write(*, root: Path, rel_path: str, source: str = "__all__: list[str] = []\n") -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(source, encoding="utf-8")


def _write_config(*, root: Path, body: str) -> None:
    _ = (root / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\n{body}",
        encoding="utf-8",
    )


def _init_repo_with_files(*, root: Path) -> None:
    _git(cwd=root, args=["init", "-q"])
    _git(cwd=root, args=["add", "-A"])


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_unclaimed_first_party_file_warns_phase_zero(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A tracked first-party `.py` outside every declared role is named at WARN."""
    _write_config(root=tmp_path, body='source_trees = ["pkg"]\n')
    _write(root=tmp_path, rel_path="pkg/claimed.py")
    _write(root=tmp_path, rel_path="loose/unclaimed.py")
    _init_repo_with_files(root=tmp_path)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert "loose/unclaimed.py" in result.stderr
    assert "partition_status" in result.stderr
    assert "unclaimed" in result.stderr
    assert '"level": "warning"' in result.stderr
    assert "newly_covered" in result.stderr


def test_source_tree_claimed_file_passes_silently(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A first-party file covered by a broad source role has exactly one claim."""
    _write_config(root=tmp_path, body='source_trees = ["pkg"]\n')
    _write(root=tmp_path, rel_path="pkg/claimed.py")
    _init_repo_with_files(root=tmp_path)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stderr == ""


def test_specific_role_inside_source_tree_is_not_double_counted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A nested semantic role beats the broad `source_trees` fallback claim."""
    _write_config(root=tmp_path, body='source_trees = ["pkg"]\nio_trees = ["pkg/io"]\n')
    _write(root=tmp_path, rel_path="pkg/io/client.py")
    _init_repo_with_files(root=tmp_path)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stderr == ""


def test_multiple_specific_role_claims_warn_phase_zero(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A first-party file claimed by two specific roles is named at WARN."""
    _write_config(root=tmp_path, body='io_trees = ["pkg/shared"]\npure_trees = ["pkg/shared"]\n')
    _write(root=tmp_path, rel_path="pkg/shared/both.py")
    _init_repo_with_files(root=tmp_path)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert "pkg/shared/both.py" in result.stderr
    assert "partition_status" in result.stderr
    assert "multiple_claims" in result.stderr
    assert "io_trees:pkg/shared" in result.stderr
    assert "pure_trees:pkg/shared" in result.stderr
    assert '"level": "warning"' in result.stderr


def test_codeless_repo_passes_without_diagnostics(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A genuinely codeless repo remains a legitimate empty-universe pass."""
    _ = (tmp_path / "README.md").write_text("no python here\n", encoding="utf-8")
    _init_repo_with_files(root=tmp_path)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stderr == ""


def test_check_is_wired_into_just_aggregate() -> None:
    """Adding the canonical module must also wire `check-partition-completeness`."""
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")

    assert "check-partition-completeness" in justfile
