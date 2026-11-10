"""Consumer-tier: the read-only drift mode of the Honeycomb board and trigger appliers.

`SPECIFICATION/non-functional-requirements.md`, in its runner-pool node
telemetry section, paragraph on board and trigger drift: `apply-boards.sh` and
`apply-triggers.sh` each offer a read-only drift mode that reads the live definition by the
committed definition's name, leaves out what the service assigns, prints the
name and each differing field or panel, reports an absent name as missing,
exits non-zero on any difference and never sends a create, update or delete.

THE HARNESS. Each applier is copied beside ONE fixture definition (the scripts
glob `*.json` in their own directory) and run unmodified against a stub of the
Honeycomb API on a loopback port. The stub answers GETs from a world the test
composes and RECORDS every request, so "sent no create or update request" is
measured off the wire rather than taken from the flag. A non-GET is answered
with a success, so a drift mode that wrote would still look healthy to the
script and only the recorded methods would convict it.

THE CONTROL ARM. Each applier is also run against a live world that matches
the committed definition, carrying server-assigned ids and timestamps, and must
exit zero: a drift mode that reported every definition as different would
otherwise satisfy the convicting arms.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_OBSERVABILITY = Path(__file__).resolve().parents[2] / "ci-runner" / "observability"
_APPLY_TRIGGERS = _OBSERVABILITY / "triggers" / "apply-triggers.sh"
_APPLY_BOARDS = _OBSERVABILITY / "boards" / "apply-boards.sh"
_RUN_TIMEOUT_S = 60

_TRIGGER: dict[str, Any] = {
    "name": "Fixture dead-man — silent 20 min",
    "description": "Fires when nothing arrives.",
    "query": {
        "calculations": [{"op": "COUNT_DATAPOINTS", "column": "fixture.gauge"}],
        "filters": [{"column": "host.name", "op": "=", "value": "fixture-host"}],
        "time_range": 1200,
    },
    "threshold": {"op": "<", "value": 1, "exceeded_limit": 1},
    "frequency": 600,
    "alert_type": "on_change",
    "recipients": [{"id": "aaa"}, {"id": "bbb"}],
    "tags": [{"key": "host", "value": "fixture-host"}, {"key": "kind", "value": "dead-man"}],
}

_BOARD: dict[str, Any] = {
    "name": "Fixture board",
    "description": "A board.",
    "type": "flexible",
    "layout_generation": "manual",
    "tags": [{"key": "kind", "value": "board"}],
    "panels": [
        {
            "type": "text",
            "position": {"x_coordinate": 0, "y_coordinate": 0, "height": 2, "width": 12},
            "text_panel": {"content": "# Heading"},
        },
        {
            "type": "query",
            "key": "load",
            "dataset": "metrics",
            "position": {"x_coordinate": 0, "y_coordinate": 2, "height": 6, "width": 6},
            "query_style": "graph",
            "query": {
                "calculations": [{"op": "MAX", "column": "fixture.load"}],
                "time_range": 7200,
            },
            "annotation": {"name": "Load by host", "description": "Peak load."},
        },
    ],
}


@dataclass
class _World:
    """What the stub answers, and every request it was sent."""

    triggers: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    boards: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    annotations: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    queries: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    requests: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])


def _read(world: _World, path: str) -> tuple[int, object]:
    """The stub's answer to a GET of `path`: (status, payload)."""
    parts = path.strip("/").split("/")
    kind, size = parts[1] if len(parts) > 1 else "", len(parts)
    if kind == "triggers" and size == 3:
        return 200, world.triggers
    if kind == "triggers" and size == 4:
        found = [t for t in world.triggers if t["id"] == parts[3]]
        return (200, found[0]) if found else (404, {"error": "none"})
    if kind == "boards" and size == 2:
        return 200, world.boards
    if kind == "query_annotations" and size == 4:
        return 200, world.annotations[parts[3]]
    if kind == "queries" and size == 4:
        return 200, world.queries[parts[3]]
    return 404, {"error": "unrouted " + path}


def _handler(world: _World) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _route(self) -> None:
            world.requests.append((self.command, self.path))
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                _ = self.rfile.read(length)
            if self.command == "GET":
                status, payload = _read(world, self.path)
            else:
                status, payload = 200, {"id": "written"}
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            _ = self.wfile.write(raw)

        do_GET = _route  # noqa: N815
        do_POST = _route  # noqa: N815
        do_PUT = _route  # noqa: N815
        do_PATCH = _route  # noqa: N815
        do_DELETE = _route  # noqa: N815

    return Handler


@pytest.fixture
def world() -> Iterator[tuple[_World, str]]:
    state = _World()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _stage(tmp_path: Path, script: Path, definition: dict[str, Any]) -> Path:
    directory = tmp_path / script.parent.name
    directory.mkdir()
    staged = directory / script.name
    shutil.copy2(script, staged)
    _ = (directory / "fixture.json").write_text(json.dumps(definition), encoding="utf-8")
    return staged


def _run(script: Path, api: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", "/"),
        "HONEYCOMB_API": api,
        "HONEYCOMB_CONFIG_KEY_LIVESPEC": "stub-key",
    }
    return subprocess.run(
        ["bash", str(script), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_S,
        check=False,
    )


def _live_trigger() -> dict[str, Any]:
    live = copy.deepcopy(_TRIGGER)
    live.update(
        {
            "id": "trig1",
            "created_at": "2026-11-01T00:00:00Z",
            "updated_at": "2026-11-02T00:00:00Z",
            "disabled": False,
            "triggered": False,
            "dataset_slug": "metrics",
        }
    )
    live["query"]["filter_combination"] = "AND"
    live["query"]["granularity"] = 600
    live["recipients"] = [
        {"id": "bbb", "type": "email", "target": "b@example.test"},
        {"id": "aaa", "type": "slack", "target": "#a"},
    ]
    live["tags"] = list(reversed(live["tags"]))
    return live


def _live_board(world: _World) -> dict[str, Any]:
    world.annotations["ann1"] = {
        "id": "ann1",
        "name": "Load by host",
        "description": "Peak load.",
        "query_id": "q1",
    }
    world.queries["q1"] = {
        "id": "q1",
        "calculations": [{"op": "MAX", "column": "fixture.load"}],
        "time_range": 7200,
        "granularity": 0,
        "filter_combination": "AND",
    }
    live = {k: copy.deepcopy(v) for k, v in _BOARD.items() if k != "panels"}
    live.update({"id": "board1", "created_at": "2026-11-01T00:00:00Z", "links": {"board_url": "u"}})
    live["panels"] = [
        {
            "type": "text",
            "position": _BOARD["panels"][0]["position"],
            "text_panel": {"content": "# Heading"},
        },
        {
            "type": "query",
            "position": _BOARD["panels"][1]["position"],
            "query_panel": {
                "query_id": "q1",
                "query_annotation_id": "ann1",
                "query_style": "graph",
                "dataset": "metrics",
            },
        },
    ]
    return live


def _only_reads(world: _World) -> bool:
    return bool(world.requests) and all(method == "GET" for method, _ in world.requests)


def test_trigger_drift_reports_each_differing_field_and_writes_nothing(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    live = _live_trigger()
    live["threshold"]["value"] = 5
    live["frequency"] = 300
    state.triggers = [live]
    script = _stage(tmp_path, _APPLY_TRIGGERS, _TRIGGER)

    result = _run(script, api, "--drift")

    assert result.returncode != 0, result.stdout + result.stderr
    report = result.stdout + result.stderr
    assert _TRIGGER["name"] in report
    assert "threshold" in report
    assert "frequency" in report
    assert "alert_type" not in report
    assert _only_reads(state), state.requests


def test_trigger_drift_matching_live_exits_zero_ignoring_server_assigned_fields(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    state.triggers = [_live_trigger()]
    script = _stage(tmp_path, _APPLY_TRIGGERS, _TRIGGER)

    result = _run(script, api, "--drift")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _only_reads(state), state.requests


def test_trigger_drift_reports_a_name_absent_from_the_api_as_missing(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    other = _live_trigger()
    other["name"] = "Some other trigger"
    state.triggers = [other]
    script = _stage(tmp_path, _APPLY_TRIGGERS, _TRIGGER)

    result = _run(script, api, "--drift")

    assert result.returncode != 0, result.stdout + result.stderr
    report = result.stdout + result.stderr
    assert "missing" in report.lower()
    assert _TRIGGER["name"] in report
    assert _only_reads(state), state.requests


def test_board_drift_reports_each_differing_panel_and_field_and_writes_nothing(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    live = _live_board(state)
    live["description"] = "Edited by hand."
    state.queries["q1"]["calculations"] = [{"op": "MIN", "column": "fixture.load"}]
    state.boards = [live]
    script = _stage(tmp_path, _APPLY_BOARDS, _BOARD)

    result = _run(script, api, "--drift")

    assert result.returncode != 0, result.stdout + result.stderr
    report = result.stdout + result.stderr
    assert _BOARD["name"] in report
    assert "description" in report
    assert "Load by host" in report
    assert "calculations" in report
    assert "# Heading" not in report
    assert _only_reads(state), state.requests


def test_board_drift_reports_a_changed_text_panel_and_a_removed_panel(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    live = _live_board(state)
    live["panels"][0]["text_panel"]["content"] = "# Edited"
    del live["panels"][1]
    state.boards = [live]
    script = _stage(tmp_path, _APPLY_BOARDS, _BOARD)

    result = _run(script, api, "--drift")

    assert result.returncode != 0, result.stdout + result.stderr
    report = result.stdout + result.stderr
    assert "text_panel" in report
    assert "Load by host" in report
    assert _only_reads(state), state.requests


def test_board_drift_matching_live_exits_zero_ignoring_server_assigned_fields(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    state.boards = [_live_board(state)]
    script = _stage(tmp_path, _APPLY_BOARDS, _BOARD)

    result = _run(script, api, "--drift")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _only_reads(state), state.requests


def test_board_drift_reports_a_name_absent_from_the_api_as_missing(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    other = _live_board(state)
    other["name"] = "Some other board"
    state.boards = [other]
    script = _stage(tmp_path, _APPLY_BOARDS, _BOARD)

    result = _run(script, api, "--drift")

    assert result.returncode != 0, result.stdout + result.stderr
    report = result.stdout + result.stderr
    assert "missing" in report.lower()
    assert _BOARD["name"] in report
    assert _only_reads(state), state.requests
