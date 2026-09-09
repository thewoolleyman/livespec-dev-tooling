"""Outside-in test for the livespec-family marketplace ref guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "marketplace_ref_release_only.py"


def _load_check_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "marketplace_ref_release_only_under_test", str(_CHECK)
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


def _write_settings(*, root: Path, body: str) -> None:
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(body, encoding="utf-8")


def _github_marketplace(*, name: str, repo: str, ref: str) -> str:
    return (
        f'    "{name}": {{\n'
        '      "source": {\n'
        '        "source": "github",\n'
        f'        "repo": "{repo}",\n'
        f'        "ref": "{ref}"\n'
        "      }\n"
        "    }"
    )


def _settings_with(*, entries: tuple[str, ...]) -> str:
    return '{\n  "extraKnownMarketplaces": {\n' + ",\n".join(entries) + "\n  }\n}\n"


def test_marketplace_ref_release_only_skips_when_no_settings_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A checkout with no `.claude/settings.json` is outside this check's role."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert "skipped" in result.stderr
    assert result.stdout == ""


def test_marketplace_ref_release_only_accepts_release_pinned_family(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every livespec-family marketplace declaring `release` passes."""
    _write_settings(
        root=tmp_path,
        body=_settings_with(
            entries=(
                _github_marketplace(name="livespec", repo="thewoolleyman/livespec", ref="release"),
                _github_marketplace(
                    name="livespec-overseer",
                    repo="thewoolleyman/livespec-overseer",
                    ref="release",
                ),
            )
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""


def test_marketplace_ref_release_only_rejects_family_pinned_to_a_tag(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A family marketplace pinned to a version tag fails and is named."""
    _write_settings(
        root=tmp_path,
        body=_settings_with(
            entries=(
                _github_marketplace(name="livespec", repo="thewoolleyman/livespec", ref="release"),
                _github_marketplace(
                    name="livespec-orchestrator-beads-fabro",
                    repo="thewoolleyman/livespec-orchestrator-beads-fabro",
                    ref="v1.72.0",
                ),
            )
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert "livespec-orchestrator-beads-fabro" in result.stderr
    assert "v1.72.0" in result.stderr
    assert "host-global" in result.stderr
    assert result.stdout == ""


def test_marketplace_ref_release_only_accepts_pinned_non_family_marketplace(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-livespec marketplace may pin any ref — it shares no family slot."""
    _write_settings(
        root=tmp_path,
        body=_settings_with(
            entries=(
                _github_marketplace(
                    name="claude-code", repo="anthropics/claude-code", ref="v2.0.1"
                ),
            )
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""


def test_marketplace_ref_release_only_accepts_settings_without_marketplaces(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Settings that declare no `extraKnownMarketplaces` key pass."""
    _write_settings(root=tmp_path, body='{\n  "env": {}\n}\n')

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""


def test_marketplace_ref_release_only_tolerates_entries_without_a_family_github_source(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Entries with no dict `source`, no string `repo`, or a non-family repo pass.

    None of these shapes rewrites a shared livespec slot in the host-global
    registry, so the guard has nothing to say about them.
    """
    _write_settings(
        root=tmp_path,
        body=_settings_with(
            entries=(
                '    "entry-not-an-object": "thewoolleyman/livespec"',
                '    "source-not-an-object": { "source": "./.claude-plugin" }',
                '    "repo-not-a-string": { "source": { "source": "github", "ref": "v1.0.0" } }',
            )
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""


def test_marketplace_ref_release_only_tolerates_non_object_marketplaces_block(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An `extraKnownMarketplaces` value that is not an object declares no family pin."""
    _write_settings(root=tmp_path, body='{\n  "extraKnownMarketplaces": []\n}\n')

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""


def test_marketplace_ref_release_only_fails_closed_on_unparseable_settings(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unparseable or non-object settings fail closed rather than passing silently."""
    unparseable = tmp_path / "unparseable"
    _write_settings(root=unparseable, body="{ not json at all\n")

    result = _run_check(cwd=unparseable, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert "unreadable" in result.stderr
    assert result.stdout == ""

    non_object = tmp_path / "non-object"
    _write_settings(root=non_object, body="[]\n")

    second = _run_check(cwd=non_object, monkeypatch=monkeypatch, capsys=capsys)

    assert second.returncode != 0
    assert "unreadable" in second.stderr
    assert second.stdout == ""
