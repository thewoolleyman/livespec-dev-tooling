"""The CI installer proof on a homelab worker (plan homelab-k8s-worker-nodes, livespec-dev-tooling-ko26ez).

`homelab-worker/prove-ci-installer.sh <host> <image> <installer>` pins one pod running a repository's
CI image to the worker, streams the installer into it, runs it, and runs the installed binary's
`--version`. These run it under `/bin/bash` against a stub `kubectl` that answers the Node's
architecture, the pod's image id and each in-pod step from mocked values, and assert:

- the proof passes only when the machine matches the node's architecture, the installer exits 0
  and the installed binary runs, and fails naming the check that does not hold;
- the installer's own bytes reach the pod, and its sha256 and the pod's image id are reported;
- the proof pod is pinned to the worker by nodeName, tolerates the class taint and the admission
  hold, runs the image given, and its namespace is deleted;
- an undeclared host, a malformed image or a missing installer is refused before any cluster call,
  and an unreachable cluster is named and creates nothing.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import hashlib
import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

# Integration tier: each test runs the real script under /bin/bash against a stub kubectl.
pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "prove-ci-installer.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"
_IMAGE = "registry.invalid/ci:test-arm64"
_IMAGE_ID = "registry.invalid/ci@sha256:" + "a" * 64
_INSTALLER_BODY = "#!/usr/bin/env bash\necho stub installer\n"

_STUB = """#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
[ -z "$STUB_UNREACHABLE" ] || { echo 'Connection closed' >&2; exit 255; }
case "$1" in
  get)
    case "$2" in
      node) printf '%s' "$STUB_ARCH" ;;
      pod) printf '%s' "$STUB_IMAGE_ID" ;;
    esac ;;
  apply) cat >> "$s/applied.yaml" ;;
  wait) exit 0 ;;
  delete) exit 0 ;;
  exec)
    cmd="${@: -1}"
    case "$cmd" in
      *"uname -m"*) sh -c "uname() { echo $STUB_MACHINE; }; $cmd" ;;
      *proved-installer*)
        cat > "$s/installer-received"
        [ "$STUB_FAIL" = installer ] && { echo 'sha256 mismatch' >&2; exit 1; }
        echo 'tool 1.0.0' ;;
      --version)
        [ "$STUB_FAIL" = tool ] && { echo 'exec format error' >&2; exit 126; }
        echo 'tool 1.0.0' ;;
    esac ;;
esac
"""


def _run(
    *,
    tmp_path: Path,
    host: str = _HOST,
    image: str = _IMAGE,
    installer: str | None = None,
    arch: str = "arm64",
    machine: str = "aarch64",
    fail: str = "",
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
    installer_file = tmp_path / "install-tool.sh"
    installer_file.write_text(_INSTALLER_BODY, encoding="utf-8")
    (state / "calls.log").write_text("", encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), host, image, installer or str(installer_file)],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(state),
            "STUB_ARCH": arch,
            "STUB_MACHINE": machine,
            "STUB_IMAGE_ID": _IMAGE_ID,
            "STUB_FAIL": fail,
            "STUB_UNREACHABLE": "1" if unreachable else "",
            "HOMELAB_WORKER_HOSTS_DIR": str(hosts),
        },
        check=False,
        timeout=60,
    )
    return result, state


def test_a_native_install_whose_tool_runs_passes(tmp_path: Path) -> None:
    result, _ = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    for check in ("machine", "installer-runs", "tool-runs"):
        assert f"PROOF {check} PASS" in result.stdout


def test_the_installer_bytes_reach_the_pod_and_are_identified(tmp_path: Path) -> None:
    result, state = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (state / "installer-received").read_text(encoding="utf-8") == _INSTALLER_BODY
    digest = hashlib.sha256(_INSTALLER_BODY.encode("utf-8")).hexdigest()
    assert f"PROOF-INFO installer-sha256 {digest}" in result.stdout
    assert f"PROOF-INFO image-id {_IMAGE_ID}" in result.stdout


def test_a_machine_that_does_not_match_the_node_architecture_fails(tmp_path: Path) -> None:
    """An amd64 image under emulation on an arm64 node reports x86_64 and must fail."""
    result, _ = _run(tmp_path=tmp_path, machine="x86_64")
    assert result.returncode != 0
    assert "PROOF machine FAIL" in result.stdout
    assert "FAILED" in result.stderr


def test_a_failing_installer_fails_and_skips_the_tool(tmp_path: Path) -> None:
    result, _ = _run(tmp_path=tmp_path, fail="installer")
    assert result.returncode != 0
    assert "PROOF installer-runs FAIL" in result.stdout
    assert "PROOF tool-runs FAIL not run" in result.stdout


def test_a_tool_that_does_not_run_fails(tmp_path: Path) -> None:
    result, _ = _run(tmp_path=tmp_path, fail="tool")
    assert result.returncode != 0
    assert "PROOF installer-runs PASS" in result.stdout
    assert "PROOF tool-runs FAIL" in result.stdout


def test_the_proof_pod_is_pinned_tolerant_and_cleaned_up(tmp_path: Path) -> None:
    result, state = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    applied = (state / "applied.yaml").read_text(encoding="utf-8")
    assert f"nodeName: {_WORKER}" in applied
    assert f"image: {_IMAGE}" in applied
    assert "key: homelab-worker.livespec.dev/class" in applied
    assert "key: homelab-worker.livespec.dev/admission" in applied
    calls = (state / "calls.log").read_text(encoding="utf-8")
    assert "kubectl delete namespace hw-ci-installer-proof" in calls


def test_an_amd64_node_expects_x86_64(tmp_path: Path) -> None:
    result, _ = _run(tmp_path=tmp_path, arch="amd64", machine="x86_64")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("host", "image", "installer"),
    [
        ("undeclared", _IMAGE, None),
        (_HOST, "bad image", None),
        (_HOST, "-x", None),
        (_HOST, _IMAGE, "/nonexistent/install-tool.sh"),
    ],
)
def test_bad_arguments_are_refused_before_any_cluster_call(
    tmp_path: Path, host: str, image: str, installer: str | None
) -> None:
    result, state = _run(tmp_path=tmp_path, host=host, image=image, installer=installer)
    assert result.returncode != 0
    assert (state / "calls.log").read_text(encoding="utf-8") == ""


def test_an_unreachable_cluster_is_named_and_creates_nothing(tmp_path: Path) -> None:
    result, state = _run(tmp_path=tmp_path, unreachable=True)
    assert result.returncode != 0
    assert "nothing was created" in result.stderr
    assert not (state / "applied.yaml").exists()
