"""Phase E placement of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

Each homelab worker gets a host-unique ARC runner scale set (`ci-runner/k3s/arc/values-*-homelab-worker.yaml`,
research/009), addressed by name so no existing CI traffic moves. These parse every such values
file and assert rules that hold for any host:

- the set is named `<host>-homelab-worker-k3s` for a host the homelab-worker host list declares,
  and idles at zero runners;
- its runner pods select that host's worker and arm64, and tolerate the permanent class taint but
  not the admission hold, so lifting the hold stays the operator's explicit gate;
- its listener runs on the fleet's amd64 nodes, never on a worker;
- the runner image is pinned by digest;
- jobs run in the fleet's container mode (compared against the fleet's reference set), asking
  for none of the fleet CI nodes' capacity, with the hook template revision rendered on install.

No assertion restates a production value.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_ARC = _ROOT / "ci-runner" / "k3s" / "arc"
_HOSTS = {p.stem for p in (_ROOT / "homelab-worker" / "hosts").glob("*.env")}
_CLASS_TAINT = "homelab-worker.livespec.dev/class"
_HOLD_TAINT = "homelab-worker.livespec.dev/admission"
_HOST_LABEL = "homelab-worker.livespec.dev/host"
_VALUES = sorted(_ARC.glob("values-*-homelab-worker.yaml"))


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_at_least_one_homelab_worker_runner_set_exists() -> None:
    assert _VALUES


@pytest.mark.parametrize("path", _VALUES, ids=lambda p: p.name)
def test_the_set_is_named_for_a_declared_host_and_idles_at_zero(path: Path) -> None:
    values = _load(path)
    host = path.name.removeprefix("values-").removesuffix("-homelab-worker.yaml")
    assert host in _HOSTS
    assert values["runnerScaleSetName"] == f"{host}-homelab-worker-k3s"
    assert values["minRunners"] == 0


@pytest.mark.parametrize("path", _VALUES, ids=lambda p: p.name)
def test_runner_pods_land_only_on_that_hosts_arm64_worker(path: Path) -> None:
    host = path.name.removeprefix("values-").removesuffix("-homelab-worker.yaml")
    spec = _load(path)["template"]["spec"]
    assert spec["nodeSelector"] == {_HOST_LABEL: host, "kubernetes.io/arch": "arm64"}
    keys = {t["key"] for t in spec["tolerations"]}
    assert _CLASS_TAINT in keys
    assert _HOLD_TAINT not in keys
    for container in spec["containers"]:
        assert re.fullmatch(r"\S+@sha256:[0-9a-f]{64}", container["image"])


@pytest.mark.parametrize("path", _VALUES, ids=lambda p: p.name)
def test_the_listener_runs_on_the_fleets_amd64_nodes(path: Path) -> None:
    listener = _load(path)["listenerTemplate"]["spec"]
    assert listener["nodeSelector"] == {"kubernetes.io/arch": "amd64"}
    assert not listener.get("tolerations")


# The fleet's container-mode reference set: the worker set runs CI jobs the way it does.
_FLEET = _ROOT / "ci-runner" / "k3s" / "phase2" / "arc" / "values-livespec-dev-tooling.yaml"


def _runner(values: dict[str, Any]) -> dict[str, Any]:
    return next(c for c in values["template"]["spec"]["containers"] if c["name"] == "runner")


@pytest.mark.parametrize("path", _VALUES, ids=lambda p: p.name)
def test_the_set_runs_jobs_in_the_fleets_container_mode(path: Path) -> None:
    # Jobs run in hook-created workflow pods on a local-path work volume, with the
    # fleet-patched hook and the fleet hook pod template, exactly as on the fleet's sets.
    values, fleet = _load(path), _load(_FLEET)
    assert values["containerMode"] == fleet["containerMode"]
    assert values["template"]["spec"]["volumes"] == fleet["template"]["spec"]["volumes"]
    runner, fleet_runner = _runner(values), _runner(fleet)
    for key in ("image", "command", "env", "volumeMounts", "securityContext"):
        assert runner[key] == fleet_runner[key], key


@pytest.mark.parametrize("path", _VALUES, ids=lambda p: p.name)
def test_the_set_asks_for_no_fleet_node_capacity(path: Path) -> None:
    # The churn-slot resource and its scheduler are the fleet CI nodes' admission; a worker
    # advertises neither, so a runner asking for them would never start.
    spec = _load(path)["template"]["spec"]
    assert "schedulerName" not in spec
    assert "resources" not in _runner(_load(path))


def test_install_arc_renders_each_worker_sets_hook_template_revision() -> None:
    script = (_ROOT / "ci-runner" / "k3s" / "install-arc.sh").read_text(encoding="utf-8")
    step = script.split('log "2b.', 1)[1].split('log "3.', 1)[0]
    assert "converge-hook-pod-template.sh" in step
    assert " --publish" in step
    assert " --render-values " in step
    assert '-f "$values"' not in step
