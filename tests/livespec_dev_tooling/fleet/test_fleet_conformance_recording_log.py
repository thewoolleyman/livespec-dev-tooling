"""Coverage for the fleet-conformance test logger helper."""

from __future__ import annotations

from test_fleet_conformance import RecordingLog

__all__: list[str] = []


def test_recording_log_captures_warning_and_info_events() -> None:
    log = RecordingLog()

    log.warning("warning event", detail="ignored")
    log.info("info event", detail="ignored")

    assert log.events == ["warning event", "info event"]
