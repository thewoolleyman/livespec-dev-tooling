"""Consumer-tier coverage for the retired-environment DELETE against Fabro's API.

Fabro's `DELETE /api/v1/environments/{id}` requires an `If-Match` header carrying
the environment's current revision, and answers `428 Precondition Required`
without one. These scenarios run the role's real delete shell against a loopback
server that enforces that precondition the way the serving build does, so a
delete that omits the header fails here exactly as it failed on gmktec's :32276
(HTTP 428, 2026-11-13).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_ROOT = Path(__file__).resolve().parents[2]
_RETIRED_ENVIRONMENT = (
    _ROOT / "ansible" / "roles" / "fabro_server" / "tasks" / "retired_environment.yml"
)
_DELETE_TASK = "Delete this retired environment from the instance's catalog"
_TOKEN = "fake-dev-token"
_ENVIRONMENT = "livespec-ci"
_REVISION = "01JX3REVISION0000000000007"


def _delete_task() -> dict[str, Any]:
    """Return the role's delete task, exactly as it ships."""
    tasks = yaml.safe_load(_RETIRED_ENVIRONMENT.read_text(encoding="utf-8"))
    (task,) = [task for task in tasks if task.get("name") == _DELETE_TASK]
    return task


class _Catalog:
    """One environment catalog that enforces Fabro's DELETE precondition."""

    def __init__(self, *, holds: bool, revision_at_delete: str = _REVISION) -> None:
        self.holds = holds
        self.revision_at_delete = revision_at_delete
        self.requests: list[tuple[str, str, str]] = []

    def answer(self, *, method: str, authorization: str, if_match: str) -> tuple[int, bytes]:
        """Answer one request the way the serving build's handlers do."""
        self.requests.append((method, authorization, if_match))
        if not self.holds:
            return 404, b'{"errors":[{"status":"404","title":"environment not found"}]}'
        if method == "GET":
            body = {"id": _ENVIRONMENT, "revision": _REVISION, "provider": "docker"}
            return 200, json.dumps(body).encode("utf-8")
        if not if_match:
            return 428, b'{"errors":[{"status":"428","title":"If-Match header is required"}]}'
        if if_match.strip().strip('"') != self.revision_at_delete:
            return 409, b'{"errors":[{"status":"409","title":"environment revision is stale"}]}'
        self.holds = False
        return 204, b""


def _serve(*, catalog: _Catalog) -> ThreadingHTTPServer:
    """Serve one catalog on loopback for GET and DELETE of the environment path."""

    class _Handler(BaseHTTPRequestHandler):
        def _respond(self) -> None:
            assert self.path == f"/api/v1/environments/{_ENVIRONMENT}", self.path
            status, body = catalog.answer(
                method=self.command,
                authorization=self.headers.get("Authorization", ""),
                if_match=self.headers.get("If-Match", ""),
            )
            self.send_response(status)
            if status == 200:
                self.send_header("ETag", f'"{_REVISION}"')
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            _ = self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 — the stdlib handler's own name.
            self._respond()

        def do_DELETE(self) -> None:  # noqa: N802 — the stdlib handler's own name.
            self._respond()

        def log_message(self, *_args: object, **_kwargs: object) -> None:  # pyright: ignore[reportImplicitOverride]
            """Silence the handler's per-request access log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run_delete(*, tmp_path: Path, catalog: _Catalog) -> str:
    """Run the role's real delete shell against one catalog; return its reported status."""
    env_file = tmp_path / "server.env"
    _ = env_file.write_text(f"FABRO_DEV_TOKEN=stale\nFABRO_DEV_TOKEN={_TOKEN}\n", encoding="utf-8")
    server = _serve(catalog=catalog)
    command = _delete_task()["ansible.builtin.shell"]["cmd"]
    assert isinstance(command, str)
    env = {
        "PATH": os.environ["PATH"],
        "FABRO_SERVER_ENV_FILE": str(env_file),
        "FABRO_ENVIRONMENT_URL": (
            f"http://127.0.0.1:{server.server_port}/api/v1/environments/{_ENVIRONMENT}"
        ),
    }
    try:
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
    finally:
        server.shutdown()
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _judged(*, status: str) -> tuple[bool, bool]:
    """Evaluate the task's own changed_when and failed_when against one reported status."""
    task = _delete_task()
    environment = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
    register = {"fabro_server_retired_environment_delete": {"stdout": f"{status}\n"}}
    changed, failed = (
        environment.from_string("{{ " + str(task[key]) + " }}").render(register) == "True"
        for key in ("changed_when", "failed_when")
    )
    return changed, failed


def test_a_held_retired_environment_is_deleted_with_its_current_revision(tmp_path: Path) -> None:
    """The delete reads the revision and sends it as If-Match, so Fabro removes the entry."""
    catalog = _Catalog(holds=True)
    status = _run_delete(tmp_path=tmp_path, catalog=catalog)
    assert status == "204", f"Fabro refused the delete: {status} after {catalog.requests}"
    assert not catalog.holds
    deletes = [request for request in catalog.requests if request[0] == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0][2].strip('"') == _REVISION
    assert all(request[1] == f"Bearer {_TOKEN}" for request in catalog.requests)
    assert _judged(status=status) == (True, False)


def test_an_already_retired_environment_is_an_unchanged_converge(tmp_path: Path) -> None:
    """An id the catalog no longer holds sends no DELETE and reports no change."""
    catalog = _Catalog(holds=False)
    status = _run_delete(tmp_path=tmp_path, catalog=catalog)
    assert status == "404"
    assert [request[0] for request in catalog.requests] == ["GET"]
    assert _judged(status=status) == (False, False)


def test_a_revision_that_moved_before_the_delete_fails_the_task(tmp_path: Path) -> None:
    """A stale If-Match is refused by Fabro and fails the converge, never reads as retired."""
    catalog = _Catalog(holds=True, revision_at_delete="01JX3REVISION0000000000008")
    status = _run_delete(tmp_path=tmp_path, catalog=catalog)
    assert status == "409"
    assert catalog.holds
    assert _judged(status=status) == (False, True)


def test_the_fake_catalog_refuses_a_delete_without_if_match_as_fabro_does() -> None:
    """The precondition these scenarios rely on: a bare DELETE is answered 428."""
    catalog = _Catalog(holds=True)
    server = _serve(catalog=catalog)
    url = f"http://127.0.0.1:{server.server_port}/api/v1/environments/{_ENVIRONMENT}"
    try:
        bare = subprocess.run(
            [
                "curl",
                "--silent",
                "--output",
                "/dev/null",
                "--write-out",
                "%{http_code}",
                "--header",
                f"Authorization: Bearer {_TOKEN}",
                "--request",
                "DELETE",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        server.shutdown()
    assert bare.stdout == "428"
    assert catalog.holds
