"""The warm uv lower follows every node that can provision a work volume.

The compilation-cache writer is intentionally a singleton on the cache-tier
carrier, but the uv lower is copied by the local-path provisioner from the
node-local ``.warm`` directory.  A second runner node therefore needs its own
uv population pod; scheduling the existing carrier CronJob there would make
two writers contend for the carrier's other hostPath-backed caches.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import yaml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_PHASE2 = _K3S / "phase2"
_PROVISION = _K3S / "provision-k3s.sh"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_SERVER_LABEL_CONVERGE = _PHASE2 / "reconstruct" / "converge-warm-uv-node-labels.sh"
_CONVERGE_UNIT_DEFAULTS = (
    _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit" / "defaults" / "main.yml"
)
_MANIFEST = _PHASE2 / "warm-cache" / "warm-cache-cronjob.yaml"
_POPULATOR = _PHASE2 / "warm-cache" / "warm-cache-populate.sh"

_WARM_UV_LABEL = "ci-runner.io/warm-uv-cache=true"
_TIER_CARRIER_LABEL = "ci-runner.io/cache-tier-carrier"
_WARM_ROOT = "/var/lib/rancher/k3s/storage/.warm"


_KUBECTL_SHIM = """\
printf 'kubectl %s\\n' "$*" >> "$ARGV_LOG"
if [ "$1" = "label" ]; then exit 0; fi
if [ "$1" = "get" ] && [ "$2" = "node" ]; then
  printf 'node/%s\\n' "$3"
  exit 0
fi
if [ "$1" = "get" ] && [ "$2" = "nodes" ]; then
  printf 'node/agent-without-facilities\\n'
  exit 0
fi
"""


def _is_named_document(document: dict[str, Any], *, kind: str, name: str) -> bool:
    """Whether one parser-produced document names the requested workload."""
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        return False
    parsed_metadata = cast(dict[str, Any], metadata)
    parsed_kind = document.get("kind")
    parsed_name = parsed_metadata.get("name")
    return (
        isinstance(parsed_kind, str)
        and parsed_kind == kind
        and isinstance(parsed_name, str)
        and parsed_name == name
    )


def test_named_document_rejects_a_malformed_document_without_metadata() -> None:
    """The manifest lookup ignores parser output missing Kubernetes metadata."""
    assert not _is_named_document({"kind": "DaemonSet"}, kind="DaemonSet", name="example")


def _manifest_document(documents: list[dict[str, Any]], *, kind: str, name: str) -> dict[str, Any]:
    """Return one named, parser-validated manifest document."""
    matched = [
        document for document in documents if _is_named_document(document, kind=kind, name=name)
    ]
    assert len(matched) == 1, f"expected exactly one {kind}/{name}; found {len(matched)}"
    return matched[0]


def test_warm_uv_population_reaches_each_work_volume_node_without_moving_the_carrier_writer() -> (
    None
):
    """A daemon on every labelled work-volume node owns only that node's uv lower."""
    # Parse every document before examining its placement.  Text splitting alone
    # accepts malformed indentation, which would prevent any workload in this
    # file from converging.
    documents = list(yaml.safe_load_all(_MANIFEST.read_text(encoding="utf-8")))
    assert documents and all(isinstance(document, dict) for document in documents)
    parsed_documents = cast(list[dict[str, Any]], documents)

    for procedure in (_PROVISION, _BOOT_CONVERGE):
        source = procedure.read_text(encoding="utf-8")
        assert _WARM_UV_LABEL in source, (
            f"{procedure.name} must assert the distinct warm-uv node label after it has "
            "confirmed this node carries the ci-workvols mount"
        )
        assert "/var/lib/rancher/k3s/storage" in source and "--overwrite" in source, (
            f"{procedure.name} must derive the label from the local work-volume mount and "
            "make a rerun idempotent"
        )

    per_node_uv = _manifest_document(
        parsed_documents, kind="DaemonSet", name="warm-uv-cache-populate"
    )
    per_node_uv_text = yaml.safe_dump(per_node_uv, sort_keys=False)
    assert "ci-runner.io/warm-uv-cache" in per_node_uv_text, (
        "the per-node uv populator must select the dedicated work-volume label, not the "
        "cache-tier carrier label"
    )
    assert _TIER_CARRIER_LABEL in per_node_uv_text and "DoesNotExist" in per_node_uv_text, (
        "the DaemonSet must leave the carrier to the singleton writer, so its uv run and "
        "the carrier CronJob never write the same warm root concurrently"
    )
    assert f"path: {_WARM_ROOT}" in per_node_uv_text, (
        "the per-node populator must write the hidden sibling that the local-path "
        "provisioner seeds into a volume on that same node"
    )
    containers = cast(list[dict[str, Any]], per_node_uv["spec"]["template"]["spec"]["containers"])
    assert isinstance(containers, list) and len(containers) == 1
    environment = cast(list[dict[str, Any]], containers[0]["env"])
    assert isinstance(environment, list)
    uv_only = next(entry for entry in environment if entry["name"] == "WARM_CACHE_UV_ONLY")
    assert (
        uv_only["value"] == "true"
    ), "the per-node leg must not become a second cargo/sccache writer"
    assert "proxy-store" not in per_node_uv_text and "ci-runner-bin" not in per_node_uv_text, (
        "the per-node uv leg needs only the warm root and proxy Service, not carrier "
        "hostPath caches"
    )

    carrier = _manifest_document(parsed_documents, kind="CronJob", name="warm-cache-populate")
    carrier_text = yaml.safe_dump(carrier, sort_keys=False)
    assert _TIER_CARRIER_LABEL in carrier_text
    assert (
        "WARM_CACHE_UV_ONLY" not in carrier_text
    ), "the carrier CronJob remains the sole cargo and compilation-cache writer"

    populator = _POPULATOR.read_text(encoding="utf-8")
    assert 'WARM_CACHE_UV_ONLY="${WARM_CACHE_UV_ONLY:-false}"' in populator
    assert 'if [ "${WARM_CACHE_UV_ONLY}" = false ]; then' in populator, (
        "the shared populator must be able to skip carrier-only cache writes on a "
        "non-carrier work-volume node"
    )


def test_server_converge_labels_a_full_facilities_agent_and_removes_the_other_label(
    *, tmp_path: Path
) -> None:
    """The server uses every installed profile, rather than only its own mount.

    `gmktec-xubuntu` is an agent and cannot run the cluster-wide converge.  The
    server must consequently read the profiles the `ci_converge_unit` role
    installed and set its warm-uv selector label for a full-facilities agent.
    The fake API records the real helper's commands, so this tests the
    profile-to-label control flow rather than merely matching its shell text.
    """
    assert _SERVER_LABEL_CONVERGE.is_file(), (
        f"{_SERVER_LABEL_CONVERGE.relative_to(_REPO_ROOT)} must reconcile warm-uv labels from "
        "every installed ci_pool profile; a server converge that only checks its own mount "
        "cannot label an already-registered agent"
    )
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "agent-with-facilities.env").write_text(
        "NODE_NAME=agent-with-facilities\nCI_NODE_FACILITIES=full\n", encoding="utf-8"
    )
    (profiles / "agent-without-facilities.env").write_text(
        "NODE_NAME=agent-without-facilities\nCI_NODE_FACILITIES=none\n", encoding="utf-8"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(f"#!/usr/bin/env bash\n{_KUBECTL_SHIM}", encoding="utf-8")
    kubectl.chmod(0o755)
    log = tmp_path / "argv.log"
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_")}
    env.update(
        {
            "ARGV_LOG": str(log),
            "CI_WARM_UV_LABEL_PROFILES_DIR": str(profiles),
            "KUBECONFIG": str(kubeconfig),
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
        }
    )
    completed = subprocess.run(
        ["bash", str(_SERVER_LABEL_CONVERGE)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines()

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (
        "kubectl label --overwrite node agent-with-facilities ci-runner.io/warm-uv-cache=true"
        in invoked
    )
    assert "kubectl label node agent-without-facilities ci-runner.io/warm-uv-cache-" in invoked

    boot_converge = _BOOT_CONVERGE.read_text(encoding="utf-8")
    assert _SERVER_LABEL_CONVERGE.name in boot_converge
    assert f"reconstruct/{_SERVER_LABEL_CONVERGE.name}" in _CONVERGE_UNIT_DEFAULTS.read_text(
        encoding="utf-8"
    )
