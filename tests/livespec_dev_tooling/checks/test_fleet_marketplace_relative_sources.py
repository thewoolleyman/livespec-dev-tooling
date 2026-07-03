"""Outside-in test for the fleet marketplace relative-source guard."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import NamedTuple, TypeAlias

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "fleet_marketplace_relative_sources.py"
_CatalogSource: TypeAlias = dict[str, object] | str


def _load_check_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fleet_marketplace_relative_sources_under_test", str(_CHECK)
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


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_catalog(*, path: Path, source: _CatalogSource) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "name": "livespec-driver-codex",
                "plugins": [
                    {
                        "name": "livespec",
                        "source": source,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_fleet_marketplace_relative_sources_rejects_github_source(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A github-type catalog source fails because it bypasses ref pinning."""
    catalog = tmp_path / ".agents" / "plugins" / "marketplace.json"
    _write_catalog(path=catalog, source="thewoolleyman/livespec")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert ".agents/plugins/marketplace.json" in result.stderr
    assert "thewoolleyman/livespec" in result.stderr
    assert "ref pin" in result.stderr
    assert result.stdout == ""


def test_fleet_marketplace_relative_sources_rejects_github_object_source(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A github-type object catalog source fails because it bypasses ref pinning."""
    catalog = tmp_path / ".agents" / "plugins" / "marketplace.json"
    _write_catalog(
        path=catalog,
        source={
            "source": "github",
            "repo": "thewoolleyman/livespec",
        },
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert ".agents/plugins/marketplace.json" in result.stderr
    assert "github" in result.stderr
    assert "ref pin" in result.stderr
    assert result.stdout == ""


def test_fleet_marketplace_relative_sources_rejects_absolute_source(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absolute catalog source fails because it is not checkout-relative."""
    catalog = tmp_path / ".claude-plugin" / "marketplace.json"
    _write_catalog(path=catalog, source="/opt/livespec/.claude-plugin")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert ".claude-plugin/marketplace.json" in result.stderr
    assert "/opt/livespec/.claude-plugin" in result.stderr
    assert result.stdout == ""


def test_fleet_marketplace_relative_sources_accepts_relative_source(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A catalog source beginning `./` preserves the ref-pin mechanism."""
    catalog = tmp_path / ".claude-plugin" / "marketplace.json"
    _write_catalog(path=catalog, source="./.claude-plugin")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""


def test_fleet_marketplace_relative_sources_accepts_local_object_relative_source(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A Codex local object source beginning `./` preserves ref pinning."""
    catalog = tmp_path / ".agents" / "plugins" / "marketplace.json"
    _write_catalog(
        path=catalog,
        source={
            "source": "local",
            "path": "./.claude-plugin",
        },
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""


def test_fleet_marketplace_relative_sources_accepts_both_core_catalog_shapes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A tree carrying both core catalog shapes remains valid."""
    _write_catalog(
        path=tmp_path / ".agents" / "plugins" / "marketplace.json",
        source={
            "source": "local",
            "path": "./.claude-plugin",
        },
    )
    _write_catalog(
        path=tmp_path / ".claude-plugin" / "marketplace.json",
        source="./.claude-plugin",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""


def test_fleet_marketplace_relative_sources_skips_when_no_catalogs(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A consumer tree with no marketplace catalogs is outside this check's role."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""
