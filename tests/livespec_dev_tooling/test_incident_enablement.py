"""The enablement record the independent controller holds, its fence and its query.

Spec v205, `## Expedited incident execution`: the record is written only through the
controller's control-credentialed route, after the controller's own two reads of
livespec core's default branch confirm the identity it names; an exact retry answers the
retained record without writing again; the query route answers the reading, the
confirmed identity and the arming state under the bounded freshness rule; and the
arming write is refused while no record binds the current identity.
"""

from __future__ import annotations

import io
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling._incident_fleet_sources import core_head_reader, core_identity_reader
from livespec_dev_tooling.fleet._local_context import CommandResult, InvocationNotPerformed
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_enablement import (
    FRESHNESS_SECONDS,
    INSTALLATION_PORTS,
    IdentitySource,
    ObserverEnablement,
    _post,
    controller_enablement_writer,
    production_identity_source,
)
from livespec_dev_tooling.incident_observer_service import ControllerService

REPO = "example/tooling"
ROOT = Path(__file__).resolve().parents[2]
CURRENT = "a" * 64
MOVED = "b" * 64
HEAD = "1" * 40
NEW_HEAD = "2" * 40


def _installation(*, tmp_path: Path) -> ControllerInstallation:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    return ControllerInstallation(
        repository=REPO,
        repo=tmp_path,
        state=state,
        reader=(sys.executable,),
        reader_release="v0.284.0",
        principal=(sys.executable,),
        release="v1.0.0",
        revision="c" * 40,
        jobs=("ci-green",),
        webhook_secret=b"webhook",
        control_secret=b"control",
        query_secret=b"query",
        port=8765,
        config=tmp_path / "controller.json",
    )


class Core:
    """A fake livespec core: its head and manifest identity, counting each read."""

    def __init__(self) -> None:
        self.head: str | None = HEAD
        self.identity: str | None = CURRENT
        self.identity_reads = 0

    def source(self) -> IdentitySource:
        def read_identity() -> str | None:
            self.identity_reads += 1
            return self.identity

        return IdentitySource(read_head=lambda: self.head, read_identity=read_identity)


class Clock:
    def __init__(self) -> None:
        self.at = 1_000_000.0

    def __call__(self) -> float:
        return self.at


def _controller(*, tmp_path: Path, core: Core, clock: Clock | None = None) -> ObserverEnablement:
    return ObserverEnablement(
        installation=_installation(tmp_path=tmp_path),
        source=core.source(),
        now=clock or Clock(),
    )


def _enable(controller: ObserverEnablement, *, identity: str = CURRENT, op: str = "op-1") -> Any:
    return controller.execute(
        path="/enablement",
        payload={"repository": REPO, "manifest_sha256": identity, "operation_id": op},
    )


def _read(controller: ObserverEnablement) -> dict[str, Any]:
    return controller.execute(path="/enablement/read", payload={"repository": REPO})


def _fence(controller: ObserverEnablement, *, path: str, op: str) -> dict[str, Any]:
    return controller.execute(path=path, payload={"repository": REPO, "operation_id": op})


def test_the_step_records_enablement_bound_to_the_identity_the_controller_confirms_twice(
    tmp_path: Path,
) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    answer = _enable(controller)
    assert answer["status"] == "enabled"
    assert answer["record"] == {
        "repository": REPO,
        "manifest_sha256": CURRENT,
        "operation_id": "op-1",
        "controller_release": "v1.0.0",
        "controller_revision": "c" * 40,
    }
    assert core.identity_reads == 2
    reading = _read(controller)
    assert reading["status"] == "enabled"
    assert reading["confirmed_manifest_sha256"] == CURRENT
    assert reading["armed"] is False
    assert reading["query"] == {"repository": REPO}


def test_an_exact_retry_answers_the_retained_record_without_writing_again(
    tmp_path: Path,
) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    first = _enable(controller)
    reads = core.identity_reads
    assert _enable(controller) == first
    assert core.identity_reads == reads


def test_an_operation_identity_reused_with_different_bytes_is_refused(tmp_path: Path) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    _ = _enable(controller)
    core.identity = MOVED
    refused = _enable(controller, identity=MOVED)
    assert refused["status"] == "refused"
    assert "different bytes" in refused["reason"]


def test_an_identity_the_controllers_own_reads_do_not_confirm_retains_nothing(
    tmp_path: Path,
) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    refused = _enable(controller, identity=MOVED)
    assert refused["status"] == "refused"
    assert "unconfirmed" in refused["reason"]
    assert _read(controller)["status"] == "absent"
    core.identity = None
    assert _enable(controller, op="op-2")["status"] == "refused"
    assert _read(controller)["status"] == "absent"


def test_a_record_bound_to_another_identity_reads_stale_and_a_revocation_reads_revoked(
    tmp_path: Path,
) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    _ = _enable(controller)
    core.head, core.identity = NEW_HEAD, MOVED
    assert _read(controller)["status"] == "stale"
    core.head, core.identity = HEAD, CURRENT
    _ = _enable(controller, op="op-3")
    assert _fence(controller, path="/enablement/revoke", op="op-4")["status"] == "revoked"
    assert _read(controller)["status"] == "revoked"
    assert _enable(controller, op="op-5")["status"] == "enabled"
    assert _read(controller)["status"] == "enabled"


def test_arming_is_refused_until_a_record_binds_the_current_identity(tmp_path: Path) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    refused = _fence(controller, path="/fence/arm", op="arm-1")
    assert refused["status"] == "refused"
    assert "stays disarmed" in refused["reason"]
    assert _read(controller)["armed"] is False
    _ = _enable(controller)
    assert _fence(controller, path="/fence/arm", op="arm-2")["status"] == "armed"
    assert _fence(controller, path="/fence/arm", op="arm-2")["status"] == "armed"
    assert _read(controller)["armed"] is True
    assert _fence(controller, path="/fence/disarm", op="disarm-1")["status"] == "disarmed"
    assert _read(controller)["armed"] is False


def test_the_fence_stays_armed_when_the_identity_moves_and_cannot_be_rearmed_on_a_stale_record(
    tmp_path: Path,
) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    _ = _enable(controller)
    _ = _fence(controller, path="/fence/arm", op="arm-1")
    core.head, core.identity = NEW_HEAD, MOVED
    reading = _read(controller)
    assert (reading["status"], reading["armed"]) == ("stale", True)
    assert _fence(controller, path="/fence/arm", op="arm-2")["status"] == "refused"


def test_the_identity_is_re_read_only_when_core_moves_and_holds_six_hours_without_a_head(
    tmp_path: Path,
) -> None:
    core = Core()
    clock = Clock()
    controller = _controller(tmp_path=tmp_path, core=core, clock=clock)
    _ = _read(controller)
    reads = core.identity_reads
    assert _read(controller)["confirmed_manifest_sha256"] == CURRENT
    assert core.identity_reads == reads
    core.head = None
    clock.at += FRESHNESS_SECONDS
    assert _read(controller)["confirmed_manifest_sha256"] == CURRENT
    clock.at += 1
    reading = _read(controller)
    assert (reading["status"], reading["confirmed_manifest_sha256"]) == ("unavailable", None)
    core.head = NEW_HEAD
    _ = _read(controller)
    assert core.identity_reads == reads + 1


def test_a_retry_that_lands_between_the_confirming_reads_answers_the_retained_record(
    tmp_path: Path,
) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    inner: list[Any] = []

    def read_identity() -> str | None:
        core.identity_reads += 1
        if core.identity_reads == 1:
            inner.append(
                ObserverEnablement(
                    installation=controller.installation, source=Core().source(), now=Clock()
                ).execute(
                    path="/enablement",
                    payload={
                        "repository": REPO,
                        "manifest_sha256": CURRENT,
                        "operation_id": "op-1",
                    },
                )
            )
        return CURRENT

    racing = ObserverEnablement(
        installation=controller.installation,
        source=IdentitySource(read_head=lambda: HEAD, read_identity=read_identity),
        now=Clock(),
    )
    assert _enable(racing) == inner[0]
    assert inner[0]["status"] == "enabled"


def test_a_moved_head_whose_manifest_cannot_be_read_is_unavailable(tmp_path: Path) -> None:
    core = Core()
    controller = _controller(tmp_path=tmp_path, core=core)
    _ = _enable(controller)
    core.head, core.identity = NEW_HEAD, None
    reading = _read(controller)
    assert (reading["status"], reading["confirmed_manifest_sha256"]) == ("unavailable", None)


def test_malformed_and_unknown_operations_are_refused(tmp_path: Path) -> None:
    controller = _controller(tmp_path=tmp_path, core=Core())
    for path, payload in (
        ("/enablement", {"repository": REPO}),
        ("/enablement", {"repository": REPO, "manifest_sha256": 1, "operation_id": "x"}),
        ("/enablement", {"repository": REPO, "manifest_sha256": CURRENT, "operation_id": ""}),
        ("/fence/arm", {"repository": REPO, "operation_id": ""}),
        ("/enablement/read", {"repository": REPO, "extra": 1}),
        ("/no-such-route", {"repository": REPO}),
    ):
        assert controller.execute(path=path, payload=payload)["status"] == "refused"


def _call(service: ControllerService, *, path: str, secret: bytes, payload: object) -> Any:
    body = json.dumps(payload).encode()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": path,
        "HTTP_AUTHORIZATION": "Bearer " + secret.decode(),
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    statuses: list[str] = []
    reply = service(environ, lambda status, _headers: statuses.append(status))
    return statuses[0], json.loads(b"".join(reply))


def test_the_service_routes_the_write_on_the_control_secret_and_the_read_on_the_query_secret(
    tmp_path: Path,
) -> None:
    core = Core()
    service = ControllerService(
        installation=_installation(tmp_path=tmp_path),
        recover=lambda _intent: None,
        identity_source=core.source(),
    )
    write = {"repository": REPO, "manifest_sha256": CURRENT, "operation_id": "op-1"}
    status, answer = _call(service, path="/enablement", secret=b"control", payload=write)
    assert (status, answer["status"]) == ("202 Accepted", "enabled")
    status, answer = _call(
        service, path="/enablement/read", secret=b"query", payload={"repository": REPO}
    )
    assert (status, answer["status"]) == ("202 Accepted", "enabled")
    refused = (
        ("/enablement", b"query", write),
        ("/enablement", b"control", {**write, "repository": "example/other"}),
        ("/fence/arm", b"control", {"repository": REPO, "operation_id": ""}),
    )
    for path, secret, payload in refused:
        assert _call(service, path=path, secret=secret, payload=payload)[0] == "403 Forbidden"


def _run(*, ls_remote: str = f"{HEAD}\tHEAD\n", failed: bool = False):
    calls: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> Any:
        _ = cwd
        calls.append(args)
        if failed:
            return IOFailure(
                InvocationNotPerformed(argv=tuple(args), kind="not-found", detail="no git")
            )
        if "ls-remote" in args:
            return IOSuccess(CommandResult(returncode=0, stdout=ls_remote, stderr=""))
        if "show" in args:
            return IOSuccess(CommandResult(returncode=0, stdout="{}\n", stderr=""))
        return IOSuccess(CommandResult(returncode=0, stdout="", stderr=""))

    return run, calls


def test_core_is_read_by_ls_remote_head_and_by_the_manifest_digest_the_audit_computes() -> None:
    run, calls = _run()
    assert core_head_reader(owner="thewoolleyman", run=run)() == HEAD
    assert core_identity_reader(owner="thewoolleyman", run=run)() == (
        "ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356"
    )
    assert any("github.com/thewoolleyman/livespec.git" in part for a in calls for part in a)
    assert "credential.helper=" in calls[0]


@pytest.mark.parametrize(("ls_remote", "failed"), [("", False), ("nonsense\n", False), ("", True)])
def test_an_unusable_core_answer_reads_as_unavailable(*, ls_remote: str, failed: bool) -> None:
    run, _ = _run(ls_remote=ls_remote, failed=failed)
    assert core_head_reader(owner="thewoolleyman", run=run)() is None
    if failed:
        assert core_identity_reader(owner="thewoolleyman", run=run)() is None


def test_the_production_source_is_built_without_reading_anything() -> None:
    source = production_identity_source()
    assert callable(source.read_head)
    assert callable(source.read_identity)


def test_the_step_writes_only_to_the_installation_serving_the_repository() -> None:
    posted: list[tuple[str, bytes, dict[str, Any]]] = []

    def post(*, url: str, secret: bytes, body: bytes) -> tuple[int, dict[str, Any]]:
        posted.append((url, secret, json.loads(body)))
        return 202, {"status": "enabled"}

    write = controller_enablement_writer(
        environ={"LIVESPEC_INCIDENT_CONTROL_SECRET": "control"}, post=post
    )
    assert write(repository="thewoolleyman/livespec-dev-tooling", manifest_sha256=CURRENT) == (
        0,
        "enabled\tthewoolleyman/livespec-dev-tooling",
    )
    url, secret, body = posted[0]
    assert (url, secret) == ("http://127.0.0.1:8765/enablement", b"control")
    assert body["manifest_sha256"] == CURRENT
    assert re.fullmatch(r"incident-enable-[0-9a-f]{32}", body["operation_id"])
    assert write(repository="example/unserved", manifest_sha256=CURRENT) == (
        1,
        "refused\texample/unserved: no controller installation serves it",
    )


def test_the_step_refuses_by_name_without_a_secret_a_reachable_controller_or_its_consent() -> None:
    repo = "thewoolleyman/livespec-dev-tooling"

    def unreachable(**_kwargs: object) -> tuple[int, dict[str, Any]]:
        raise OSError("connection refused")

    assert controller_enablement_writer(environ={}, post=unreachable)(
        repository=repo, manifest_sha256=CURRENT
    )[1] == (f"refused\t{repo}: LIVESPEC_INCIDENT_CONTROL_SECRET is not projected")
    secret = {"LIVESPEC_INCIDENT_CONTROL_SECRET": "control"}
    line = controller_enablement_writer(environ=secret, post=unreachable)(
        repository=repo, manifest_sha256=CURRENT
    )[1]
    assert line == f"refused\t{repo}: controller unreachable: connection refused"

    def refusing(**_kwargs: object) -> tuple[int, dict[str, Any]]:
        return 403, {"status": "refused", "reason": "not confirmed"}

    refused = controller_enablement_writer(environ=secret, post=refusing)(
        repository=repo, manifest_sha256=CURRENT
    )
    assert refused == (1, f"refused\t{repo}: controller refused: not confirmed")


def test_the_post_carries_the_control_secret_and_reads_an_accepted_or_refused_answer() -> None:
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server's method name
            seen.append(self.headers["Authorization"])
            _ = self.rfile.read(int(self.headers["Content-Length"]))
            refused = self.path == "/refuse"
            self.send_response(403 if refused else 202)
            self.end_headers()
            _ = self.wfile.write(json.dumps({"status": "refused" if refused else "ok"}).encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        assert _post(url=base + "/enablement", secret=b"s3", body=b"{}") == (202, {"status": "ok"})
        assert _post(url=base + "/refuse", secret=b"s3", body=b"{}") == (403, {"status": "refused"})
    finally:
        server.shutdown()
    assert seen == ["Bearer s3", "Bearer s3"]


def test_the_served_ports_are_the_incident_observer_roles_listener_ports() -> None:
    defaults = (ROOT / "ansible/roles/incident_observer/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    port = re.search(r"^incident_observer_port: (\d+)$", defaults, re.MULTILINE)
    assert port is not None
    assert {"thewoolleyman/livespec-dev-tooling": int(port.group(1))} == INSTALLATION_PORTS
