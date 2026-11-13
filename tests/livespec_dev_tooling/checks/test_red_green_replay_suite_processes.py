"""Focused coverage for bounded stalled-suite cleanup helpers."""

from __future__ import annotations

import signal

import pytest

from livespec_dev_tooling.checks._red_green_replay_suite_processes import (
    StalledCleanupSettings,
    StalledCleanupTools,
    end_stalled_cleanup,
)

__all__: list[str] = []


def test_a_later_pass_ends_a_new_target_and_a_gone_survivor_stops_the_final_wait(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reattribution defers new targets and stops once the final survivor exits."""

    class FinishedProcess:
        pid = 1

        def poll(self) -> int:
            return 0

    snapshots = iter(
        (
            ((2, "first"),),
            ((2, "first"), (3, "new after TERM")),
            ((3, "new after TERM"),),
            ((3, "new after TERM"),),
            (),
            (),
            ((4, "SIGKILL survivor"),),
            (),
        )
    )
    calls: list[tuple[int, signal.Signals]] = []
    ticks = iter((0.0,) * 20)
    monkeypatch.setattr(
        "livespec_dev_tooling.checks._red_green_replay_suite_processes.time.monotonic",
        lambda: next(ticks),
    )
    monkeypatch.setattr(
        "livespec_dev_tooling.checks._red_green_replay_suite_processes.time.sleep",
        lambda _seconds: None,
    )
    monkeypatch.setattr(
        "livespec_dev_tooling.checks._red_green_replay_suite_processes.os.kill",
        lambda pid, sig: calls.append((pid, sig)),
    )
    monkeypatch.setattr(
        "livespec_dev_tooling.checks._red_green_replay_suite_processes.os.killpg",
        lambda _pid, _sig: None,
    )

    found = end_stalled_cleanup(
        proc=FinishedProcess(),
        mark="mark",
        report=None,
        tools=StalledCleanupTools(
            find_descendants=lambda **_kwargs: next(snapshots),
            is_pid_alive=lambda **_kwargs: False,
        ),
        settings=StalledCleanupSettings(grace_seconds=1, poll_seconds=0.0, signal_passes=3),
    )

    assert found == ((2, "first"), (3, "new after TERM"), (4, "SIGKILL survivor"))
    assert calls == [
        (2, signal.SIGTERM),
        (2, signal.SIGKILL),
        (3, signal.SIGTERM),
        (3, signal.SIGKILL),
    ]
