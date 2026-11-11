"""Tests for the ambient-environment loop guard."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

__all__: list[str] = []

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "no_ambient_environment_loops.py"
)


def test_direct_os_environ_loop_is_rejected(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A loop over ``os.environ`` fails with its source location and rewrite."""
    tests = tmp_path / "tests"
    tests.mkdir()
    source = tests / "test_example.py"
    source.write_text(
        "import os\n\nfor name in os.environ:\n    del name\n",
        encoding="utf-8",
    )

    assert _MODULE_PATH.is_file()
    check = importlib.import_module("livespec_dev_tooling.checks.no_ambient_environment_loops")
    monkeypatch.chdir(tmp_path)
    result = check.main()
    captured = capsys.readouterr()

    assert result == 4
    assert "tests/test_example.py" in captured.err
    assert '"line": 3' in captured.err
    assert "single-expression rewrite" in captured.err
