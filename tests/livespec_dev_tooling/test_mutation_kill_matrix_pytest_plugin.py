"""Tests for the pytest plugin that records each test's own kill-matrix outcome."""

from __future__ import annotations

import importlib
import json
import signal
from dataclasses import dataclass, field
from pathlib import Path

import pytest

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.mutation_kill_matrix_pytest_plugin"


@dataclass
class _Item:
    nodeid: str


@dataclass
class _Hook:
    deselected: list[object] = field(default_factory=list)

    def pytest_deselected(self, *, items: list[object]) -> None:
        self.deselected.extend(items)


@dataclass
class _Config:
    hook: _Hook = field(default_factory=_Hook)


@dataclass
class _Report:
    nodeid: str
    failed: bool


def _lines(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_collection_keeps_only_the_selected_node_ids(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A selection file deselects every other collected item; without one nothing changes."""
    module = importlib.import_module(_MODULE)
    items = [_Item("t::a"), _Item("t::b"), _Item("t::c")]
    config = _Config()

    module.pytest_collection_modifyitems(config, items)
    assert [item.nodeid for item in items] == ["t::a", "t::b", "t::c"]

    select = tmp_path / "select.txt"
    _ = select.write_text("t::a\nt::c\n", encoding="utf-8")
    monkeypatch.setenv(module.SELECT_VARIABLE, str(select))
    module.pytest_collection_modifyitems(config, items)

    assert [item.nodeid for item in items] == ["t::a", "t::c"]
    assert config.hook.deselected == [_Item("t::b")]


def test_each_test_records_whether_any_of_its_phases_failed(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failing phase makes the test failed; outcomes append one line per test."""
    module = importlib.import_module(_MODULE)
    outcomes = tmp_path / "outcomes.jsonl"
    monkeypatch.setenv(module.OUTCOMES_VARIABLE, str(outcomes))
    monkeypatch.delenv(module.TIMEOUT_VARIABLE, raising=False)

    for nodeid, phases in (("t::pass", (False, False, False)), ("t::fail", (False, True, False))):
        protocol = module.pytest_runtest_protocol(_Item(nodeid))
        next(protocol)
        for failed in phases:
            module.pytest_runtest_logreport(_Report(nodeid, failed))
        with pytest.raises(StopIteration):
            protocol.send(None)

    lines = _lines(path=outcomes)
    assert [(line["test"], line["failed"]) for line in lines] == [
        ("t::pass", False),
        ("t::fail", True),
    ]
    assert all(isinstance(line["duration"], float) for line in lines)


def test_a_timeout_arms_a_default_action_timer_for_each_test_and_disarms_it(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The timer runs while the test runs, with no handler a test could swallow."""
    module = importlib.import_module(_MODULE)
    monkeypatch.setenv(module.OUTCOMES_VARIABLE, str(tmp_path / "outcomes.jsonl"))
    monkeypatch.setenv(module.TIMEOUT_VARIABLE, "300")
    previous = signal.getsignal(signal.SIGALRM)
    try:
        protocol = module.pytest_runtest_protocol(_Item("t::timed"))
        next(protocol)
        armed = signal.getitimer(signal.ITIMER_REAL)[0]
        disposition = signal.getsignal(signal.SIGALRM)
        with pytest.raises(StopIteration):
            protocol.send(None)
        disarmed = signal.getitimer(signal.ITIMER_REAL)[0]
    finally:
        _ = signal.setitimer(signal.ITIMER_REAL, 0)
        _ = signal.signal(signal.SIGALRM, previous)

    assert 0 < armed <= 300
    assert disposition is signal.SIG_DFL
    assert disarmed == 0


def test_without_an_outcomes_file_nothing_is_written(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Loaded outside the engine, the plugin records nothing."""
    module = importlib.import_module(_MODULE)
    monkeypatch.delenv(module.OUTCOMES_VARIABLE, raising=False)
    monkeypatch.delenv(module.TIMEOUT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)

    protocol = module.pytest_runtest_protocol(_Item("t::quiet"))
    next(protocol)
    with pytest.raises(StopIteration):
        protocol.send(None)

    assert list(tmp_path.iterdir()) == []
