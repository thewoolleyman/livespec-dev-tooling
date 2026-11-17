"""A nested session's reports and summary never reach the outer session's retry state.

Companion of `test_flake_retry_nested_session.py`: that file covers collection and
the xdist hand-off; this one covers the report hook and the terminal summary
(livespec-dev-tooling-qawphe).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _session(*, root: Path) -> Any:
    config = SimpleNamespace(rootpath=root, stash=pytest.Stash(), workeroutput={})
    return SimpleNamespace(config=config)


def _report(*, nodeid: str) -> Any:
    return SimpleNamespace(when="call", outcome="failed", nodeid=nodeid, longrepr="boom")


@pytest.fixture
def plugin(monkeypatch: pytest.MonkeyPatch) -> Any:
    module = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(module, "_RESULTS", {})
    monkeypatch.setattr(module, "_FAILED_NODEIDS", set[str]())
    monkeypatch.setattr(module, "_SESSION_WITHHELD", list[str]())
    monkeypatch.setattr(module, "_WITHHELD_BY_NODEID", dict[str, str]())
    monkeypatch.setattr(module, "_LIVE_SESSIONS", [], raising=False)
    return module


def test_a_report_made_while_a_nested_session_is_live_is_not_recorded(
    tmp_path: Path, plugin: Any
) -> None:
    plugin.pytest_sessionstart(_session(root=tmp_path / "outer"))
    inner = _session(root=tmp_path / "inner")
    plugin.pytest_sessionstart(inner)

    plugin.pytest_runtest_logreport(_report(nodeid="inner.py::test_inner"))
    plugin.pytest_sessionfinish(inner, 0)
    plugin.pytest_runtest_logreport(_report(nodeid="outer.py::test_outer"))

    assert {"outer.py::test_outer"} == plugin._FAILED_NODEIDS  # noqa: SLF001


def test_a_nested_sessions_summary_announces_nothing(
    tmp_path: Path, plugin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    announced: list[object] = []
    monkeypatch.setattr(plugin, "announce_retries", lambda **kwargs: announced.append(kwargs))
    outer = _session(root=tmp_path / "outer")
    inner = _session(root=tmp_path / "inner")
    plugin.pytest_sessionstart(outer)
    plugin.pytest_sessionstart(inner)

    plugin.pytest_terminal_summary(object(), 0, inner.config)
    plugin.pytest_terminal_summary(object(), 0, outer.config)

    assert len(announced) == 1
