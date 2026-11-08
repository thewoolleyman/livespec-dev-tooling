"""The per-target wall-time table shows each wall time as a reader compares it.

Incident livespec-dev-tooling-e62ss6: a 169.9-minute coverage run read as a bare
second count, which had to be divided by hand.
"""

from __future__ import annotations

import pytest

from livespec_dev_tooling.parallel_check_dispatcher import TargetResult, _write_timing_table

__all__: list[str] = []


def _table_line(*, wall_time_s: float, capsys: pytest.CaptureFixture[str]) -> str:
    # EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-e62ss6
    result = TargetResult(
        name="check-target", skipped=False, exit_code=0, wall_time_s=wall_time_s, output=""
    )
    _write_timing_table(results=[result])
    return capsys.readouterr().out.splitlines()[-1]


def test_a_wall_time_under_a_minute_keeps_one_decimal(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _table_line(wall_time_s=59.4, capsys=capsys).split() == ["59.4s", "check-target"]


def test_a_wall_time_of_a_minute_or_more_shows_minutes_and_seconds(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _table_line(wall_time_s=125.4, capsys=capsys).split() == ["2m", "05s", "check-target"]
