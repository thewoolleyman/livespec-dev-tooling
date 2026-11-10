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
import urllib.error
import urllib.request
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
    datasets: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    queries: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    requests: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])


def _read(world: _World, path: str) -> tuple[int, object]:
    """The stub's answer to a GET of `path`: (status, payload)."""
    parts = path.strip("/").split("/")
    kind, size = parts[1] if len(parts) > 1 else "", len(parts)
    payload: object | None = None
    if kind == "triggers" and size == 3:
        payload = world.triggers
    elif kind == "triggers" and size == 4:
        found = [t for t in world.triggers if t["id"] == parts[3]]
        if not found:
            return 404, {"error": "none"}
        payload = found[0]
    elif kind == "boards" and size == 2:
        payload = world.boards
    elif kind == "datasets" and size == 3:
        payload = world.datasets[parts[2]]
    elif kind == "query_annotations" and size == 4:
        payload = world.annotations[parts[3]]
    elif kind == "queries" and size == 4:
        payload = world.queries[parts[3]]
    if payload is not None:
        return 200, payload
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
    world.datasets["metrics"] = {"slug": "metrics", "name": "Metrics"}
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
    live = {
        k: copy.deepcopy(v) for k, v in _BOARD.items() if k not in {"layout_generation", "panels"}
    }
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
                "dataset": "Metrics",
            },
        },
    ]
    return live


def _only_reads(world: _World) -> bool:
    return bool(world.requests) and all(method == "GET" for method, _ in world.requests)


def test_the_stub_records_a_write_and_answers_it_with_success(
    world: tuple[_World, str],
) -> None:
    state, api = world
    post = urllib.request.Request(api + "/1/triggers/metrics", data=b"{}", method="POST")  # noqa: S310

    with urllib.request.urlopen(post, timeout=_RUN_TIMEOUT_S) as reply:  # noqa: S310
        assert reply.status == 200

    assert state.requests == [("POST", "/1/triggers/metrics")]
    assert not _only_reads(state)


def test_the_stub_answers_a_path_it_does_not_route_with_not_found(
    world: tuple[_World, str],
) -> None:
    _, api = world

    with pytest.raises(urllib.error.HTTPError) as refused:
        _ = urllib.request.urlopen(api + "/1/nothing", timeout=_RUN_TIMEOUT_S)  # noqa: S310

    assert refused.value.code == 404


def test_the_stub_answers_a_missing_trigger_with_not_found(
    world: tuple[_World, str],
) -> None:
    state, api = world

    with pytest.raises(urllib.error.HTTPError) as refused:
        _ = urllib.request.urlopen(api + "/1/triggers/metrics/missing", timeout=_RUN_TIMEOUT_S)  # noqa: S310

    assert refused.value.code == 404
    assert state.requests == [("GET", "/1/triggers/metrics/missing")]


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


def test_board_drift_reports_a_query_panel_with_a_different_dataset(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    live = _live_board(state)
    live["panels"][1]["query_panel"]["dataset"] = "OtherMetrics"
    state.boards = [live]
    script = _stage(tmp_path, _APPLY_BOARDS, _BOARD)

    result = _run(script, api, "--drift")

    assert result.returncode != 0, result.stdout + result.stderr
    assert 'panel Load by host.dataset: committed "Metrics" live "OtherMetrics"' in result.stdout
    assert _only_reads(state), state.requests


def test_board_apply_reuses_a_query_panel_with_a_display_name_dataset(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    state.boards = [_live_board(state)]
    script = _stage(tmp_path, _APPLY_BOARDS, _BOARD)

    result = _run(script, api)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "panel reused load [metrics] query=q1" in result.stdout
    assert not any(
        method == "POST" and path.startswith(("/1/queries/", "/1/query_annotations/"))
        for method, path in state.requests
    ), state.requests


def test_board_apply_reuses_a_query_panel_when_the_api_adds_an_empty_filter_join_column(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    definition = copy.deepcopy(_BOARD)
    filters = [{"column": "host.name", "op": "=", "value": "fixture-host"}]
    definition["panels"][1]["query"]["filters"] = filters
    live = _live_board(state)
    state.queries["q1"]["filters"] = [
        {**filters[0], "join_column": ""},
    ]
    state.boards = [live]
    script = _stage(tmp_path, _APPLY_BOARDS, definition)

    result = _run(script, api)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "panel reused load [metrics] query=q1" in result.stdout
    assert not any(
        method == "POST" and path.startswith(("/1/queries/", "/1/query_annotations/"))
        for method, path in state.requests
    ), state.requests


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
