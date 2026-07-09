"""Branch-level coverage for the partition-completeness public check path."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

from livespec_dev_tooling.checks import partition_completeness

__all__: list[str] = []


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
    rc = partition_completeness.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_supervisor_and_dataclasses_roles_claim_files_through_main(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """File-specific and nullable-tree roles become direct semantic claims."""
    _write_config(
        root=tmp_path,
        body='supervisor_entry_files = ["bin/run.py"]\ndataclasses_tree = "pkg/schemas"\n',
    )
    _write(root=tmp_path, rel_path="bin/run.py")
    _write(root=tmp_path, rel_path="pkg/schemas/model.py")
    _init_repo_with_files(root=tmp_path)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stderr == ""


def test_broad_mirror_and_prefix_roles_claim_files_through_main(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Applicability-style roles claim files but do not create duplicate noise."""
    _write_config(
        root=tmp_path,
        body=(
            'source_tree_prefixes = ["other/", "pkg/"]\n'
            "mirror_pairings = [\n"
            '  { source_tree = "other", test_tree = "tests/other" },\n'
            '  { source_tree = "pkg", test_tree = "tests/pkg" },\n'
            "]\n"
        ),
    )
    _write(root=tmp_path, rel_path="pkg/module.py")
    _init_repo_with_files(root=tmp_path)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stderr == ""
