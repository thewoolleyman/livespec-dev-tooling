"""A pytest session started inside another one leaves the outer session's retry state alone.

The orchestrator's tests drive in-process pytest sessions from inside a test, and
this plugin is loaded into those inner sessions as well. Its state lives in
module globals, so an inner session's collection cleared and refilled the outer
session's withholding reason with its own (a tmp directory under a hermetic
repository), and the outer xdist worker then forwarded the inner reason to the
controller: `FLAKE-RETRY-WITHHELD ... git fetch --deepen=1 origin ... exit 128`
in 6 of 24 coverage shard jobs (livespec-dev-tooling-qawphe).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_OUTER_REASON = "a justfile change"
_INNER_REASON = "`git fetch --quiet --deepen=1 origin abc` failed (exit 128)"


def _session(*, root: Path) -> Any:
    config = SimpleNamespace(
        rootpath=root,
        stash=pytest.Stash(),
        pluginmanager=SimpleNamespace(hasplugin=lambda _name: True),
        workeroutput={},
    )
    return SimpleNamespace(config=config)


def test_a_nested_session_does_not_replace_the_outer_sessions_withholding_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(plugin, "_RESULTS", {})
    monkeypatch.setattr(plugin, "_FAILED_NODEIDS", set[str]())
    withheld: list[str] = []
    monkeypatch.setattr(plugin, "_SESSION_WITHHELD", withheld)
    monkeypatch.setattr(plugin, "_WITHHELD_BY_NODEID", dict[str, str]())
    monkeypatch.setattr(plugin, "_LIVE_SESSIONS", [], raising=False)
    outer_root = tmp_path / "outer"
    inner_root = tmp_path / "inner"
    reasons = {outer_root: _OUTER_REASON, inner_root: _INNER_REASON}
    monkeypatch.setattr(plugin, "mark_untouched_tests", lambda *, root, **_ignored: reasons[root])
    start = getattr(plugin, "pytest_sessionstart", lambda _session: None)
    outer = _session(root=outer_root)
    inner = _session(root=inner_root)

    start(outer)
    plugin.pytest_collection_modifyitems(outer, outer.config, [])
    start(inner)
    plugin.pytest_collection_modifyitems(inner, inner.config, [])
    plugin.pytest_sessionfinish(inner, 0)
    plugin.pytest_sessionfinish(outer, 0)

    forwarded = outer.config.workeroutput["livespec_flake_retry_withheld"]
    assert (withheld, forwarded["session"]) == (
        [_OUTER_REASON],
        _OUTER_REASON,
    )
