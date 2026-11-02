"""The pinned sandbox-driver-kubernetes reports its pod's node to the factory worker.

Orchestrator work-item `bd-ib-motuct` (plan `bd-ib-nmuyjc`). Fabro's `run_turn`
spans name the cluster node a Kubernetes sandbox's pod runs on (`k8s.node.name`).
The worker learns it from the provider's `sandbox/environment` map, which Petri
passes through unchanged. sandbox-driver-kubernetes reports `K8S_NODE_NAME` there
from v0.6.0. An earlier pin leaves the attribute absent on every span, silently,
so this file pins the floor and checks that every gmktec provider kind running
the plugin carries the role's digest for the same release.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "sandbox_driver_kubernetes" / "defaults" / "main.yml"
_GMKTEC = _REPO_ROOT / "ansible" / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_PLUGIN_PATH = "/usr/local/bin/sandbox-driver-kubernetes"


def _default(*, name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}: (\S+)$", _DEFAULTS.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match, f"{name} must be set in the role defaults"
    return match[1]


def test_the_pinned_plugin_reports_its_pods_node_in_the_sandbox_environment() -> None:
    version = _default(name="sandbox_driver_kubernetes_version")
    major, minor = (int(part) for part in version.lstrip("v").split(".")[:2])
    assert (major, minor) >= (0, 6), (
        f"plugin {version} does not report K8S_NODE_NAME in sandbox/environment, so Fabro's "
        f"run_turn spans carry no k8s.node.name. Pin v0.6.0 or later"
    )


def test_every_gmktec_provider_kind_running_the_plugin_carries_the_pinned_digest() -> None:
    digest = _default(name="sandbox_driver_kubernetes_sha256")
    text = _GMKTEC.read_text(encoding="utf-8")
    pinned = re.findall(rf"path: {re.escape(_PLUGIN_PATH)}\n\s+sha256: ([0-9a-f]{{64}})", text)
    assert (
        len(pinned) >= 2
    ), f"expected the gmktec provider kinds that run the plugin, found {pinned!r}"
    assert set(pinned) == {digest}, (
        f"gmktec provider kinds pin {sorted(set(pinned))} but the role installs {digest}; Fabro refuses "
        f"a plugin whose digest differs from the one it was configured with"
    )
