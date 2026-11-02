"""The warm uv lower follows every node that can provision a work volume.

The compilation-cache writer is intentionally a singleton on the cache-tier
carrier, but the uv lower is copied by the local-path provisioner from the
node-local ``.warm`` directory.  A second runner node therefore needs its own
uv population pod; scheduling the existing carrier CronJob there would make
two writers contend for the carrier's other hostPath-backed caches.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_PHASE2 = _K3S / "phase2"
_PROVISION = _K3S / "provision-k3s.sh"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_MANIFEST = _PHASE2 / "warm-cache" / "warm-cache-cronjob.yaml"
_POPULATOR = _PHASE2 / "warm-cache" / "warm-cache-populate.sh"

_WARM_UV_LABEL = "ci-runner.io/warm-uv-cache=true"
_TIER_CARRIER_LABEL = "ci-runner.io/cache-tier-carrier"
_WARM_ROOT = "/var/lib/rancher/k3s/storage/.warm"


def _manifest_document(*, kind: str, name: str) -> str:
    """Return one named YAML document without relying on a host YAML package."""
    documents = _MANIFEST.read_text(encoding="utf-8").split("\n---\n")
    matched = [
        document
        for document in documents
        if f"kind: {kind}" in document and f"  name: {name}" in document
    ]
    assert len(matched) == 1, f"expected exactly one {kind}/{name}; found {len(matched)}"
    return matched[0]


def test_warm_uv_population_reaches_each_work_volume_node_without_moving_the_carrier_writer() -> (
    None
):
    """A daemon on every labelled work-volume node owns only that node's uv lower."""
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

    per_node_uv = _manifest_document(kind="DaemonSet", name="warm-uv-cache-populate")
    assert 'ci-runner.io/warm-uv-cache: "true"' in per_node_uv, (
        "the per-node uv populator must select the dedicated work-volume label, not the "
        "cache-tier carrier label"
    )
    assert _TIER_CARRIER_LABEL in per_node_uv and "DoesNotExist" in per_node_uv, (
        "the DaemonSet must leave the carrier to the singleton writer, so its uv run and "
        "the carrier CronJob never write the same warm root concurrently"
    )
    assert f"path: {_WARM_ROOT}" in per_node_uv, (
        "the per-node populator must write the hidden sibling that the local-path "
        "provisioner seeds into a volume on that same node"
    )
    assert (
        'name: WARM_CACHE_UV_ONLY\n                  value: "true"' in per_node_uv
    ), "the per-node leg must not become a second cargo/sccache writer"
    assert "proxy-store" not in per_node_uv and "ci-runner-bin" not in per_node_uv, (
        "the per-node uv leg needs only the warm root and proxy Service, not carrier "
        "hostPath caches"
    )

    carrier = _manifest_document(kind="CronJob", name="warm-cache-populate")
    assert 'ci-runner.io/cache-tier-carrier: "true"' in carrier
    assert (
        "WARM_CACHE_UV_ONLY" not in carrier
    ), "the carrier CronJob remains the sole cargo and compilation-cache writer"

    populator = _POPULATOR.read_text(encoding="utf-8")
    assert 'WARM_CACHE_UV_ONLY="${WARM_CACHE_UV_ONLY:-false}"' in populator
    assert 'if [ "${WARM_CACHE_UV_ONLY}" = false ]; then' in populator, (
        "the shared populator must be able to skip carrier-only cache writes on a "
        "non-carrier work-volume node"
    )
