"""The flake-retry plugin decides once per session whether the change is release metadata only.

A release-please branch changes exactly `pyproject.toml` and `uv.lock`. Whether
that change is a version bump alone costs a `git diff`, two `git show` reads and
four TOML parses, and its answer is the same for every test item in the session.
Collection must therefore ask it once per session, never once per item, and a
second session must ask it again rather than reuse the first one's answer.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

_RELEASE_PATHS = {Path("pyproject.toml"), Path("uv.lock")}
_ITEM_COUNT = 40


def _items(*, tmp_path: Path) -> list[Mock]:
    """Return many collected items over one test file."""
    _ = (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    test_file = tests / "test_a.py"
    _ = test_file.write_text("import app\nassert app.VALUE == 1\n", encoding="utf-8")
    return [Mock(path=test_file) for _ in range(_ITEM_COUNT)]


def _plugin_and_spy(*, monkeypatch: pytest.MonkeyPatch, verdict: bool) -> tuple[ModuleType, Mock]:
    """Load the plugin with a release change set and a counting version-only spy."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    decisions = importlib.import_module("livespec_dev_tooling.flake_retry_decisions")
    monkeypatch.setattr(plugin, "change_paths", Mock(return_value=set(_RELEASE_PATHS)))
    spy = Mock(return_value=verdict)
    monkeypatch.setattr(decisions, "version_only_release_change", spy)
    return plugin, spy


@pytest.mark.integration
def test_collection_asks_the_version_only_question_once_however_many_items_it_holds(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forty items on a release-only change set ask the version-only question once."""
    plugin, spy = _plugin_and_spy(monkeypatch=monkeypatch, verdict=True)
    items = _items(tmp_path=tmp_path)

    withheld = plugin.mark_untouched_tests(root=tmp_path, items=items, can_retry=True)

    assert withheld is None
    assert spy.call_count == 1


@pytest.mark.integration
def test_a_version_only_release_change_still_marks_every_item_for_retry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The decision per item is the one the uncached path gives: every item is marked."""
    plugin, _ = _plugin_and_spy(monkeypatch=monkeypatch, verdict=True)
    items = _items(tmp_path=tmp_path)

    _ = plugin.mark_untouched_tests(root=tmp_path, items=items, can_retry=True)

    assert [item.add_marker.call_count for item in items] == [1] * _ITEM_COUNT


@pytest.mark.integration
def test_a_non_version_only_release_change_withholds_every_retry_after_one_question(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A release change that is more than a version bump withholds the session, asked once."""
    plugin, spy = _plugin_and_spy(monkeypatch=monkeypatch, verdict=False)
    items = _items(tmp_path=tmp_path)

    withheld = plugin.mark_untouched_tests(root=tmp_path, items=items, can_retry=True)

    assert withheld == "a non-version-only pyproject.toml or uv.lock change"
    assert spy.call_count == 1
    assert [item.add_marker.call_count for item in items] == [0] * _ITEM_COUNT


@pytest.mark.integration
def test_each_session_asks_the_version_only_question_for_itself(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two sessions ask twice in all: the first session's answer is never reused."""
    plugin, spy = _plugin_and_spy(monkeypatch=monkeypatch, verdict=True)
    items = _items(tmp_path=tmp_path)

    _ = plugin.mark_untouched_tests(root=tmp_path, items=items, can_retry=True)
    _ = plugin.mark_untouched_tests(root=tmp_path, items=items, can_retry=True)

    assert spy.call_count == 2
