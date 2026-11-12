"""The Fabro settings endpoint is a read-only part of a drift report.

The rendered ``settings.toml`` is only an input to Fabro: defaults and other
runtime resolution mean it cannot prove what the running instance uses.  This
test runs the role's endpoint comparison against a local server so the report
is held to the resolved values, rather than to the file it would render.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import threading
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path
from socketserver import StreamRequestHandler, ThreadingTCPServer

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_TASKS = _REPO_ROOT / "ansible" / "roles" / "fabro_server" / "tasks" / "main.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_TIMEOUT_SECONDS = 600
_DEV_TOKEN = "fixture-dev-token"
_LIFTED = (
    "Resolve this instance's settings endpoint declarations",
    "Read the running instance's resolved settings",
    "Report settings endpoint drift for this instance",
    "Report an unreachable settings endpoint for this instance",
)


class _SettingsServer(ThreadingTCPServer):
    """A settings endpoint whose request method and replies the test can inspect."""

    def __init__(self, *, settings: object, status: int = 200) -> None:
        super().__init__(("127.0.0.1", 0), _handler())
        self.settings = settings
        self.status = status
        self.requests: list[str] = []
        self.authorizations: list[str | None] = []


def _handler() -> type[StreamRequestHandler]:
    class Handler(StreamRequestHandler):
        def handle(self) -> None:
            server = self.server
            assert isinstance(server, _SettingsServer)
            request = self.rfile.readline().decode().split()
            server.requests.append(request[0])
            authorization = None
            while (line := self.rfile.readline().decode().strip()) != "":
                name, _, value = line.partition(":")
                if name.lower() == "authorization":
                    authorization = value.strip()
            server.authorizations.append(authorization)
            status = server.status
            settings = server.settings
            if authorization != f"Bearer {_DEV_TOKEN}":
                status, settings = 401, {}
            payload = json.dumps(settings).encode()
            response = (
                f"HTTP/1.1 {status} fixture\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode()
            self.wfile.write(response + payload)

    return Handler


@pytest.fixture
def settings_server() -> Iterator[_SettingsServer]:
    """Serve one mutable Fabro settings response for an Ansible role fragment."""
    server = _SettingsServer(settings={})
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _ansible_core_pin() -> str:
    """The exact Ansible version that the drift recipe invokes."""
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None
    return pin[0]


def _role_tasks() -> dict[str, str]:
    """The role's column-zero tasks, keyed by their observable names."""
    text = _TASKS.read_text(encoding="utf-8")
    starts = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    return {
        body.splitlines()[0].removeprefix("- name: ").strip(): body
        for start, end in pairwise([*starts, len(text)])
        if (body := text[start:end])
    }


def _lifted_tasks() -> str:
    """The endpoint comparison, verbatim, without the role's host side effects."""
    tasks = _role_tasks()
    missing = [name for name in _LIFTED if name not in tasks]
    assert not missing, f"the fabro_server role must carry {missing}"
    return "".join(tasks[name] for name in _LIFTED).replace("  become: true\n", "")


def _run(*, tmp_path: Path, port: int, service_state: str | None = None) -> tuple[int, str]:
    """Run the committed comparison against the local endpoint and return its report."""
    storage = tmp_path / "home" / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    _ = (storage / "server.env").write_text(
        f"OTHER=1\nFABRO_DEV_TOKEN={_DEV_TOKEN}\n", encoding="utf-8"
    )
    vars = {
        "fabro_server_home_dir": str(tmp_path / "home"),
        "fabro_server_unit_name": "fabro-server-fixture",
        "fabro_server_port": port,
        "fabro_server_canonical_host": f"fixture.invalid:{port}",
        "fabro_server_github_app_id": "12345",
        "fabro_server_max_concurrent_runs": 7,
    }
    if service_state is not None:
        vars["fabro_server_service_state"] = service_state
    playbook = tmp_path / "settings-drift.yml"
    header = "\n".join(
        (
            "- hosts: localhost",
            "  connection: local",
            "  gather_facts: false",
            f"  vars: {json.dumps(vars)}",
            "  tasks:",
        )
    )
    body = "".join(f"    {line}\n" if line else "\n" for line in _lifted_tasks().splitlines())
    _ = playbook.write_text(f"{header}\n{body}", encoding="utf-8")
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            "localhost,",
            "--check",
            str(playbook),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _resolved(*, port: int, runs: int = 7, app_id: str = "12345") -> dict[str, object]:
    """The endpoint values declared by the fixture instance's host_vars axes."""
    host = f"fixture.invalid:{port}"
    return {
        "server": {
            "api": {"url": f"https://{host}/api/v1"},
            "integrations": {"github": {"app_id": app_id}},
            "listen": {"address": f"127.0.0.1:{port}"},
            "scheduler": {"max_concurrent_runs": runs},
            "web": {"url": f"https://{host}"},
        }
    }


def test_a_declared_resolved_setting_difference_is_named_as_drift(
    *, tmp_path: Path, settings_server: _SettingsServer
) -> None:
    """A mismatch names the instance, key, declaration and resolved endpoint value."""
    port = settings_server.server_address[1]
    settings_server.settings = _resolved(port=port, runs=3)

    code, output = _run(tmp_path=tmp_path, port=port)

    assert code == 0, output
    assert "DRIFT: fabro-server-fixture" in output
    assert "server.scheduler.max_concurrent_runs" in output
    assert "declared 7" in output
    assert "resolved 3" in output
    assert settings_server.requests == ["GET"], settings_server.requests


def test_an_endpoint_setting_that_host_vars_does_not_declare_is_not_drift(
    *, tmp_path: Path, settings_server: _SettingsServer
) -> None:
    """Server defaults outside the mapping must not make a clean host look drifted."""
    port = settings_server.server_address[1]
    resolved = _resolved(port=port)
    server = resolved["server"]
    assert isinstance(server, dict)
    server["unmanaged_default"] = {"value": "the server chose this"}
    settings_server.settings = resolved

    code, output = _run(tmp_path=tmp_path, port=port)

    assert code == 0, output
    assert "DRIFT:" not in output
    assert "unmanaged_default" not in output
    assert settings_server.requests == ["GET"], settings_server.requests


def test_an_unreachable_settings_endpoint_is_named_unreachable_not_matching(
    *, tmp_path: Path, settings_server: _SettingsServer
) -> None:
    """A failed read has an explicit result and never becomes a false clean comparison."""
    port = settings_server.server_address[1]
    settings_server.status = 503

    code, output = _run(tmp_path=tmp_path, port=port)

    assert code == 0, output
    assert "fabro-server-fixture" in output
    assert "settings endpoint is unreachable" in output
    assert "DRIFT:" not in output
    assert settings_server.requests == ["GET"], settings_server.requests


def test_a_parked_instance_with_no_listener_is_named_unreachable_not_skipped(
    *, tmp_path: Path
) -> None:
    """A stopped instance still gets a result: its closed endpoint is unreachable."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    code, output = _run(tmp_path=tmp_path, port=port, service_state="stopped")

    assert code == 0, output
    assert "fabro-server-fixture" in output
    assert "settings endpoint is unreachable" in output
    assert "DRIFT:" not in output


def test_the_settings_read_authenticates_with_the_instances_dev_token(
    *, tmp_path: Path, settings_server: _SettingsServer
) -> None:
    """A token-protected server is compared, not misreported as unreachable."""
    port = settings_server.server_address[1]
    settings_server.settings = _resolved(port=port, runs=3)

    code, output = _run(tmp_path=tmp_path, port=port)

    assert code == 0, output
    assert settings_server.authorizations == [f"Bearer {_DEV_TOKEN}"]
    assert "settings endpoint is unreachable" not in output
    assert "resolved 3" in output
    assert _DEV_TOKEN not in output


def test_a_settings_envelope_response_is_compared_like_a_root_response(
    *, tmp_path: Path, settings_server: _SettingsServer
) -> None:
    """The top-level settings envelope yields real drift and no false drift."""
    port = settings_server.server_address[1]
    settings_server.settings = {"settings": _resolved(port=port, runs=3)}

    code, output = _run(tmp_path=tmp_path, port=port)

    assert code == 0, output
    assert output.count("DRIFT:") == 1, output
    assert "server.scheduler.max_concurrent_runs" in output
    assert "declared 7" in output
    assert "resolved 3" in output

    settings_server.settings = {"settings": _resolved(port=port)}

    code, output = _run(tmp_path=tmp_path, port=port)

    assert code == 0, output
    assert "DRIFT:" not in output
    assert "settings endpoint is unreachable" not in output
