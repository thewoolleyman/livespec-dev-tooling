"""The factory agent image proof on a homelab worker (livespec-dev-tooling-a3brdf).

`homelab-worker/prove-agent-image.sh <host> <image>` pins one pod running the image to the worker and
checks that it runs natively and carries both ACP adapters and bwrap. These run it under `/bin/bash`
against a stub `kubectl` that answers the Node's architecture and each in-pod check from mocked
values, and assert:

- the proof passes only when the machine matches the node's architecture and every tool is present,
  and fails naming the check that does not hold;
- the proof pod is pinned to the worker by nodeName, tolerates the class taint and the admission
  hold, runs the image given, and its namespace is deleted;
- an undeclared host or a malformed image is refused before any cluster call, and an unreachable
  cluster is named and creates nothing.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

# Integration tier: each test runs the real script under /bin/bash against a stub kubectl.
pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "prove-agent-image.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"
_IMAGE = "registry.invalid/agent:test-arm64"

_STUB = """#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
[ -z "$STUB_UNREACHABLE" ] || { echo 'Connection closed' >&2; exit 255; }
case "$1" in
  get) printf '%s' "$STUB_ARCH" ;;
  apply) cat >> "$s/applied.yaml" ;;
  wait) exit 0 ;;
  delete) exit 0 ;;
  exec)
    cmd="${@: -1}"
    case "$cmd" in
      *"uname -m"*) sh -c "uname() { echo $STUB_MACHINE; }; $cmd" ;;
      *claude-agent-acp*) [ "$STUB_NO" = claude ] && exit 1; echo /usr/local/bin/claude-agent-acp ;;
      *codex-acp*) [ "$STUB_NO" = codex ] && { echo 'No such file or directory' >&2; exit 2; }; echo /opt/livespec/codex-acp ;;
      *bwrap*) [ "$STUB_NO" = bwrap ] && { echo 'bwrap: not found' >&2; exit 127; }; echo 'bubblewrap 0.11.0' ;;
    esac ;;
esac
"""


def _run(
    *,
    tmp_path: Path,
    host: str = _HOST,
    image: str = _IMAGE,
    arch: str = "arm64",
    machine: str = "aarch64",
    missing: str = "",
    unreachable: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "kubectl"
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    hosts = tmp_path / "hosts"
    hosts.mkdir(exist_ok=True)
    (hosts / f"{_HOST}.env").write_text("HOST=alpha\n", encoding="utf-8")
    (state / "calls.log").write_text("", encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), host, image],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(state),
            "STUB_ARCH": arch,
            "STUB_MACHINE": machine,
            "STUB_NO": missing,
            "STUB_UNREACHABLE": "1" if unreachable else "",
            "HOMELAB_WORKER_HOSTS_DIR": str(hosts),
        },
        check=False,
        timeout=60,
    )
    return result, state


def test_a_native_image_with_every_tool_passes(tmp_path: Path) -> None:
    result, _ = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("machine", "claude-agent-acp", "codex-acp", "bwrap"):
        assert f"PROOF {check} PASS" in result.stdout


def test_a_machine_that_does_not_match_the_node_architecture_fails(tmp_path: Path) -> None:
    """An amd64 image under emulation on an arm64 node reports x86_64 and must fail."""
    result, _ = _run(tmp_path=tmp_path, machine="x86_64")
    assert result.returncode != 0
    assert "PROOF machine FAIL" in result.stdout
    assert "FAILED" in result.stderr


@pytest.mark.parametrize(
    ("missing", "check"),
    [("claude", "claude-agent-acp"), ("codex", "codex-acp"), ("bwrap", "bwrap")],
)
def test_a_missing_tool_fails_naming_its_check(tmp_path: Path, missing: str, check: str) -> None:
    result, _ = _run(tmp_path=tmp_path, missing=missing)
    assert result.returncode != 0
    assert f"PROOF {check} FAIL" in result.stdout


def test_the_proof_pod_is_pinned_tolerant_and_cleaned_up(tmp_path: Path) -> None:
    result, state = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    applied = (state / "applied.yaml").read_text(encoding="utf-8")
    assert f"nodeName: {_WORKER}" in applied
    assert f"image: {_IMAGE}" in applied
    assert "key: homelab-worker.livespec.dev/class" in applied
    assert "key: homelab-worker.livespec.dev/admission" in applied
    calls = (state / "calls.log").read_text(encoding="utf-8")
    assert "kubectl delete namespace hw-agent-proof" in calls


def test_an_amd64_node_expects_x86_64(tmp_path: Path) -> None:
    result, _ = _run(tmp_path=tmp_path, arch="amd64", machine="x86_64")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("host", "image"), [("undeclared", _IMAGE), (_HOST, "bad image"), (_HOST, "-x")]
)
def test_bad_arguments_are_refused_before_any_cluster_call(
    tmp_path: Path, host: str, image: str
) -> None:
    result, state = _run(tmp_path=tmp_path, host=host, image=image)
    assert result.returncode != 0
    assert (state / "calls.log").read_text(encoding="utf-8") == ""


def test_an_unreachable_cluster_is_named_and_creates_nothing(tmp_path: Path) -> None:
    result, state = _run(tmp_path=tmp_path, unreachable=True)
    assert result.returncode != 0
    assert "nothing was created" in result.stderr
    assert not (state / "applied.yaml").exists()
