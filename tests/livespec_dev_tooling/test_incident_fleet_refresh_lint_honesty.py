"""The refresh command satisfies the return-count lint rule instead of suppressing it."""

from __future__ import annotations

from pathlib import Path

_MODULE = Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "incident_fleet_refresh.py"


def test_refresh_module_does_not_suppress_the_return_count_rule() -> None:
    assert "PLR0911" not in _MODULE.read_text(encoding="utf-8")
