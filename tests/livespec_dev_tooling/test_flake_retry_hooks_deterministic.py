"""Deterministic coverage of the flake-retry hook branches the live session used to reach.

Every branch below was once covered only when this suite's OWN loaded plugin
happened to take it, which depends on the real checkout: its change set, and
whether CI can deepen a shallow clone (livespec-dev-tooling#4251, run
43149673846, left `flake_retry.py:113` uncovered on bytes master covered). Each
test here drives one branch in-process against a stubbed change set and stubbed
hook inputs, so the verdict no longer moves with the checkout.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest


def _justfile_changed(**_: object) -> set[Path]:
    return {Path("justfile")}


def test_an_unsafe_change_withholds_every_retry_and_marks_nothing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A justfile change names a whole-session reason and leaves every test unmarked."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    _ = (tmp_path / "test_safe.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(plugin, "change_paths", _justfile_changed)
    added: list[object] = []
    withheld_by_nodeid: dict[str, str] = {}

    withheld = plugin.mark_untouched_tests(
        root=tmp_path,
        items=[
            cast(
                pytest.Item,
                SimpleNamespace(
                    path=tmp_path / "test_safe.py",
                    nodeid="test_safe.py::test_it",
                    add_marker=added.append,
                ),
            )
        ],
        withheld_by_nodeid=withheld_by_nodeid,
    )

    assert withheld == "a justfile change"
    assert added == []
    assert withheld_by_nodeid == {}


def test_the_configure_hook_hands_the_config_to_the_finalizer_guard(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pytest_configure passes pytest's positional config on as a keyword."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    seen: list[object] = []

    def _preserve(*, config: object) -> None:
        seen.append(config)

    monkeypatch.setattr(plugin, "preserve_finalizers", _preserve)
    config = SimpleNamespace(name="config")

    plugin.pytest_configure(config)

    assert seen == [config]


def test_a_worker_sends_its_session_reason_and_failed_closure_holds_to_the_controller(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An xdist worker's sessionfinish writes the session reason and only failed holds."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(plugin, "_SESSION_WITHHELD", ["a justfile change"])
    monkeypatch.setattr(
        plugin,
        "_WITHHELD_BY_NODEID",
        {"t.py::failed": "an indeterminable path", "t.py::passed": "an unparseable module"},
    )
    monkeypatch.setattr(plugin, "_FAILED_NODEIDS", {"t.py::failed"})
    workeroutput: dict[str, object] = {}

    plugin.pytest_sessionfinish(
        SimpleNamespace(config=SimpleNamespace(workeroutput=workeroutput)), 1
    )

    assert workeroutput == {
        "livespec_flake_retry_withheld": {
            "session": "a justfile change",
            "nodes": {"t.py::failed": "an indeterminable path"},
        }
    }


def test_a_worker_sends_failed_closure_holds_with_no_session_reason(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker with only a failed closure hold sends it with a null session reason."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(plugin, "_SESSION_WITHHELD", [])
    monkeypatch.setattr(plugin, "_WITHHELD_BY_NODEID", {"t.py::failed": "an unparseable module"})
    monkeypatch.setattr(plugin, "_FAILED_NODEIDS", {"t.py::failed"})
    workeroutput: dict[str, object] = {}

    plugin.pytest_sessionfinish(
        SimpleNamespace(config=SimpleNamespace(workeroutput=workeroutput)), 1
    )

    assert workeroutput == {
        "livespec_flake_retry_withheld": {
            "session": None,
            "nodes": {"t.py::failed": "an unparseable module"},
        }
    }


def test_a_worker_with_nothing_withheld_sends_nothing(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker with no session reason and no failed hold leaves workeroutput empty."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(plugin, "_SESSION_WITHHELD", [])
    monkeypatch.setattr(plugin, "_WITHHELD_BY_NODEID", {"t.py::passed": "an unparseable module"})
    monkeypatch.setattr(plugin, "_FAILED_NODEIDS", set[str]())
    workeroutput: dict[str, object] = {}

    plugin.pytest_sessionfinish(
        SimpleNamespace(config=SimpleNamespace(workeroutput=workeroutput)), 0
    )

    assert workeroutput == {}


def test_a_session_without_xdist_writes_no_worker_output(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-worker session (no workeroutput) finishes without touching the config."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(plugin, "_SESSION_WITHHELD", ["a justfile change"])
    config = SimpleNamespace()

    plugin.pytest_sessionfinish(SimpleNamespace(config=config), 0)

    assert vars(config) == {}


def test_the_controller_ignores_a_worker_that_sent_no_withholding_payload(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A node down with no payload, or with no workeroutput, changes nothing."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    session_withheld: list[str] = []
    withheld_by_nodeid: dict[str, str] = {}
    monkeypatch.setattr(plugin, "_SESSION_WITHHELD", session_withheld)
    monkeypatch.setattr(plugin, "_WITHHELD_BY_NODEID", withheld_by_nodeid)

    plugin.pytest_testnodedown(SimpleNamespace(workeroutput={}), None)
    plugin.pytest_testnodedown(SimpleNamespace(), None)

    assert session_withheld == []
    assert withheld_by_nodeid == {}


def test_the_controller_adopts_the_first_worker_session_reason_only(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first worker's session reason is kept; a later one does not replace it."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    session_withheld: list[str] = []
    withheld_by_nodeid: dict[str, str] = {}
    monkeypatch.setattr(plugin, "_SESSION_WITHHELD", session_withheld)
    monkeypatch.setattr(plugin, "_WITHHELD_BY_NODEID", withheld_by_nodeid)

    def node(*, session: object, nodes: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            workeroutput={"livespec_flake_retry_withheld": {"session": session, "nodes": nodes}}
        )

    plugin.pytest_testnodedown(
        node(session="a justfile change", nodes={"a.py::t": "an unparseable module", "b": 3}),
        None,
    )
    plugin.pytest_testnodedown(node(session="a conftest.py change", nodes={}), None)

    assert session_withheld == ["a justfile change"]
    assert withheld_by_nodeid == {"a.py::t": "an unparseable module"}
