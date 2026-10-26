"""The mi-homelab organisation's factory namespace is its own, and its quota is a split.

Rulings R668 / R669(1) keep homelab's work out of reach of the shared fleet
Fabro instance, and a pod in the `factory` namespace can be exec'd into by that
namespace's `sandbox-launcher` credential. So homelab's Kubernetes sandboxes run
in `factory-mi-homelab`, declared under `ci-runner/k3s/phase2/factory-mi-homelab/`
and applied by the boot converge. The pool has no room for an additional quota,
so homelab's two runs are carved out of the fleet's eight (coordinator ruling on
livespec-dev-tooling-dfixhe, 2026-10-24; plan kubernetes-sandbox-backend,
bd-ib-nmuyjc).

These tests read the REAL manifests, the REAL boot converge and the REAL
converge-unit file list.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_HOMELAB_DIR = _PHASE2 / "factory-mi-homelab"
_HOMELAB_MANIFEST = _HOMELAB_DIR / "factory-mi-homelab.yaml"
_FLEET_NAMESPACE = _PHASE2 / "factory" / "factory-namespace.yaml"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_ROLE_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit" / "defaults" / "main.yml"
_NAMESPACE = "factory-mi-homelab"
_CLUSTER_SCOPED = {"Namespace", "ClusterRoleBinding"}
# The pool check in factory/DERIVATION.md "The quota, raised to twelve runs":
# CI's cpu-requesting queues 17 + factory 56 = 73 of ~104 schedulable cpu. The
# fleet and homelab quotas together must stay at 56.
_FACTORY_CPU_TOTAL = 56
_HOMELAB_RUNS = 2
_RUN_CPU = 4


def _documents(*, path: Path) -> list[str]:
    return [doc for doc in path.read_text(encoding="utf-8").split("\n---\n") if "kind:" in doc]


def _field(*, document: str, pattern: str) -> str:
    match = re.search(pattern, document, flags=re.MULTILINE)
    return match.group(1).strip().strip('"') if match else ""


def _kind(*, document: str) -> str:
    return _field(document=document, pattern=r"^kind:\s*(\S+)")


def _quota_cpu(*, path: Path) -> int:
    quotas = [doc for doc in _documents(path=path) if _kind(document=doc) == "ResourceQuota"]
    assert len(quotas) == 1, f"{path.name} must declare exactly one ResourceQuota"
    return int(_field(document=quotas[0], pattern=r"^\s+requests\.cpu:\s*(\S+)"))


def test_the_homelab_namespace_declares_its_own_launcher_policy_and_quota() -> None:
    documents = _documents(path=_HOMELAB_MANIFEST)
    kinds = sorted(_kind(document=doc) for doc in documents)
    assert kinds == sorted(
        [
            "ClusterRoleBinding",
            "Namespace",
            "NetworkPolicy",
            "ResourceQuota",
            "Role",
            "RoleBinding",
            "Secret",
            "ServiceAccount",
        ]
    ), f"the homelab namespace must repeat the factory objects one for one; found {kinds}"
    for document in documents:
        kind = _kind(document=document)
        if kind == "Namespace":
            assert _field(document=document, pattern=r"^  name:\s*(\S+)") == _NAMESPACE
            continue
        if kind in _CLUSTER_SCOPED:
            continue
        namespace = _field(document=document, pattern=r"^  namespace:\s*(\S+)")
        assert namespace == _NAMESPACE, (
            f"{kind} declares namespace {namespace!r}: every namespaced homelab object must be IN "
            f"{_NAMESPACE!r}, or homelab's pods share a credential with the fleet's"
        )


def test_every_launcher_binding_names_only_the_homelab_service_account() -> None:
    for document in _documents(path=_HOMELAB_MANIFEST):
        if _kind(document=document) not in {"RoleBinding", "ClusterRoleBinding"}:
            continue
        subjects = document.split("subjects:", 1)[1]
        assert re.findall(r"namespace:\s*(\S+)", subjects) == [
            _NAMESPACE
        ], "a homelab binding must grant only the homelab ServiceAccount, never the fleet's"


def test_the_quota_is_a_split_of_the_fleet_total_not_an_addition() -> None:
    homelab = _quota_cpu(path=_HOMELAB_MANIFEST)
    fleet = _quota_cpu(path=_FLEET_NAMESPACE)
    assert homelab == _HOMELAB_RUNS * _RUN_CPU, (
        f"homelab's quota must hold its {_HOMELAB_RUNS} runs at {_RUN_CPU} cpu each, matching the "
        f"instance's max_concurrent_runs; found {homelab}"
    )
    assert fleet + homelab == _FACTORY_CPU_TOTAL, (
        f"fleet {fleet} + homelab {homelab} cpu must stay {_FACTORY_CPU_TOTAL}: the pool check "
        "(CI cpu 17 + factory 56 = 73 of ~104) was derived for that total"
    )


def test_the_boot_converge_applies_and_renders_the_homelab_namespace() -> None:
    converge = _BOOT_CONVERGE.read_text(encoding="utf-8")
    fleet_apply = converge.index('kubectl apply -f "${FACTORY_DIR}"')
    homelab_apply = converge.index('kubectl apply -f "${FACTORY_MI_HOMELAB_DIR}"')
    assert fleet_apply < homelab_apply, (
        "the homelab directory must apply after ../factory/: its node-reader binding names the "
        "ClusterRole that directory defines"
    )
    assert "--namespace factory-mi-homelab" in converge, (
        "the converge must render the homelab launcher's kubeconfig, or a reboot leaves the "
        "homelab instance holding a token the fresh API server has never seen"
    )
    assert '"$FACTORY_MI_HOMELAB_DIR"' in converge, "the homelab directory must be required"


def test_the_converge_unit_ships_the_homelab_manifest() -> None:
    defaults = _ROLE_DEFAULTS.read_text(encoding="utf-8")
    assert re.search(r"^  - factory-mi-homelab$", defaults, flags=re.MULTILINE), (
        "the role creates each installed subdirectory from ci_converge_unit_directories before "
        "copying into it, so the homelab directory must be listed there or the copy fails"
    )
    assert "src: factory-mi-homelab/factory-mi-homelab.yaml" in defaults, (
        "the boot converge runs from the installed tree with no checkout, so the role must ship "
        "the homelab manifest or the namespace never appears"
    )
