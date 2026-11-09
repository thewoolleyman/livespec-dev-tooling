"""The principal process keeps the exact schema-1 envelope and fixed installed argv."""

from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_recovery_principal_service as service
from livespec_dev_tooling._incident_observer_store import repository_lock
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError
from tests.livespec_dev_tooling.test_incident_recovery_principal import (
    plan_for,
    publish_request,
)
from tests.livespec_dev_tooling.test_incident_recovery_principal import (
    world as world_fixture,
)

world = world_fixture
_CONFIG = Path("/fixed/controller.json")


@pytest.mark.parametrize(
    "raw",
    [b"{", b"[]", b'{"schema": true}', b"\xff", b'{"a": 1, "a": 2}', b"1e999"],
)
def test_malformed_packets_refuse_before_any_operation(world, raw):
    reply = world.service().execute(raw=raw)
    assert reply["status"] == "refused"
    assert "binding" not in reply
    assert world.forge.calls == []


def test_binding_must_cover_the_exact_payload(world):
    packet = world.packet("lookup", {"intent": asdict(world.intent)})
    packet["binding"] = {"request_sha256": "0" * 64}
    reply = world.service().execute(raw=json.dumps(packet).encode())
    assert reply["reason"] == "exact schema and request binding required"


@pytest.mark.parametrize(
    ("operation", "payload", "reason"),
    [
        ("reserve", {"request": {}}, "unknown recovery principal operation"),
        ("lookup", {"intent": {}, "extra": 1}, "exact principal payload required"),
        ("publish", {"request": {}}, "borrowed observer repository fence required"),
        ("conflict", {"request": {}}, "borrowed observer repository fence required"),
        ("lookup", {"intent": {"action_id": "x"}}, "lookup unavailable: ValueError"),
    ],
)
def test_envelope_and_fence_refusals_keep_the_binding(world, operation, payload, reason):
    reply = world.call(operation, payload, fenced=False)
    assert reply["status"] == "refused"
    assert reply["reason"] == reason
    assert reply["binding"] == world.packet(operation, payload)["binding"]
    assert reply["authorizes_current_effects"] is False


def test_a_damaged_publication_record_fails_closed_with_the_refusal_reply(world, monkeypatch):
    def damaged(_principal, **_):
        raise IncidentJsonRefusalError("incident JSON refused: duplicate key")

    monkeypatch.setattr(service.RecoveryPrincipal, "lookup", damaged)
    reply = world.call("lookup", {"intent": asdict(world.intent)}, fenced=False)
    assert reply["status"] == "refused"
    assert reply["reason"] == "lookup unavailable: IncidentJsonRefusalError"
    assert reply["binding"] == world.packet("lookup", {"intent": asdict(world.intent)})["binding"]


def _main(monkeypatch, world, packet, *, config=_CONFIG):
    output = io.StringIO()

    def load(*, config):
        assert config == expected
        return world.installation

    expected = config
    monkeypatch.setattr(service.ControllerInstallation, "load", load)
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(service.sys, "argv", ["principal", str(config)])
    raw = json.dumps(packet).encode()
    monkeypatch.setattr(service.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
    monkeypatch.setattr(service.sys, "stdout", output)
    assert service.main() == 0
    return json.loads(output.getvalue())


def test_main_requires_an_isolated_protected_installation(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(service.sys, "argv", ["principal", str(_CONFIG)])
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=0))
    monkeypatch.setattr(service.sys, "stdout", output)
    assert service.main() == 2
    assert json.loads(output.getvalue())["status"] == "refused"


def test_main_answers_lookup_without_the_app_and_never_reads_ambient_tokens(world, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ambient-token-is-never-read")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "the-factory-bot-key-is-never-read")
    reply = _main(monkeypatch, world, world.packet("lookup", {"intent": asdict(world.intent)}))
    assert reply["status"] == "absent"
    reply = _main(
        monkeypatch,
        world,
        world.packet("head", {"repository": "owner/repo", "branch": "master"}),
    )
    assert reply["code"] == "recovery-app-credential-absent"


@pytest.mark.parametrize("marker", ["+3", "003", "2", "-1", "not-a-descriptor", "999999"])
def test_main_refuses_a_noncanonical_or_invalid_inherited_fence(world, monkeypatch, marker):
    monkeypatch.setenv(service.REPOSITORY_FENCE_FD_ENV, marker)
    reply = _main(monkeypatch, world, world.packet("lookup", {"intent": asdict(world.intent)}))
    assert reply["status"] == "refused"


def test_main_reads_the_app_credential_beside_the_config_and_borrows_the_fence(
    world, monkeypatch, tmp_path
):
    config = tmp_path / "etc" / "controller.json"
    config.parent.mkdir()
    credential = config.parent / "recovery-app.json"
    pem = "-----BEGIN RSA PRIVATE KEY-----\nQUJD\n-----END RSA PRIVATE KEY-----\n"
    credential.write_text(json.dumps({"app_id": "42", "private_key": pem}))
    credential.chmod(0o600)

    connected = world.connect()
    request = {"request": asdict(publish_request(world, plan_for(world)))}

    def connect(*, repository, credential):
        assert (repository, credential.app_id, credential.private_key) == ("owner/repo", "42", pem)
        return connected

    monkeypatch.setattr(service.RecoveryForge, "connect", connect)
    with repository_lock(
        directory=world.installation.state, repository="owner/repo", existing_only=True
    ):
        fence = service.current_repository_fence(
            repository="owner/repo", directory=world.installation.state
        )
        monkeypatch.setenv(service.REPOSITORY_FENCE_FD_ENV, str(fence.descriptor))
        reply = _main(monkeypatch, world, world.packet("publish", request), config=config)
    assert reply["status"] == "committed"
    assert reply["merge_sha"] == world.forge.master()
