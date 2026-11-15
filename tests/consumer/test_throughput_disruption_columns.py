"""Consumer-tier: the throughput board's confound columns come from the committed quiet record.

`ci-runner/observability/throughput/apply-disruption-columns.sh` turns the
quiet record (`disruption-windows.json`) into two Honeycomb derived columns:
`pr.disruption`, which labels a pull request with the merge-quiet window or CI
pool stall its open-to-merge life overlaps (or `clean`), and `pr.lead_rule`,
which splits lead time by the 2026-11-14 start-rule change. The board's M2 and
M3 panels break down by them, so the confounds are part of the data a reader of
the board sees (maintainer direction 2026-11-15, plan throughput-metric).

THE HARNESS. The script is copied beside a fixture record and run unmodified
against a loopback stub of the Honeycomb derived-columns API that records every
request, so "converge writes only what differs" and "drift writes nothing" are
measured off the wire.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "ci-runner"
    / "observability"
    / "throughput"
    / "apply-disruption-columns.sh"
)
_RUN_TIMEOUT_S = 60

_RECORD: dict[str, Any] = {
    "dataset": "pr-throughput",
    "windows": [
        {
            "id": "stall",
            "kind": "ci-pool-stall",
            "repos": ["*"],
            "start": "2026-11-13T23:00:00Z",
            "end": "2026-11-14T07:00:00Z",
            "label": "fleet CI pool stall",
            "source": "fixture",
        },
        {
            "id": "quiet",
            "kind": "merge-quiet",
            "repos": ["repo-a"],
            "start": "2026-11-14T03:00:00Z",
            "end": "2026-11-14T05:00:00Z",
            "label": "repo-a merge-quiet",
            "source": "fixture",
        },
    ],
    "start_rule_change": {
        "at": "2026-11-14",
        "field": "pr.start_rule",
        "new_label": "new start rule",
        "old_label": "old start rule (not comparable)",
        "rebuild": "2026-11-21",
        "text": "The start rule changed.",
    },
}


@dataclass
class _World:
    columns: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    requests: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])


def _handler(world: _World) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _route(self) -> None:
            world.requests.append((self.command, self.path))
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            status, payload = 200, {"id": "written"}
            if self.command == "GET":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                found = world.columns.get(query.get("alias", [""])[0])
                status, payload = (200, found) if found else (404, {"error": "not found"})
            elif self.command == "POST" and isinstance(body, dict):
                status, payload = 201, dict(body, id="new-" + str(body.get("alias")))
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            _ = self.wfile.write(raw)

        def log_message(self, *_args: object) -> None:
            return

        do_GET = _route  # noqa: N815
        do_POST = _route  # noqa: N815
        do_PUT = _route  # noqa: N815

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


def _stage(tmp_path: Path, record: dict[str, Any]) -> Path:
    staged = tmp_path / _SCRIPT.name
    shutil.copy2(_SCRIPT, staged)
    _ = (tmp_path / "disruption-windows.json").write_text(json.dumps(record), encoding="utf-8")
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


def _columns(script: Path) -> dict[str, dict[str, Any]]:
    done = _run(script, "http://127.0.0.1:9", "--expressions")
    assert done.returncode == 0, done.stderr
    return {column["alias"]: column for column in json.loads(done.stdout)}


def test_a_merge_quiet_window_outranks_the_fleet_stall_and_is_scoped_to_its_repository(
    tmp_path: Path,
) -> None:
    expression = _columns(_stage(tmp_path, _RECORD))["pr.disruption"]["expression"]
    quiet = expression.index('"held: repo-a merge-quiet"')
    stall = expression.index('"slowed: fleet CI pool stall"')
    assert quiet < stall
    assert 'IN($repo, "repo-a")' in expression
    # 2026-11-14T05:00:00Z and 2026-11-14T03:00:00Z as epoch seconds: opened before the end, merged after the start.
    assert "LT(UNIX_TIMESTAMP($pr.opened_at), 1794632400)" in expression
    assert "GT(UNIX_TIMESTAMP($pr.merged_at), 1794625200)" in expression
    assert expression.endswith('"clean"))')


def test_the_lead_rule_column_splits_on_the_start_rule_field(tmp_path: Path) -> None:
    rule = _columns(_stage(tmp_path, _RECORD))["pr.lead_rule"]["expression"]
    assert rule == 'IF(EXISTS($pr.start_rule), "new start rule", "old start rule (not comparable)")'


def test_converge_creates_missing_columns_and_then_writes_nothing(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    script = _stage(tmp_path, _RECORD)
    first = _run(script, api)
    assert first.returncode == 0, first.stderr
    assert [m for m, _ in state.requests if m != "GET"] == ["POST", "POST"]
    for column in _columns(script).values():
        state.columns[column["alias"]] = dict(column, id="live-" + column["alias"])
    state.requests.clear()
    again = _run(script, api)
    assert again.returncode == 0, again.stderr
    assert state.requests
    assert all(method == "GET" for method, _ in state.requests)


def test_drift_reports_missing_columns_and_sends_only_reads(
    tmp_path: Path, world: tuple[_World, str]
) -> None:
    state, api = world
    done = _run(_stage(tmp_path, _RECORD), api, "--drift")
    assert done.returncode == 1
    assert "missing pr.disruption" in done.stdout
    assert "missing pr.lead_rule" in done.stdout
    assert all(method == "GET" for method, _ in state.requests)


def test_the_board_markdown_names_every_window_and_the_rule_change(tmp_path: Path) -> None:
    done = _run(_stage(tmp_path, _RECORD), "http://127.0.0.1:9", "--markdown")
    assert done.returncode == 0, done.stderr
    assert "held: repo-a merge-quiet" in done.stdout
    assert "slowed: fleet CI pool stall" in done.stdout
    assert "start rule changed 2026-11-14" in done.stdout


def test_a_window_that_ends_before_it_starts_is_refused(tmp_path: Path) -> None:
    record = json.loads(json.dumps(_RECORD))
    record["windows"][1]["end"] = "2026-11-14T02:00:00Z"
    done = _run(_stage(tmp_path, record), "http://127.0.0.1:9", "--expressions")
    assert done.returncode == 1
    assert "ends before it starts" in done.stderr
