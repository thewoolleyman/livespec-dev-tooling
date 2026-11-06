"""The operator's remote kubectl for `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/remote-kubectl.sh` lets a worker host with no kubeconfig drive the production join
and proof: installed as `kubectl` on PATH it runs the API server node's own kubectl over
`tailscale ssh`, and with `--shell` it is the proof's `PORT_FORWARD_SHELL`. These run it against a
stub `tailscale` that hands the received command string to a real shell, as the remote end does,
and assert:

- every argument reaches the remote kubectl intact, including jsonpath quotes, spaces and `$`;
- standard input passes through, for `apply -f -`;
- `--shell` runs its command on the remote host as root, beside that host's kubectl;
- a missing target is refused before any connection.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "remote-kubectl.sh"
_TARGET = "operator@api-node"

# The stub plays `tailscale ssh <target> <command string>`: it logs the target and runs the command
# string through bash, the way the remote login shell would, with `sudo` and `kubectl` stubbed.
_STUB_TAILSCALE = """#!/bin/bash
s="$STUB_STATE"
[ "$1" = ssh ] || exit 9
printf '%s\\n' "$2" >> "$s/targets.log"
shift 2
PATH="$STUB_REMOTE_BIN:$PATH" exec bash -c "$*"
"""

_STUB_SUDO = """#!/bin/bash
[ "$1" = -n ] && shift
printf 'sudo:' >> "$STUB_STATE/remote.log"
exec "$@"
"""

_STUB_KUBECTL = """#!/bin/bash
for a in "$@"; do printf '[%s]' "$a"; done >> "$STUB_STATE/remote.log"
printf '\\n' >> "$STUB_STATE/remote.log"
[ "$1 $2" = "apply -f" ] && cat > "$STUB_STATE/stdin"
exit 0
"""


@dataclass(frozen=True, kw_only=True)
class _Env:
    state: Path
    bin_dir: Path
    remote_bin: Path


def _exe(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    state = tmp_path / "stub"
    state.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    remote_bin = tmp_path / "remote-bin"
    remote_bin.mkdir()
    _exe(path=bin_dir / "tailscale", body=_STUB_TAILSCALE)
    _exe(path=remote_bin / "sudo", body=_STUB_SUDO)
    _exe(
        path=remote_bin / "k3s",
        body='#!/bin/bash\n[ "$1" = kubectl ] && shift\n' 'exec "$STUB_REMOTE_BIN/kubectl" "$@"\n',
    )
    _exe(path=remote_bin / "kubectl", body=_STUB_KUBECTL)
    return _Env(state=state, bin_dir=bin_dir, remote_bin=remote_bin)


def _run(
    *, env: _Env, args: list[str], stdin: str = "", target: str | None = _TARGET
) -> subprocess.CompletedProcess[str]:
    environ = {
        "PATH": f"{env.bin_dir}:/usr/bin:/bin",
        "STUB_STATE": str(env.state),
        "STUB_REMOTE_BIN": str(env.remote_bin),
    }
    if target is not None:
        environ["REMOTE_KUBECTL_TARGET"] = target
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=environ,
        check=False,
        timeout=60,
    )


def _remote(*, env: _Env) -> list[str]:
    return (env.state / "remote.log").read_text(encoding="utf-8").splitlines()


def test_every_argument_reaches_the_remote_kubectl_intact(env: _Env) -> None:
    jsonpath = '{range .status.addresses[?(@.type=="InternalIP")]}{.address}{"\\n"}{end}'
    result = _run(env=env, args=["get", "node", "a b", "-o", f"jsonpath={jsonpath}", "$HOME"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert _remote(env=env) == [f"sudo:[get][node][a b][-o][jsonpath={jsonpath}][$HOME]"]
    assert (env.state / "targets.log").read_text(encoding="utf-8").splitlines() == [_TARGET]


def test_standard_input_passes_through_for_apply(env: _Env) -> None:
    manifest = "kind: ConfigMap\nmetadata:\n  name: x\n"
    result = _run(env=env, args=["apply", "-f", "-"], stdin=manifest)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (env.state / "stdin").read_text(encoding="utf-8") == manifest


def test_shell_mode_runs_its_command_as_root_beside_the_remote_kubectl(env: _Env) -> None:
    result = _run(env=env, args=["--shell", "kubectl get pods 'x y' && echo done-$((1 + 1))"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "done-2" in result.stdout
    assert _remote(env=env) == ["sudo:[get][pods][x y]"]


def test_a_missing_target_is_refused_before_any_connection(env: _Env) -> None:
    result = _run(env=env, args=["get", "nodes"], target=None)
    assert result.returncode != 0
    assert "REMOTE_KUBECTL_TARGET" in result.stderr
    assert not (env.state / "targets.log").exists()
