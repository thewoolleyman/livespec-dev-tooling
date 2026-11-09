"""Tests for the scheduled, advisory kill-matrix entry point."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

__all__: list[str] = []


def test_a_scheduled_run_retains_the_last_report_and_compares_against_it(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first run says it has nothing to compare; a later one passes the retained report."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_scheduled")
    received: list[list[str]] = []

    def engine(*, argv: list[str]) -> int:
        received.append(argv)
        return 0

    monkeypatch.setattr(module.mutation_kill_matrix_runner, "main", engine)

    assert module.main(argv=[str(tmp_path), "--workers", "2"]) == 0
    assert received[-1] == [str(tmp_path.resolve()), "--workers", "2"]
    assert "without a what-changed summary" in capsys.readouterr().out

    report = tmp_path / "reports" / "mutation-kill-matrix.json"
    report.parent.mkdir()
    _ = report.write_text('{"run": 1}\n', encoding="utf-8")
    assert module.main(argv=[str(tmp_path)]) == 0

    retained = tmp_path.resolve() / module.RETAINED_PATH
    assert retained.read_text(encoding="utf-8") == '{"run": 1}\n'
    assert received[-1] == [str(tmp_path.resolve()), "--previous-report", str(retained)]
