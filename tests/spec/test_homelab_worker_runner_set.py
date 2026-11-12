"""Phase E placement of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

Each homelab worker gets a host-unique ARC runner scale set (`ci-runner/k3s/phase2/arc/worker/values-*-homelab-worker.yaml`,
research/009), addressed by name so no existing CI traffic moves. These parse every such values
file and assert rules that hold for any host:

- the set is named `<host>-homelab-worker-k3s` for a host the homelab-worker host list declares,
  and idles at zero runners;
- its runner pods select that host's worker and arm64, and tolerate the permanent class taint but
  not the admission hold, so lifting the hold stays the operator's explicit gate;
- its listener runs on the fleet's amd64 nodes, never on a worker;
- the runner image is pinned by digest;
- jobs run in the fleet's container mode (compared against the fleet's reference set), asking
  for none of the fleet CI nodes' capacity;
- the CI stack converge, not a one-time installer, upgrades the set, so its hook template
  revision follows every hook change.

No assertion restates a production value.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _ROOT / "ci-runner" / "k3s" / "phase2"
_ARC = _PHASE2 / "arc" / "worker"
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


_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_PLACEHOLDER = "arc-hook-pod-template-@HOOK_REVISION@"


def _run_converge_scale_set_step(*, tmp_path: Path, worker_files: list[str]) -> list[str]:
    """Run the converge's own release-map and step-7 text against stub tools; return helm's calls."""
    converge = _CONVERGE.read_text(encoding="utf-8")
    scale_sets = converge.split("declare -A SCALE_SETS=(", 1)[1].split("\nlog() {", 1)[0]
    step = converge.split('log "7a.', 1)[1].split('log "7b.', 1)[0]
    arc = tmp_path / "arc"
    (arc / "worker").mkdir(parents=True)
    fleet_files = re.findall(r'\]="(values-[^"]+)"', scale_sets)
    for name in [*fleet_files, *(f"worker/{w}" for w in worker_files)]:
        _ = (arc / name).write_text(f"mount: {_PLACEHOLDER}\n", encoding="utf-8")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    calls = tmp_path / "helm.calls"
    hook_stub = "\n".join(
        [
            "#!/bin/bash",
            'case "$1" in',
            "  --name) echo arc-hook-pod-template-cafe ;;",
            '  --render-values) sed "s/@HOOK_REVISION@/cafe/" "$2" > "$3" ;;',
            "esac",
            "",
        ]
    )
    helm_stub = "\n".join(
        [
            "#!/bin/bash",
            'release="$3"; values="$8"',
            f'echo "$release $(cat "$values")" >> {calls}',
            "",
        ]
    )
    for path, text in (
        (arc / "converge-hook-pod-template.sh", hook_stub),
        (arc / "render-arch-overlay.sh", '#!/bin/bash\n: > "$3"\n'),
        (stubs / "helm", helm_stub),
    ):
        _ = path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    program = "\n".join(
        [
            "set -euo pipefail",
            f'ARC_DIR="{arc}"',
            "RUNNERS_NAMESPACE=arc-runners",
            "ARC_SCALE_SET_CHART=chart.tgz",
            "log() { :; }",
            f'declare -A SCALE_SETS=({scale_sets}\nlog "7a.{step}',
        ]
    )
    _ = subprocess.run(
        ["/bin/bash", "-c", program],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": f"{stubs}:/usr/bin:/bin"},
        timeout=60,
    )
    return calls.read_text(encoding="utf-8").splitlines()


def test_the_ci_stack_converge_upgrades_each_worker_set_on_the_published_hook_revision(
    tmp_path: Path,
) -> None:
    # Mocked worker hosts, not the committed one: the converge finds a worker's set by its
    # values file alone, and upgrades it with the placeholder rendered like a fleet set's.
    calls = _run_converge_scale_set_step(
        tmp_path=tmp_path,
        worker_files=["values-alpha-homelab-worker.yaml", "values-beta-homelab-worker.yaml"],
    )
    by_release = dict(line.split(" ", 1) for line in calls)
    for release in ("alpha-homelab-worker-k3s", "beta-homelab-worker-k3s"):
        assert by_release[release] == "mount: arc-hook-pod-template-cafe"
    assert all(_PLACEHOLDER not in rendered for rendered in by_release.values())


def test_the_ci_stack_converge_runs_unchanged_with_no_worker_set(tmp_path: Path) -> None:
    calls = _run_converge_scale_set_step(tmp_path=tmp_path, worker_files=[])
    assert calls
    assert not [line for line in calls if "homelab-worker" in line]


def test_every_committed_worker_set_declares_its_architecture() -> None:
    # The converge refuses a release the per-class architecture list does not declare.
    declared = {
        line.split()[1]: line.split()[2]
        for line in (_PHASE2 / "workload-arch.conf").read_text(encoding="utf-8").splitlines()
        if line.startswith("release ")
    }
    for path in _VALUES:
        release = path.name.removeprefix("values-").removesuffix(".yaml") + "-k3s"
        assert declared.get(release) == "arm64", release


def test_the_converge_unit_role_installs_the_worker_sets_values() -> None:
    role = _ROOT / "ansible" / "roles" / "ci_converge_unit"
    assert (
        "arc/worker"
        in yaml.safe_load((role / "defaults" / "main.yml").read_text("utf-8"))[
            "ci_converge_unit_directories"
        ]
    )
    assert "/arc/worker/values-*-homelab-worker.yaml" in (role / "tasks" / "main.yml").read_text(
        "utf-8"
    )


def test_the_one_time_installer_no_longer_installs_worker_sets() -> None:
    script = (_ROOT / "ci-runner" / "k3s" / "install-arc.sh").read_text(encoding="utf-8")
    assert 'helm upgrade --install "$release"' not in script
    assert not list((_ROOT / "ci-runner" / "k3s" / "arc").glob("values-*-homelab-worker.yaml"))
