"""Consumer-tier coverage for retiring Fabro sandbox environments.

The catalog is state owned by the running Fabro instance, not a rendered file.
This scenario therefore reads the role's task graph: it must first obtain every
non-terminal run's persisted settings, reject an environment still selected by
one of them, and only then issue the authenticated catalog DELETE.  Reading the
task graph keeps the safety ordering observable without requiring a reachable
factory host in a repository test.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from pathlib import Path
from typing import TypeAlias
from urllib.parse import parse_qs, urlsplit

import jinja2
import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_ROOT = Path(__file__).resolve().parents[2]
_MAIN = _ROOT / "ansible" / "roles" / "fabro_server" / "tasks" / "main.yml"
_RETIRED_ENVIRONMENT = _MAIN.with_name("retired_environment.yml")
_RETIRED_RUN = _MAIN.with_name("retired_run.yml")
_INVENTORY = _ROOT / "ansible" / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_HOST_VARS = _ROOT / "ansible" / "roles" / "fabro_server" / "HOST_VARS.md"
_HEADING_COVERAGE = _ROOT / "tests" / "heading-coverage.json"
_NON_TERMINAL_STATUSES = (
    "pending",
    "runnable",
    "initializing",
    "starting",
    "running",
    "paused",
    "blocked",
    "removing",
)


def _tasks(*, source: Path) -> list[tuple[str, str]]:
    """Return each column-zero Ansible task in source order."""
    assert source.is_file(), f"the role must carry {source.name}"
    text = source.read_text(encoding="utf-8")
    starts = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert starts, f"{source.name} must have named top-level tasks"
    return [
        (body.split("\n", 1)[0][len("- name: ") :].strip(), body)
        for start, stop in pairwise([*starts, len(text)])
        for body in [text[start:stop]]
    ]


def _task(*, source: Path, name: str) -> str:
    """Return one uniquely named role task."""
    matching = [body for task_name, body in _tasks(source=source) if task_name == name]
    assert len(matching) == 1, f"{source.name} must carry exactly one {name!r} task"
    return matching[0]


def _index(*, source: Path, name: str) -> int:
    """Return a task's position, preserving the role's safety order."""
    names = [task_name for task_name, _ in _tasks(source=source)]
    assert name in names, f"{source.name} must carry {name!r}"
    return names.index(name)


def test_the_role_reads_all_live_runs_before_retiring_catalog_entries() -> None:
    """A live run blocks every delete, and a 404 delete is an unchanged converge."""
    resolve = _task(source=_MAIN, name="Resolve this instance's axes")
    assert "fabro_server_retired_environments" in resolve

    overlap = "Refuse an environment id declared both active and retired"
    first_write = "Create the shared libexec directory"
    assert _index(source=_MAIN, name=overlap) < _index(source=_MAIN, name=first_write)

    read_runs = _task(
        source=_MAIN, name="Read this instance's non-terminal runs before retiring environments"
    )
    assert "/api/v1/runs" in read_runs
    assert "--header @-" in read_runs
    assert "FABRO_SERVER_ENV_FILE" in read_runs
    for status in ("pending", "starting", "running", "paused"):
        assert f"status={status}" not in read_runs, (
            "the run read must not filter on a status list: each Fabro build "
            "refuses a status variant it does not know"
        )
    assert "include_tasks: retired_run.yml" in _task(
        source=_MAIN, name="Read every non-terminal run's selected environment"
    )
    assert (
        _index(source=_MAIN, name="Read every non-terminal run's selected environment")
        < _index(
            source=_MAIN, name="Refuse to retire an environment selected by a non-terminal run"
        )
        < _index(source=_MAIN, name="Delete each retired sandbox environment")
    )

    settings = _task(source=_RETIRED_RUN, name="Read this non-terminal run's settings")
    assert "/settings" in settings
    assert "--header @-" in settings
    assert "FABRO_SERVER_ENV_FILE" in settings
    assert "environment.id" in _task(
        source=_RETIRED_RUN, name="Record this non-terminal run's selected environment"
    )

    delete = _task(
        source=_RETIRED_ENVIRONMENT,
        name="Delete this retired environment from the instance's catalog",
    )
    assert "--request DELETE" in delete
    assert "--header @-" in delete
    assert "FABRO_SERVER_ENV_FILE" in delete
    assert "204" in delete and "404" in delete
    assert "changed_when" in delete


def _live_run_settings(*, environment: str) -> dict[str, object]:
    """GET /api/v1/runs/<id>/settings as the serving build answers it.

    The handler returns the run spec's `WorkflowSettings`, whose top level is
    the `project`, `workflow` and `run` namespaces; the selected environment is
    `run.environment` (`RunEnvironmentSettings`, carrying its catalog `id`).
    """
    return {
        "project": {"metadata": {}},
        "workflow": {"metadata": {}},
        "run": {
            "metadata": {},
            "environment": {
                "id": environment,
                "provider": "docker",
                "image": {},
                "resources": {},
                "network": {},
                "lifecycle": {},
                "labels": {},
                "env": {},
            },
        },
    }


def test_the_recorded_environment_is_the_one_the_live_settings_select() -> None:
    """The role reads the selected environment where the settings answer carries it."""
    tasks = yaml.safe_load(_RETIRED_RUN.read_text(encoding="utf-8"))
    (record,) = [
        task
        for task in tasks
        if task["name"] == "Record this non-terminal run's selected environment"
    ]
    expression = record["ansible.builtin.set_fact"]["fabro_server_retired_run_environment"][
        "environment"
    ]
    # A path the answer does not carry renders empty rather than raising, so a
    # wrong path reads as the wrong environment.
    environment = jinja2.Environment(undefined=jinja2.ChainableUndefined, autoescape=False)
    environment.filters["from_json"] = json.loads
    answer = json.dumps(_live_run_settings(environment="livespec-ci-k8s"))
    selected = environment.from_string(expression).render(
        fabro_server_retired_run={"id": "01M79KYY1KVVZ3MFDZS5CEQ8E9"},
        fabro_server_retired_run_settings_read={"stdout": answer},
    )
    assert selected == "livespec-ci-k8s", (
        "the run settings answer carries the selected environment at "
        "run.environment.id; a guard reading any other path aborts the converge "
        "on the first non-terminal run"
    )


def _instance_block(*, unit: str) -> str:
    """Return one inventory instance mapping, excluding its siblings."""
    text = _INVENTORY.read_text(encoding="utf-8")
    opener = f"  - unit_name: {unit}\n"
    start = text.find(opener)
    assert start >= 0, f"gmktec inventory must declare {unit}"
    stop = text.find("\n  - unit_name: ", start + len(opener))
    return text[start:] if stop < 0 else text[start:stop]


def _list_items(*, block: str, key: str) -> list[str]:
    """Return scalar list items from one instance mapping."""
    match = re.search(
        rf"^    {re.escape(key)}:\n(?P<items>(?:^      - [^\n]+\n)+)", block, re.MULTILINE
    )
    return [] if match is None else [line[8:] for line in match["items"].splitlines()]


def _environment_ids(*, block: str) -> list[str]:
    """Return the catalog ids that one mapping still declares active."""
    return re.findall(r"^      - id: ([^\s]+)$", block, re.MULTILINE)


def test_gmktec_declares_the_completed_environment_rename_and_its_operator_interface() -> None:
    """The fleet and homelab mappings retire only their replaced ids."""
    fleet = _instance_block(unit="fabro-server")
    candidate = _instance_block(unit="fabro-server-candidate")
    homelab = _instance_block(unit="fabro-server-mi-homelab")

    assert not {"livespec-ci", "livespec-ci-k8s", "livespec-ci-rust"} & set(
        _environment_ids(block=fleet)
    )
    assert _list_items(block=fleet, key="retired_environments") == [
        "livespec-ci",
        "livespec-ci-k8s",
        "livespec-ci-rust",
    ]
    assert "retired_environments" not in candidate
    assert {"livespec-ci", "livespec-ci-k8s", "livespec-ci-rust"} <= set(
        _environment_ids(block=candidate)
    )
    assert _environment_ids(block=homelab) == ["factory-python"]
    assert _list_items(block=homelab, key="retired_environments") == ["livespec-ci"]

    document = _HOST_VARS.read_text(encoding="utf-8")
    assert "| `retired_environments` |" in document
    assert "DELETE /api/v1/environments/{id}" in document
    assert "non-terminal run" in document
    for status in _NON_TERMINAL_STATUSES:
        assert f"`{status}`" in document, f"HOST_VARS.md must name the {status} run status"

    coverage = json.loads(_HEADING_COVERAGE.read_text(encoding="utf-8"))
    row = next(
        row
        for row in coverage
        if row["heading"]
        == "## Scenario: the fabro_server role deletes an instance's retired sandbox environments"
    )
    assert row["test"] == (
        "tests.consumer.test_fabro_retired_environment_catalog_scenario."
        "test_the_role_reads_all_live_runs_before_retiring_catalog_entries"
    )


# The run-status enum the live Fabro servers accept as a `status` query filter,
# read from each reachable gmktec instance (:32276, :32277 and :32278 answered
# with this same list on 2026-11-13; hp-xubuntu and vps refused connections).
# A filter naming anything else is refused with HTTP 400, which is why the role
# must not send a status list: another build may know a different set.
_LIVE_STATUS_FILTER_ENUM = (
    "pending",
    "runnable",
    "initializing",
    "running",
    "blocked",
    "succeeded",
    "failed",
    "archived",
    "removing",
)
# A Fabro listing with no status filter hides `removing` and archived runs
# (fabro-store run_summary_store.rs, RunSummaryVisibility::Default, at fabro
# 3b3781888). A `removing` run still holds its environment, so the role must
# ask for it by name.
_HIDDEN_BY_DEFAULT = frozenset({"removing", "archived"})
_TERMINAL_KINDS = frozenset({"succeeded", "failed", "archived"})
_TOKEN = "fake-dev-token"
_READ_TASK = "Read this instance's non-terminal runs before retiring environments"

_Query: TypeAlias = "dict[str, list[str]]"
_Responder: TypeAlias = "Callable[[_Query], tuple[int, bytes]]"


def _read_runs_command() -> str:
    """Return the run-read task's shell, exactly as the role ships it."""
    tasks = yaml.safe_load(_MAIN.read_text(encoding="utf-8"))
    matching = [task for task in tasks if task.get("name") == _READ_TASK]
    assert len(matching) == 1, f"main.yml must carry exactly one {_READ_TASK!r} task"
    return matching[0]["ansible.builtin.shell"]["cmd"]


def _fake_runs() -> list[dict[str, object]]:
    """Runs in the shapes the live servers return, plus kinds no filter enum names."""
    kinds = ["running", "failed", "succeeded", "blocked", "pending", "archived", "removing"]
    runs: list[dict[str, object]] = [
        {"id": f"run-{index:03d}", "lifecycle": {"status": {"kind": kinds[index % len(kinds)]}}}
        for index in range(460)
    ]
    runs.append({"id": "run-paused", "lifecycle": {"status": {"kind": "paused"}}})
    runs.append({"id": "run-starting", "lifecycle": {"status": {"kind": "starting"}}})
    runs.append({"id": "run-legacy-shape", "status": "running"})
    runs.append({"id": "run-legacy-done", "status": "succeeded"})
    return runs


def _fake_kind(*, run: dict[str, object]) -> object:
    """The status a fake run reports, in either live shape."""
    lifecycle = run.get("lifecycle")
    if isinstance(lifecycle, dict):
        return lifecycle["status"]["kind"]  # pyright: ignore[reportUnknownVariableType]
    return run["status"]


def _fabro_listing(*, runs: list[dict[str, object]]) -> _Responder:
    """GET /api/v1/runs as the live server answers it, visibility rules included."""

    def respond(query: _Query) -> tuple[int, bytes]:
        statuses = query.get("status", [])
        unknown = [value for value in statuses if value not in _LIVE_STATUS_FILTER_ENUM]
        if unknown:
            expected = ", ".join(f"`{name}`" for name in _LIVE_STATUS_FILTER_ENUM)
            message = (
                "Failed to deserialize query string: status[0]: unknown variant "
                f"`{unknown[0]}`, expected one of {expected}"
            )
            return 400, message.encode()
        visible = [
            run
            for run in runs
            if (_fake_kind(run=run) in statuses)
            or (not statuses and _fake_kind(run=run) not in _HIDDEN_BY_DEFAULT)
        ]
        limit = min(int(query.get("page[limit]", ["100"])[0]), 100)
        offset = int(query.get("page[offset]", ["0"])[0])
        page = visible[offset : offset + limit]
        more = offset + len(page) < len(visible)
        body = {"data": page, "meta": {"has_more": more, "total": len(visible)}}
        return 200, json.dumps(body).encode()

    return respond


def _serve(*, responder: _Responder, seen: list[_Query]) -> ThreadingHTTPServer:
    """Serve one scripted responder on loopback, recording each request's query."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — the stdlib handler's own name.
            query = parse_qs(urlsplit(self.path).query)
            seen.append({**query, "authorization": [self.headers.get("Authorization", "")]})
            status, body = responder(query)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _ = self.wfile.write(body)

        def log_message(self, *_args: object, **_kwargs: object) -> None:  # pyright: ignore[reportImplicitOverride]
            """Silence the handler's per-request access log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run_read(
    *, tmp_path: Path, responder: _Responder, seen: list[_Query], extra_env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run the role's real run-read shell against one scripted server."""
    env_file = tmp_path / "server.env"
    _ = env_file.write_text(f"FABRO_DEV_TOKEN=stale\nFABRO_DEV_TOKEN={_TOKEN}\n", encoding="utf-8")
    server = _serve(responder=responder, seen=seen)
    env = {
        "PATH": os.environ["PATH"],
        "FABRO_SERVER_ENV_FILE": str(env_file),
        "FABRO_SERVER_RUNS_URL": f"http://127.0.0.1:{server.server_port}/api/v1/runs",
        **extra_env,
    }
    try:
        return subprocess.run(
            ["/bin/bash", "-c", _read_runs_command()],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
    finally:
        server.shutdown()


def test_the_run_read_keeps_every_non_terminal_run_including_the_removing_runs_fabro_hides(
    tmp_path: Path,
) -> None:
    """Every status page is read, `removing` is asked for by name, and only terminal runs drop."""
    runs = _fake_runs()
    seen: list[_Query] = []
    listing = _fabro_listing(runs=runs)
    refused_status, refused_body = listing({"status": ["starting"]})
    result = _run_read(tmp_path=tmp_path, responder=listing, seen=seen, extra_env={})

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    kept = [run["id"] for run in payload["data"]]
    expected = {run["id"] for run in runs if _fake_kind(run=run) not in _TERMINAL_KINDS}
    removing = {run["id"] for run in runs if _fake_kind(run=run) == "removing"}
    facts = [
        refused_status == 400,
        b"unknown variant `starting`" in refused_body,
        set(kept) == expected,
        len(kept) == len(set(kept)),
        removing <= set(kept),
        {"run-paused", "run-starting", "run-legacy-shape"} <= set(kept),
        "run-legacy-done" not in kept,
        payload["meta"]["has_more"] is False,
        all(query.get("status", ["removing"]) == ["removing"] for query in seen),
        any(query.get("status") == ["removing"] for query in seen),
        all(query["authorization"] == [f"Bearer {_TOKEN}"] for query in seen),
    ]
    assert all(facts), (facts, result.stdout[:400], seen)


def test_the_run_read_reports_no_run_when_every_run_is_terminal(tmp_path: Path) -> None:
    """A listing of only finished runs lets the retirement proceed with nothing held."""
    runs: list[dict[str, object]] = [
        {"id": f"done-{index}", "lifecycle": {"status": {"kind": kind}}}
        for index, kind in enumerate(["succeeded", "failed", "archived"] * 50)
    ]
    seen: list[_Query] = []
    result = _run_read(
        tmp_path=tmp_path, responder=_fabro_listing(runs=runs), seen=seen, extra_env={}
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [payload["data"], payload["meta"]["has_more"]] == [[], False]


def test_the_run_read_reports_more_runs_when_its_page_bound_is_reached(tmp_path: Path) -> None:
    """A listing longer than the page bound reaches the role's has_more refusal, never a partial pass."""
    seen: list[_Query] = []
    result = _run_read(
        tmp_path=tmp_path,
        responder=_fabro_listing(runs=_fake_runs()),
        seen=seen,
        extra_env={"FABRO_SERVER_RUNS_MAX_PAGES": "1"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [payload["meta"]["has_more"], len(seen)] == [True, 2]


def _answering(*, status: int, body: str) -> _Responder:
    """A server that gives every request the same answer."""

    def respond(query: _Query) -> tuple[int, bytes]:
        _ = query
        return status, body.encode()

    return respond


_EMPTY_PAGE = (200, json.dumps({"data": [], "meta": {"has_more": False}}).encode())

_UNREADABLE_ANSWERS: dict[str, _Responder] = {
    "server error": _answering(status=500, body='{"errors": []}'),
    "status filter refused": _answering(status=400, body="unknown variant `removing`"),
    "empty object": _answering(status=200, body="{}"),
    "no meta": _answering(status=200, body='{"data": []}'),
    "no has_more": _answering(status=200, body='{"data": [], "meta": {"total": 0}}'),
    "has_more not a boolean": _answering(
        status=200, body='{"data": [], "meta": {"has_more": "false"}}'
    ),
    "data not a list": _answering(status=200, body='{"data": "x", "meta": {"has_more": false}}'),
    "body not an object": _answering(status=200, body="[]"),
}


def _on_pass(*, answer: _Responder, read_pass: str) -> _Responder:
    """Give one read pass the unreadable answer and the other a readable empty page."""

    def respond(query: _Query) -> tuple[int, bytes]:
        if ("status" in query) == (read_pass == "removing"):
            return answer(query)
        return _EMPTY_PAGE

    return respond


@pytest.mark.parametrize("read_pass", ["listing", "removing"])
@pytest.mark.parametrize("shape", sorted(_UNREADABLE_ANSWERS))
def test_the_run_read_refuses_a_listing_it_cannot_read_completely(
    tmp_path: Path, shape: str, read_pass: str
) -> None:
    """An unreadable page on EITHER pass fails the task, never proceeds as empty."""
    seen: list[_Query] = []
    result = _run_read(
        tmp_path=tmp_path,
        responder=_on_pass(answer=_UNREADABLE_ANSWERS[shape], read_pass=read_pass),
        seen=seen,
        extra_env={},
    )

    facts = [
        result.returncode != 0,
        "run listing refused" in result.stderr,
        _TOKEN not in result.stdout + result.stderr,
        (read_pass == "listing") or any(query.get("status") == ["removing"] for query in seen),
    ]
    assert all(facts), (shape, read_pass, facts, result.stdout, result.stderr)


def test_the_run_read_holds_a_run_both_passes_list_once(tmp_path: Path) -> None:
    """A run moving to `removing` between the passes is held once, under either reading."""
    listed = {"id": "run-moving", "lifecycle": {"status": {"kind": "running"}}}
    moving = {"id": "run-moving", "lifecycle": {"status": {"kind": "removing"}}}
    finished = {"id": "run-late", "lifecycle": {"status": {"kind": "succeeded"}}}
    late = {"id": "run-late", "lifecycle": {"status": {"kind": "removing"}}}

    def respond(query: _Query) -> tuple[int, bytes]:
        data = [moving, late] if "status" in query else [listed, finished]
        return 200, json.dumps({"data": data, "meta": {"has_more": False}}).encode()

    seen: list[_Query] = []
    result = _run_read(tmp_path=tmp_path, responder=respond, seen=seen, extra_env={})

    assert result.returncode == 0, result.stderr
    held = [run["id"] for run in json.loads(result.stdout)["data"]]
    assert held == ["run-moving", "run-late"]
