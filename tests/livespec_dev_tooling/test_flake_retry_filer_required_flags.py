"""The flake-retry filer takes its state and repository locations only from flags."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import Mock

import pytest


def _filer_with_every_side_effect_recorded(*, monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Load the filer with each side-effecting seam recording instead of acting.

    Directory creation and marker touching are recorded rather than performed,
    so a refusal is proved by an empty record and a failing run cannot write
    wherever an omitted flag would have pointed.
    """
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")
    seams = Mock()
    monkeypatch.setattr(Path, "mkdir", seams.mkdir)
    monkeypatch.setattr(Path, "touch", seams.touch)
    monkeypatch.setattr(filer, "file_root_fixes", seams.file_root_fixes)
    monkeypatch.setattr(filer, "registered_plugin_root", seams.registered_plugin_root)
    return seams


def test_the_filer_refuses_to_run_without_state_dir_and_names_the_flag(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting `--state-dir` exits non-zero before any filing or marker write."""
    seams = _filer_with_every_side_effect_recorded(monkeypatch=monkeypatch)
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(SystemExit) as refusal:
        _ = filer.main(argv=["--repo-root", str(tmp_path)])

    assert refusal.value.code != 0
    assert "--state-dir" in capsys.readouterr().err
    assert seams.mock_calls == []


def test_the_filer_refuses_to_run_without_repo_root_and_names_the_flag(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting `--repo-root` exits non-zero, files nothing and leaves the state dir alone."""
    seams = _filer_with_every_side_effect_recorded(monkeypatch=monkeypatch)
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(SystemExit) as refusal:
        _ = filer.main(argv=["--state-dir", str(tmp_path / "state")])

    assert refusal.value.code != 0
    assert "--repo-root" in capsys.readouterr().err
    assert seams.mock_calls == []


def test_the_staleness_check_also_refuses_without_repo_root(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The health check is an invocation of the same entry point, so it names both flags."""
    seams = _filer_with_every_side_effect_recorded(monkeypatch=monkeypatch)
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(SystemExit) as refusal:
        _ = filer.main(argv=["--state-dir", str(tmp_path), "--check-staleness"])

    assert refusal.value.code != 0
    assert "--repo-root" in capsys.readouterr().err
    assert seams.mock_calls == []


def test_the_filer_help_still_prints_usage_and_exits_zero(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--help` is exempt from the required flags."""
    filer = importlib.import_module("livespec_dev_tooling.flake_retry_filer")

    with pytest.raises(SystemExit) as helped:
        _ = filer.main(argv=["--help"])

    assert helped.value.code == 0
    usage = capsys.readouterr().out
    assert "--state-dir" in usage
    assert "--repo-root" in usage
