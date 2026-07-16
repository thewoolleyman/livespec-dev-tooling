"""Tests for `source_trees_scoped_to_consumer`."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "source_trees_scoped_to_consumer.py"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "source_trees_scoped_to_consumer_under_test",
        str(_CHECK),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_check(
    *, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    module = _load_check()
    monkeypatch.chdir(root)
    rc = module.main()
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


def test_source_trees_scoped_to_consumer_rejects_drifted_core_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'source_trees = [".claude-plugin/scripts/livespec"]\n'
        'commands_trees = [".claude-plugin/scripts/livespec/commands"]\n',
        encoding="utf-8",
    )
    (tmp_path / ".claude-plugin" / "scripts" / "consumer_pkg").mkdir(parents=True)
    (tmp_path / ".claude-plugin" / "scripts" / "livespec" / "commands").mkdir(parents=True)

    rc, combined = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc != 0
    assert ".claude-plugin/scripts/livespec" in combined
    assert "foreign_package" in combined


def test_source_trees_scoped_to_consumer_rejects_missing_declared_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["missing_pkg"]\n',
        encoding="utf-8",
    )

    rc, combined = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc != 0
    assert "missing" in combined
    assert "missing_pkg" in combined


def test_source_trees_scoped_to_consumer_accepts_flat_consumer_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'source_trees = ["pkg"]\n'
        'source_tree_prefixes = ["pkg/"]\n'
        'mirror_pairings = [{ source_tree = "pkg", test_tree = "tests/pkg" }]\n',
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests" / "pkg").mkdir(parents=True)

    rc, combined = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0
    assert combined == ""


def test_source_trees_scoped_to_consumer_accepts_repo_without_plugin_scripts(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'source_trees = ["pkg"]\n'
        'covered_trees = ["pkg"]\n'
        'target_dirs = ["pkg"]\n',
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()

    rc, combined = _run_check(root=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert rc == 0
    assert combined == ""
