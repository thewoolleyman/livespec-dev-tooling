"""Control admission and callback HTTP share the actual protected observer APIs."""

from __future__ import annotations

# ruff: noqa: SLF001 -- Exercise the composed standard-server request cleanup boundary.
import hashlib
import hmac
import io
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_observer_control as control
from livespec_dev_tooling import incident_observer_service as service
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@pytest.fixture
def controller(tmp_path, monkeypatch):
    settings = ControllerInstallation(
        repository="owner/repo",
        repo=tmp_path / "repo",
        state=tmp_path / "state",
        reader=("/installed/reader",),
        reader_release="v0.282.0",
        principal=("/installed/principal",),
        release="v1.169.0",
        revision="b" * 40,
        jobs=("coverage",),
        webhook_secret=b"webhook" * 8,
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        port=8765,
        config=tmp_path / "controller.json",
    )
    attempt = {
        "repository": "owner/repo",
        "item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": "owner",
        "base": "e" * 40,
        "head": "c" * 40,
        "pr_number": 55,
        "landed_commits": [],
    }
    payload = {
        "repository": "owner/repo",
        "incident_item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": "owner",
        "base_sha": "e" * 40,
        "head_sha": "c" * 40,
        "pr_number": 55,
        "authority_receipt": json.dumps(attempt, sort_keys=True, separators=(",", ":"))
        .encode()
        .hex(),
    }
    calls = []
    reply = {
        "schema": 1,
        "status": "verified",
        "authorizes_current_effects": True,
        "result": {"is_current": True, "attempt": attempt},
    }

    def reader(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(reply), "")

    monkeypatch.setattr(subprocess, "run", reader)
    monkeypatch.setattr(control.MergedRunVerifier, "__call__", lambda *_: True)
    effects = []
    application = service.ControllerService(
        installation=settings,
        recover=lambda intent: effects.append(intent.action_id) or "exact-effect",
    )
    return application, payload, calls, effects, reply


def _request(*, application, path, payload, **changes):
    body = json.dumps(payload).encode()
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_AUTHORIZATION": "Bearer "
        + (
            application.installation.query_secret
            if path in {"/current", "/admitted"}
            else application.installation.control_secret
        ).decode(),
    }
    environ.update(changes)
    responses = []
    data = b"".join(application(environ, lambda status, _: responses.append(status)))
    return responses[0], json.loads(data)


def test_http_arms_and_queries_canonical_current_authority(controller):
    application, payload, calls, _, _ = controller
    status, result = _request(application=application, path="/arm", payload=payload)
    assert status == "202 Accepted" and result["status"] == "armed"
    assert calls[0][:2] == ["/installed/reader", "read-current"]
    query = {
        "repository": "owner/repo",
        "arm_id": result["receipt"],
        "pr_number": 55,
        "base_sha": "e" * 40,
        "head_sha": "c" * 40,
        "receipt_digest": hashlib.sha256(bytes.fromhex(payload["authority_receipt"])).hexdigest(),
    }
    assert (
        _request(application=application, path="/admitted", payload=query)[1]["status"]
        == "admitted"
    )
    query["head_sha"] = "wrong"
    assert _request(application=application, path="/admitted", payload=query)[0] == "403 Forbidden"
    payload["expected_arm_id"] = result["receipt"]
    assert _request(application=application, path="/arm", payload=payload)[1]["status"] == "armed"


@pytest.mark.parametrize(
    "change",
    [
        "auth",
        "repository",
        "malformed",
        "unknown",
        "bad-arm",
        "controller",
        "jobs",
        "bad-expected",
        "canonical-outage",
    ],
)
def test_control_requests_cannot_replace_host_identity_or_reader(controller, change):
    application, payload, _, effects, reply = controller
    options = {"application": application, "path": "/arm", "payload": payload}
    if change == "auth":
        options["HTTP_AUTHORIZATION"] = "Bearer candidate"
    elif change == "repository":
        payload["repository"] = "other/repo"
    elif change == "malformed":
        options["wsgi.input"] = io.BytesIO(b"{")
    elif change == "unknown":
        options["path"] = "/candidate-command"
    elif change == "bad-arm":
        payload.pop("head_sha")
    elif change == "controller":
        payload["controller_release"] = "candidate"
    elif change == "jobs":
        payload["required_jobs"] = []
    elif change == "bad-expected":
        payload["expected_arm_id"] = 1
    else:
        assert change == "canonical-outage"
        reply["status"] = "unavailable"
    assert _request(**options)[0] == "403 Forbidden"
    assert effects == []


def test_bound_callback_executes_once_and_keeps_other_original_jobs_running(controller):
    application, payload, calls, effects, _ = controller
    assert _request(application=application, path="/arm", payload=payload)[1]["status"] == "armed"
    bind = {"repository": "owner/repo", "head_sha": "a" * 40, "run_id": 91}
    assert _request(application=application, path="/bind", payload=bind)[1]["status"] == "admitted"
    assert len(calls) == 1
    event = {
        "action": "completed",
        "repository": {"full_name": "owner/repo"},
        "workflow_job": {
            "id": 12,
            "run_id": 91,
            "head_sha": "a" * 40,
            "head_branch": "master",
            "name": "coverage",
            "status": "completed",
            "conclusion": "failure",
        },
    }
    signature = (
        "sha256="
        + hmac.new(
            application.installation.webhook_secret, json.dumps(event).encode(), hashlib.sha256
        ).hexdigest()
    )
    for _ in range(2):
        status, result = _request(
            application=application,
            path="/callback",
            payload=event,
            HTTP_X_HUB_SIGNATURE_256=signature,
            HTTP_X_GITHUB_EVENT="workflow_job",
            HTTP_X_GITHUB_DELIVERY="delivery-1",
        )
        assert status == "202 Accepted" and result["status"] == "completed"
    assert len(effects) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"repository": "owner/repo", "head_sha": "a" * 40, "run_id": 91},
        {"repository": "owner/repo", "head_sha": "a" * 40, "run_id": True},
        {"repository": "owner/repo", "head_sha": 2, "run_id": 1},
        {"repository": "owner/repo", "head_sha": "a" * 40, "run_id": -1},
    ],
)
def test_no_binding_without_actual_arm_and_exact_run(controller, payload):
    application, _, _, _, _ = controller
    assert _request(application=application, path="/bind", payload=payload)[0] == "403 Forbidden"


def test_startup_requires_installed_inverse_before_any_listener(controller, monkeypatch, tmp_path):
    application, _, _, _, _ = controller
    monkeypatch.setattr(
        service.ControllerInstallation, "load", lambda **_: application.installation
    )
    modules = {
        "livespec_dev_tooling.incident_inverse": SimpleNamespace(
            observer_inverse_callback=lambda **_: application.recover
        ),
        "livespec_dev_tooling.incident_inverse_service": SimpleNamespace(
            ProcessInverseForge=lambda **_: object()
        ),
    }
    monkeypatch.setattr(service.importlib, "import_module", lambda name: modules[name])
    assert service.ControllerService.installed(config=tmp_path) == application
    monkeypatch.setattr(service.importlib, "import_module", lambda _: SimpleNamespace())
    assert service.ControllerService.installed(config=tmp_path) is None
    monkeypatch.setattr(service.ControllerInstallation, "load", lambda **_: None)
    assert service.ControllerService.installed(config=tmp_path) is None


def test_isolated_main_binds_only_loopback_after_protected_installation(controller, monkeypatch):
    application, _, _, _, _ = controller
    monkeypatch.setattr(sys, "argv", ["observer-service", "--config", "/etc/host-config"])
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(service.ControllerService, "installed", lambda **_: application)
    calls = []

    class Server:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def serve_forever(self):
            calls.append("serve")

    def make(host, port, app, **_kwargs):
        calls.append((host, port, app))
        return Server()

    monkeypatch.setattr(service, "make_server", make)
    assert service.main() == 0
    assert calls == [("127.0.0.1", 8765, application), "serve"]


@pytest.mark.parametrize("repository", ["other/repo", "owner/repo"])
def test_callback_scope_and_signature_refuse_before_opening_state(controller, repository):
    application, _, _, effects, _ = controller
    event = {
        "action": "completed",
        "repository": {"full_name": repository},
        "workflow_job": {
            "id": 12,
            "run_id": 91,
            "head_sha": "a" * 40,
            "head_branch": "master",
            "name": "coverage",
            "status": "completed",
            "conclusion": "failure",
        },
    }
    signature = (
        "sha256="
        + hmac.new(
            application.installation.webhook_secret, json.dumps(event).encode(), hashlib.sha256
        ).hexdigest()
    )
    status, _ = _request(
        application=application,
        path="/callback",
        payload=event,
        HTTP_X_HUB_SIGNATURE_256=signature if repository == "other/repo" else "bad",
        HTTP_X_GITHUB_EVENT="workflow_job",
        HTTP_X_GITHUB_DELIVERY="delivery-1",
    )
    assert status == "403 Forbidden"
    assert effects == []
    assert not application.installation.state.exists()


def test_dispatch_uses_public_protocol_and_always_closes_request(monkeypatch):
    calls = []
    request = SimpleNamespace(settimeout=lambda seconds: calls.append(("timeout", seconds)))

    def finish(_request, address):
        calls.append(("finish", address))

    server = SimpleNamespace(
        finish_request=finish, shutdown_request=lambda _: calls.append("closed")
    )
    dispatch = service._RequestDispatcher(server=server)

    class Thread:
        def __init__(self, *, target, kwargs, daemon):
            self.target, self.kwargs = target, kwargs
            assert daemon

        def start(self):
            self.target(**self.kwargs)

    monkeypatch.setattr(service, "Thread", Thread)
    dispatch(request, "client")
    assert calls == [("timeout", 10), ("finish", "client"), "closed"]

    def broken(*_):
        raise OSError("client disconnected")

    server.finish_request = broken
    with pytest.raises(OSError, match="client disconnected"):
        dispatch(request, "client")
    assert calls[-1] == "closed"


@pytest.mark.parametrize("path", ["/current", "/admitted", "/unknown"])
def test_control_adapter_refuses_queries_and_unknown_operations(controller, path):
    application, payload, calls, effects, _ = controller
    result = control.ObserverControl(installation=application.installation).execute(
        path=path, payload=payload
    )
    assert result["status"] == "refused"
    assert calls == []
    assert effects == []
