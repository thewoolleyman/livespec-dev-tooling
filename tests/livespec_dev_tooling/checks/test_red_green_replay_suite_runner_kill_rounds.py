"""Mirror-paired test for the stalled suite's final kill rounds."""

from __future__ import annotations

import signal
import types

import pytest

from livespec_dev_tooling.checks import _red_green_replay_suite_runner as mod

__all__: list[str] = []


def test_the_final_kill_rescans_until_the_escapee_is_gone(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An escapee that survives one KILL round is signalled again before the verdict."""

    class FinishedProcess:
        pid = 1

        def poll(self) -> int:
            return 0

    delivered: list[tuple[int, int]] = []

    def deliver(pid: int, sig: int) -> None:
        delivered.append((pid, sig))

    def kill_group(*_args: object) -> None:
        raise ProcessLookupError

    def alive(**_kwargs: object) -> bool:
        return [sig for _, sig in delivered].count(signal.SIGKILL) < 2

    monkeypatch.setattr(mod, "_KILL_GRACE_SECONDS", 1)
    monkeypatch.setattr(mod, "out_of_group_descendants", lambda **_kwargs: ((2, "escaped"),))
    monkeypatch.setattr(mod, "is_alive", alive)
    monkeypatch.setattr(mod.os, "kill", deliver)
    monkeypatch.setattr(mod.os, "killpg", kill_group)

    assert mod.end_stalled_suite(proc=FinishedProcess(), mark="mark") == ((2, "escaped"),)
    assert [sig for _, sig in delivered].count(signal.SIGKILL) == 2


def test_the_final_kill_keeps_rescanning_while_each_scan_finds_a_new_escapee(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spawner that outlasts the grace period is still ended before the verdict."""

    class FinishedProcess:
        pid = 1

        def poll(self) -> int:
            return 0

    scans = [0]
    clock = [0.0]
    killed: set[int] = set()
    spawned: set[int] = set()

    def scan(**_kwargs: object) -> tuple[tuple[int, str], ...]:
        scans[0] += 1
        survivors = sorted(spawned - killed)
        if scans[0] <= 1000:
            pid = 1000 + scans[0]
            spawned.add(pid)
            survivors.append(pid)
        return tuple((pid, "respawned") for pid in survivors)

    def deliver(pid: int, sig: int) -> None:
        if sig == signal.SIGKILL:
            killed.add(pid)

    def kill_group(*_args: object) -> None:
        raise ProcessLookupError

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    fake_time = types.SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep)
    monkeypatch.setattr(mod, "time", fake_time)
    monkeypatch.setattr(mod, "out_of_group_descendants", scan)
    monkeypatch.setattr(mod, "is_alive", lambda **kwargs: kwargs["pid"] not in killed)
    monkeypatch.setattr(mod.os, "kill", deliver)
    monkeypatch.setattr(mod.os, "killpg", kill_group)

    mod.end_stalled_suite(proc=FinishedProcess(), mark="mark")

    assert spawned
    assert spawned <= killed
