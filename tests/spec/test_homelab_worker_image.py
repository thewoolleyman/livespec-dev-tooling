"""The worker image of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

"The worker image MUST be built from this repository's sources as a native OCI image for the
host architecture, running upstream kubelet and containerd with no K3s agent, pinned to the
fleet's Kubernetes minor version." These read `homelab-worker/image/` the way a build does:

- every downloaded asset is pinned by version AND by a per-architecture SHA-256, selected by
  `TARGETARCH`, so a build for an architecture with no declared checksum fails instead of
  installing an unverified binary;
- the kubelet's minor version equals kube-proxy's and the fixture K3s's (a kubelet may not
  be newer than its API server) and nothing in the image is a K3s binary;
- the kubelet registers with the admission-hold taint, which only a separate operator action
  lifts.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_IMAGE = Path(__file__).resolve().parents[2] / "homelab-worker" / "image"
_DOCKERFILE = _IMAGE / "Dockerfile"
_ASSETS = ("KUBELET", "CONTAINERD", "RUNC", "CNI_PLUGINS", "FLANNEL_CNI", "CRICTL", "TAILSCALE")


def _args() -> dict[str, str]:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    return dict(re.findall(r"^ARG ([A-Za-z0-9_]+)=(\S+)$", text, flags=re.MULTILINE))


def test_every_asset_carries_an_arm64_sha256_pin() -> None:
    args = _args()
    for asset in _ASSETS:
        assert re.fullmatch(r"[0-9a-f]{64}", args[f"{asset}_SHA256_arm64"]), asset


def test_every_download_is_verified_against_its_pinned_checksum_by_target_architecture() -> None:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG TARGETARCH" in text
    for asset in _ASSETS:
        assert f'"$(pinned-sha256 {asset})' in text, asset
    assert 'var="${1}_SHA256_${TARGETARCH' in text
    assert "no pinned SHA-256 for" in text
    for url in re.findall(r'curl -fsSLo \S+ "([^"]+)"', text):
        assert "${TARGETARCH}" in url, url
        assert "amd64" not in url
        assert "x86_64" not in url


def _minor(version: str) -> str:
    match = re.search(r"v?(\d+\.\d+)\.\d+", version)
    assert match, version
    return match.group(1)


def test_the_kubelet_matches_the_fleet_minor_and_containerd_is_2_x() -> None:
    args = _args()
    worker = _IMAGE.parent
    [proxy] = re.findall(
        r"registry\.k8s\.io/kube-proxy:(v[\d.]+)@",
        (worker / "networking" / "kube-proxy.yaml").read_text(encoding="utf-8"),
    )
    [k3s] = re.findall(
        r"rancher/k3s:(v[\d.]+)-k3s",
        (worker / "fixture" / "k3s-fixture.sh").read_text(encoding="utf-8"),
    )
    assert _minor(args["KUBERNETES_VERSION"]) == _minor(proxy) == _minor(k3s)
    assert args["CONTAINERD_VERSION"].startswith("2.")
    assert (
        "dl.k8s.io/release/${KUBERNETES_VERSION}/bin/linux/${TARGETARCH}/kubelet"
        in _DOCKERFILE.read_text(encoding="utf-8")
    )


def test_the_image_carries_no_k3s_agent() -> None:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    downloads = re.findall(r'curl -fsSLo \S+ "([^"]+)"', text)
    installs = re.findall(r"install -m \d+ \S+ (\S+)", text)
    assert downloads
    assert [u for u in downloads if "k3s" in u.lower()] == []
    assert [i for i in installs if "k3s" in i.lower()] == []
    for unit in (_IMAGE / "systemd").glob("*.service"):
        assert "k3s" not in unit.read_text(encoding="utf-8").lower(), unit


def test_systemd_is_pid_1_and_the_runtime_uses_the_systemd_cgroup_driver() -> None:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["/sbin/init"]' in text
    assert "STOPSIGNAL SIGRTMIN+3" in text
    assert "SystemdCgroup = true" in (_IMAGE / "containerd-config.toml").read_text(encoding="utf-8")


def test_the_kubelet_registers_under_the_admission_hold_taint() -> None:
    unit = (_IMAGE / "systemd" / "kubelet.service").read_text(encoding="utf-8")
    assert "--register-with-taints=homelab-worker.livespec.dev/admission=hold:NoSchedule" in unit
    assert "--bootstrap-kubeconfig=" in unit


def test_the_worker_enrolls_on_the_tailnet_untagged_with_no_auth_key() -> None:
    # tailscale-admin retired tags fleet-wide (maintainer ruling 2026-08-17): every persistent
    # machine is an untagged autogroup:member enrolled by interactive login, never by an auth key.
    unit = (_IMAGE / "systemd" / "tailscaled.service").read_text(encoding="utf-8")
    assert "--state=/var/lib/tailscale/" in unit
    for forbidden in ("advertise-tags", "auth-key", "authkey", "TS_TAGS"):
        assert forbidden not in unit, forbidden
    assert " up " not in unit
