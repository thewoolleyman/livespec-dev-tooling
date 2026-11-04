"""The isolated K3s fixture of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

"Every production cluster network or control-plane change a worker needs MUST ... be proved
against an isolated K3s fixture matching the fleet's version and network configuration before
it is applied to the production fleet." `homelab-worker/fixture/k3s-fixture.sh` builds that
fixture inside a worker VM. These run it under the system `/bin/bash` with stub `hostname`,
`uname`, `k3d`, `docker`, `curl`, `sha256sum` and `install` executables, and assert:

- it runs only inside a `<host>-homelab-worker` VM and only for the two egress modes;
- the server is the fleet's pinned K3s image with the production flags and config keys, and
  only the egress mode varies;
- a rerun keeps an existing fixture, and an egress change restarts only the fixture server.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "fixture" / "k3s-fixture.sh"
_PROD_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "k3s-config"
    / "config.yaml"
)


@dataclass(frozen=True, kw_only=True)
class _Vm:
    root: Path
    bin_dir: Path
    log: Path
    clusters: Path


def _stub(*, vm: _Vm, name: str, body: str) -> None:
    path = vm.bin_dir / name
    path.write_text(
        f'#!/bin/bash\nprintf "{name} %s\\n" "$*" >> "{vm.log}"\n{body}\n', encoding="utf-8"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def vm(tmp_path: Path) -> _Vm:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    made = _Vm(
        root=tmp_path / "state",
        bin_dir=bin_dir,
        log=tmp_path / "calls.log",
        clusters=tmp_path / "clusters",
    )
    made.log.write_text("", encoding="utf-8")
    made.clusters.write_text("", encoding="utf-8")
    _stub(vm=made, name="hostname", body='echo "lima-macbook-m4-max-homelab-worker"')
    _stub(vm=made, name="uname", body='echo "aarch64"')
    _stub(
        vm=made,
        name="k3d",
        body=(
            'case "$1 $2" in\n'
            '  "version "*) echo "k3d version v5.9.0" ;;\n'
            f'  "cluster list") cat "{made.clusters}" ;;\n'
            f'  "cluster create") echo "hw-fixture 1/1 1/1 true" > "{made.clusters}" ;;\n'
            f'  "cluster delete") : > "{made.clusters}" ;;\n'
            '  "kubeconfig get") echo "apiVersion: v1" ;;\n'
            "esac"
        ),
    )
    _stub(vm=made, name="docker", body="exit 0")
    return made


def _run(*, vm: _Vm, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        env={"PATH": f"{vm.bin_dir}:/usr/bin:/bin", "FIXTURE_ROOT": str(vm.root)},
        check=False,
        timeout=60,
    )


def _calls(*, vm: _Vm, command: str) -> list[str]:
    return [
        c for c in vm.log.read_text(encoding="utf-8").splitlines() if c.startswith(f"{command} ")
    ]


def test_the_fixture_refuses_to_run_outside_a_homelab_worker_vm(vm: _Vm) -> None:
    _stub(vm=vm, name="hostname", body='echo "macbook-air"')
    result = _run(vm=vm, args=["up", "agent"])
    assert result.returncode != 0
    assert "not a homelab worker VM" in result.stderr
    assert _calls(vm=vm, command="k3d") == []


def test_an_egress_mode_other_than_agent_or_disabled_is_refused(vm: _Vm) -> None:
    result = _run(vm=vm, args=["up", "cluster"])
    assert result.returncode != 0
    assert "'cluster' is not agent or disabled" in result.stderr
    assert _calls(vm=vm, command="k3d") == []


def test_up_builds_the_fleet_version_with_production_flags_at_the_requested_egress_mode(
    vm: _Vm,
) -> None:
    result = _run(vm=vm, args=["up", "agent"])
    assert result.returncode == 0, result.stdout + result.stderr
    [create] = [c for c in _calls(vm=vm, command="k3d") if c.startswith("k3d cluster create ")]
    assert "--image rancher/k3s:v1.36.2-k3s1@sha256:" in create
    assert "--servers 1 --agents 1" in create
    assert "--disable=traefik@server:0" in create
    assert "--disable=servicelb@server:0" in create
    assert "--api-port 127.0.0.1:6550" in create
    config = (vm.root / "config.yaml").read_text(encoding="utf-8")
    assert 'egress-selector-mode: "agent"' in config
    assert '"max-pods=200"' in config
    assert "- local-storage" in config
    prod = _PROD_CONFIG.read_text(encoding="utf-8")
    assert '"max-pods=200"' in prod
    assert "- local-storage" in prod


def test_a_rerun_keeps_an_existing_fixture(vm: _Vm) -> None:
    assert _run(vm=vm, args=["up", "agent"]).returncode == 0
    result = _run(vm=vm, args=["up", "disabled"])
    assert result.returncode == 0, result.stdout + result.stderr
    creates = [c for c in _calls(vm=vm, command="k3d") if c.startswith("k3d cluster create ")]
    assert len(creates) == 1
    assert 'egress-selector-mode: "agent"' in (vm.root / "config.yaml").read_text(encoding="utf-8")


def test_an_egress_change_rewrites_the_mode_and_restarts_only_the_fixture_server(vm: _Vm) -> None:
    assert _run(vm=vm, args=["up", "agent"]).returncode == 0
    inode = (vm.root / "config.yaml").stat().st_ino
    result = _run(vm=vm, args=["egress", "disabled"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'egress-selector-mode: "disabled"' in (vm.root / "config.yaml").read_text(
        encoding="utf-8"
    )
    assert (vm.root / "config.yaml").stat().st_ino == inode
    restarts = [c for c in _calls(vm=vm, command="docker") if c.startswith("docker restart ")]
    assert restarts == ["docker restart k3d-hw-fixture-server-0"]


def test_down_deletes_the_fixture_and_its_state(vm: _Vm) -> None:
    assert _run(vm=vm, args=["up", "agent"]).returncode == 0
    result = _run(vm=vm, args=["down"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "k3d cluster delete hw-fixture" in _calls(vm=vm, command="k3d")
    assert not vm.root.exists()
