"""Fixture stage two of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/fixture/underlay-fixture.sh` puts each of hw-fixture's K3s node containers on the
tailnet advertising its own /32, as Option A puts the production nodes on it (research 007). These
run it under the system `/bin/bash` against stub `hostname`, `uname`, `curl`, `sha256sum`, `tar`
and `docker` executables, with each node's tailscaled state in files, and assert:

- it runs only inside a homelab worker VM and only with the fixture's nodes running;
- each node gets the pinned Tailscale release and an ephemeral (`--state=mem:`) tailscaled, logs
  in as the untagged `hw-fixture-<node>` and advertises only its own /32 with route acceptance off;
- it prints each login URL and each route to approve, and waits for both;
- a node already on the tailnet with its route approved is kept untouched;
- `down` stops each node's tailscaled.
"""

from __future__ import annotations

import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "fixture" / "underlay-fixture.sh"
_SERVER = "k3d-hw-fixture-server-0"
_AGENT = "k3d-hw-fixture-agent-0"
_IPS = {_SERVER: "172.18.0.2", _AGENT: "172.18.0.3"}


def _status(*, state: str, url: str = "", route: str | None = None) -> str:
    routes = f'["{route}"]' if route else "null"
    return (
        "{\n"
        f'  "BackendState": "{state}",\n'
        f'  "AuthURL": "{url}",\n'
        '  "Self": {\n'
        f'    "PrimaryRoutes": {routes}\n'
        "  }\n"
        "}\n"
    )


_STUB_DOCKER = """#!/bin/bash
s="$STUB_STATE"
printf 'docker %s\\n' "$*" >> "$s/calls.log"
case "$1" in
  inspect)
    case "$3" in
      *State.Running*) cat "$s/running" ;;
      *) case "$4" in *server-0) echo 172.18.0.2 ;; *) echo 172.18.0.3 ;; esac ;;
    esac ;;
  cp) : ;;
  exec)
    shift
    [ "$1" = "--detach" ] && shift
    node="$1"
    shift
    case "$*" in
      "test -S "*) [ -f "$s/$node.sock" ] ;;
      *tailscaled\\ --state=mem:*) touch "$s/$node.sock" ;;
      *kill*) [ -f "$s/$node.sock" ] && rm "$s/$node.sock" ;;
      *" status --json") cat "$s/$node.status" ;;
      *" up "*) if [ -f "$s/$node.after-up" ]; then cp "$s/$node.after-up" "$s/$node.status"; fi ;;
      *) exit 2 ;;
    esac ;;
esac
"""


def _script_var(name: str) -> str:
    """A value the script pins, read from the script rather than restated here."""
    [value] = re.findall(
        rf'^{name}="([^"]+)"$', _SCRIPT.read_text(encoding="utf-8"), flags=re.MULTILINE
    )
    return value


_TS_VERSION = _script_var("ts_version")
_TS_SHA256 = _script_var("ts_sha256_arm64")

_STUB_TAR = f"""#!/bin/bash
dir="$2"
mkdir -p "$dir/tailscale_{_TS_VERSION}_arm64"
touch "$dir/tailscale_{_TS_VERSION}_arm64/tailscale" "$dir/tailscale_{_TS_VERSION}_arm64/tailscaled"
"""


@dataclass(frozen=True, kw_only=True)
class _Vm:
    state: Path
    bin_dir: Path


def _exe(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def vm(tmp_path: Path) -> _Vm:
    state = tmp_path / "stub"
    state.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(path=bin_dir / "docker", body=_STUB_DOCKER)
    _exe(path=bin_dir / "tar", body=_STUB_TAR)
    _exe(path=bin_dir / "hostname", body="#!/bin/bash\necho lima-alpha-homelab-worker\n")
    _exe(path=bin_dir / "uname", body="#!/bin/bash\necho aarch64\n")
    _exe(
        path=bin_dir / "curl",
        body='#!/bin/bash\nprintf "curl %s\\n" "$*" >> "$STUB_STATE/calls.log"\n'
        'while [ "$#" -gt 0 ]; do [ "$1" = -fsSLo ] && { : > "$2"; shift; }; shift; done\n',
    )
    _exe(path=bin_dir / "sha256sum", body='#!/bin/bash\ncat >> "$STUB_STATE/sha.log"\n')
    (state / "calls.log").write_text("", encoding="utf-8")
    (state / "running").write_text("true\n", encoding="utf-8")
    for node in (_SERVER, _AGENT):
        (state / f"{node}.status").write_text(_status(state="NoState"), encoding="utf-8")
    return _Vm(state=state, bin_dir=bin_dir)


def _run(*, vm: _Vm, action: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), action],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{vm.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(vm.state),
            "LOGIN_TIMEOUT": "1",
            "POLL_SECONDS": "1",
        },
        check=False,
        timeout=60,
    )


def _docker(*, vm: _Vm, verb: str) -> list[str]:
    lines = (vm.state / "calls.log").read_text(encoding="utf-8").splitlines()
    return [c for c in lines if c.startswith(f"docker {verb} ")]


def _approved(*, vm: _Vm) -> None:
    for node, ip in _IPS.items():
        (vm.state / f"{node}.after-up").write_text(
            _status(state="Running", route=f"{ip}/32"), encoding="utf-8"
        )


def test_each_node_joins_ephemerally_advertising_only_its_own_slash_32(vm: _Vm) -> None:
    _approved(vm=vm)
    result = _run(vm=vm, action="up")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"tailscale_{_TS_VERSION}_arm64.tgz" in (vm.state / "calls.log").read_text(
        encoding="utf-8"
    )
    assert _TS_SHA256 in (vm.state / "sha.log").read_text(encoding="utf-8")
    execs = _docker(vm=vm, verb="exec")
    for node, ip in _IPS.items():
        name = "hw-fixture-" + node.removeprefix("k3d-hw-fixture-")
        assert any(node in c and "tailscaled --state=mem:" in c for c in execs)
        assert (
            f"docker exec --detach {node} tailscale --socket=/run/tailscale/tailscaled.sock up "
            f"--hostname={name} --advertise-routes={ip}/32 --accept-routes=false"
        ) in execs
        assert f"{node} is on the tailnet as {name} with {ip}/32 approved" in result.stdout
    assert len(_docker(vm=vm, verb="cp")) == 4
    assert "--authkey" not in "".join(execs)
    assert "--advertise-tags" not in "".join(execs)


def test_a_pending_login_and_route_are_printed_and_waited_for(vm: _Vm) -> None:
    (vm.state / f"{_SERVER}.after-up").write_text(
        _status(state="NeedsLogin", url="https://login.tailscale.com/a/fx1"), encoding="utf-8"
    )
    result = _run(vm=vm, action="up")
    assert result.returncode != 0
    assert (
        "approve the tailnet login of hw-fixture-server-0: https://login.tailscale.com/a/fx1"
        in result.stdout
    )
    assert "approve them and run 'underlay-fixture up' again" in result.stderr


def test_a_logged_in_node_waiting_on_its_route_names_the_route_to_approve(vm: _Vm) -> None:
    (vm.state / f"{_SERVER}.after-up").write_text(_status(state="Running"), encoding="utf-8")
    result = _run(vm=vm, action="up")
    assert result.returncode != 0
    assert (
        "approve route 172.18.0.2/32 for device hw-fixture-server-0 in the Tailscale admin console"
        in result.stdout
    )


def test_a_node_already_on_the_tailnet_with_its_route_is_kept(vm: _Vm) -> None:
    for node, ip in _IPS.items():
        (vm.state / f"{node}.status").write_text(
            _status(state="Running", route=f"{ip}/32"), encoding="utf-8"
        )
    result = _run(vm=vm, action="up")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _docker(vm=vm, verb="cp") == []
    assert [c for c in _docker(vm=vm, verb="exec") if " up " in c] == []
    assert "keeping it" in result.stdout


def test_down_stops_each_nodes_tailscaled(vm: _Vm) -> None:
    for node in _IPS:
        (vm.state / f"{node}.sock").write_text("", encoding="utf-8")
    result = _run(vm=vm, action="down")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("its ephemeral device leaves the tailnet") == 2
    assert not list(vm.state.glob("*.sock"))


@pytest.mark.parametrize(
    ("hostname", "running", "message"),
    [
        ("some-other-host", "true", "not a homelab worker VM"),
        ("lima-alpha-homelab-worker", "false", "run k3s-fixture.sh up first"),
    ],
)
def test_it_refuses_outside_a_worker_vm_or_without_the_fixture(
    vm: _Vm, hostname: str, running: str, message: str
) -> None:
    _exe(path=vm.bin_dir / "hostname", body=f"#!/bin/bash\necho {hostname}\n")
    (vm.state / "running").write_text(f"{running}\n", encoding="utf-8")
    result = _run(vm=vm, action="up")
    assert result.returncode != 0
    assert message in result.stderr
    assert _docker(vm=vm, verb="exec") == []


def test_every_pending_login_url_is_shown_in_the_same_pass(vm: _Vm) -> None:
    for node, code in ((_SERVER, "srv"), (_AGENT, "agt")):
        (vm.state / f"{node}.after-up").write_text(
            _status(state="NeedsLogin", url=f"https://login.tailscale.com/a/{code}"),
            encoding="utf-8",
        )
    result = _run(vm=vm, action="up")
    assert result.returncode != 0
    assert "hw-fixture-server-0: https://login.tailscale.com/a/srv" in result.stdout
    assert "hw-fixture-agent-0: https://login.tailscale.com/a/agt" in result.stdout
