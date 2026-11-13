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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

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
    assert "status=" not in read_runs, (
        "the run read must not send a server-side status filter: each Fabro build "
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
# must not send one: another build may know a different set.
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
_TERMINAL_KINDS = frozenset({"succeeded", "failed", "archived"})
_TOKEN = "fake-dev-token"
_READ_TASK = "Read this instance's non-terminal runs before retiring environments"


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
        for index in range(230)
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


def _strict_fabro_server(*, runs: list[dict[str, object]], seen: list[dict[str, list[str]]]):
    """A Fabro runs API that refuses an unknown status variant as the live one does."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — the stdlib handler's own name.
            query = parse_qs(urlsplit(self.path).query)
            seen.append({**query, "authorization": [self.headers.get("Authorization", "")]})
            unknown = [
                value for value in query.get("status", []) if value not in _LIVE_STATUS_FILTER_ENUM
            ]
            if unknown:
                expected = ", ".join(f"`{name}`" for name in _LIVE_STATUS_FILTER_ENUM)
                body = (
                    "Failed to deserialize query string: status[0]: unknown variant "
                    f"`{unknown[0]}`, expected one of {expected}"
                ).encode()
                self.send_response(400)
            else:
                limit = min(int(query.get("page[limit]", ["100"])[0]), 100)
                offset = int(query.get("page[offset]", ["0"])[0])
                page = runs[offset : offset + limit]
                more = offset + len(page) < len(runs)
                body = json.dumps(
                    {"data": page, "meta": {"has_more": more, "total": len(runs)}}
                ).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _ = self.wfile.write(body)

        def log_message(self, *_args: object, **_kwargs: object) -> None:  # pyright: ignore[reportImplicitOverride]
            """Silence the handler's per-request access log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run_read(
    *, tmp_path: Path, url: str, extra_env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "server.env"
    _ = env_file.write_text(f"FABRO_DEV_TOKEN=stale\nFABRO_DEV_TOKEN={_TOKEN}\n", encoding="utf-8")
    env = {
        "PATH": os.environ["PATH"],
        "FABRO_SERVER_ENV_FILE": str(env_file),
        "FABRO_SERVER_RUNS_URL": url,
        **extra_env,
    }
    return subprocess.run(
        ["/bin/bash", "-c", _read_runs_command()],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_the_run_read_keeps_every_non_terminal_run_from_a_server_that_refuses_unknown_status_variants(
    tmp_path: Path,
) -> None:
    """The guard pages every run and filters client-side, so no build's status enum can refuse it."""
    runs = _fake_runs()
    seen: list[dict[str, list[str]]] = []
    server = _strict_fabro_server(runs=runs, seen=seen)
    url = f"http://127.0.0.1:{server.server_port}/api/v1/runs"
    try:
        probe = subprocess.run(
            [
                "curl",
                "--silent",
                "--get",
                "--data-urlencode",
                "status=starting",
                "--write-out",
                "%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        result = _run_read(tmp_path=tmp_path, url=url, extra_env={})
    finally:
        server.shutdown()

    assert probe.stdout.endswith(
        "400"
    ), "the fake must refuse an unknown status variant as the live server does"
    assert "unknown variant `starting`" in probe.stdout
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    expected = [run["id"] for run in runs if _fake_kind(run=run) not in _TERMINAL_KINDS]
    facts = [
        [run["id"] for run in payload["data"]] == expected,
        {"run-paused", "run-starting", "run-legacy-shape"}
        <= {run["id"] for run in payload["data"]},
        "run-legacy-done" not in {run["id"] for run in payload["data"]},
        payload["meta"]["has_more"] is False,
        all("status" not in query for query in seen[1:]),
        all(query["authorization"] == [f"Bearer {_TOKEN}"] for query in seen[1:]),
        len(seen) - 1 == 3,
    ]
    assert all(facts), (facts, result.stdout[:400], seen[1:])


def test_the_run_read_reports_more_runs_when_its_page_bound_is_reached(tmp_path: Path) -> None:
    """A listing longer than the page bound reaches the role's has_more refusal, never a partial pass."""
    seen: list[dict[str, list[str]]] = []
    server = _strict_fabro_server(runs=_fake_runs(), seen=seen)
    try:
        result = _run_read(
            tmp_path=tmp_path,
            url=f"http://127.0.0.1:{server.server_port}/api/v1/runs",
            extra_env={"FABRO_SERVER_RUNS_MAX_PAGES": "2"},
        )
    finally:
        server.shutdown()

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [payload["meta"]["has_more"], len(seen)] == [True, 2]
