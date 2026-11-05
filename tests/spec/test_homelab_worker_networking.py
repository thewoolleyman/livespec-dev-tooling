"""Worker-class networking of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

The worker runs upstream kubelet and containerd with no K3s agent, so the three networking agents
K3s embeds (flannel, kube-proxy and kube-router) run on it as DaemonSets from
`homelab-worker/networking/`. These parse those manifests and assert:

- every DaemonSet selects only the worker class, runs on the host network and tolerates the
  admission hold, so it never doubles an embedded agent on a K3s node;
- each image is the fleet-matched upstream version, pinned by digest;
- flannel carries the fleet's VXLAN network and CNI conflist, kube-proxy the fleet's K3s flag set,
  and kube-router the firewall alone;
- each agent reaches the API server through one per-cluster ConfigMap, never the kubernetes
  Service it would otherwise depend on, and no agent may read Secrets;
- every object carries the one rollback label.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

_NETWORKING = Path(__file__).resolve().parents[2] / "homelab-worker" / "networking"
_ROLLBACK_LABEL = "homelab-worker.livespec.dev/networking"
_IMAGES = {
    "homelab-worker-flannel": "ghcr.io/flannel-io/flannel:v0.28.4@sha256:",
    "homelab-worker-kube-proxy": "registry.k8s.io/kube-proxy:v1.36.2@sha256:",
    "homelab-worker-kube-router": "docker.io/cloudnativelabs/kube-router:v2.6.3@sha256:",
}


def _objects() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for path in sorted(_NETWORKING.glob("*.yaml")):
        found.extend(d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d)
    return found


def _one(*, kind: str, name: str) -> dict[str, Any]:
    [found] = [o for o in _objects() if o["kind"] == kind and o["metadata"]["name"] == name]
    return found


def _container(*, name: str) -> dict[str, Any]:
    pod = _one(kind="DaemonSet", name=name)["spec"]["template"]["spec"]
    return pod["containers"][0]


@pytest.mark.parametrize("name", sorted(_IMAGES))
def test_each_agent_runs_only_on_the_worker_class_on_the_host_network(name: str) -> None:
    pod = _one(kind="DaemonSet", name=name)["spec"]["template"]["spec"]
    assert pod["nodeSelector"] == {"homelab-worker.livespec.dev/class": "worker"}
    assert pod["hostNetwork"] is True
    assert {"operator": "Exists", "effect": "NoSchedule"} in pod["tolerations"]
    assert pod["serviceAccountName"] == name
    for container in pod.get("initContainers", []) + pod["containers"]:
        assert container["image"].startswith(_IMAGES[name])
        assert len(container["image"].split("@sha256:")[1]) == 64


@pytest.mark.parametrize("name", sorted(_IMAGES))
def test_each_agent_reaches_the_api_server_through_the_cluster_configmap(name: str) -> None:
    env = {e["name"]: e for e in _container(name=name)["env"]}
    for var, key in (
        ("KUBERNETES_SERVICE_HOST", "api-server-host"),
        ("KUBERNETES_SERVICE_PORT", "api-server-port"),
    ):
        assert env[var]["valueFrom"]["configMapKeyRef"] == {
            "name": "homelab-worker-cluster",
            "key": key,
        }
    cluster = _one(kind="ConfigMap", name="homelab-worker-cluster")["data"]
    assert cluster == {
        "api-server-host": "poweredge-xubuntu.perch-rudd.ts.net",
        "api-server-port": "6443",
        "flannel-iface": "tailscale0",
    }


def test_flannel_carries_the_fleet_vxlan_network_and_cni_conflist() -> None:
    data = _one(kind="ConfigMap", name="homelab-worker-flannel")["data"]
    assert json.loads(data["net-conf.json"]) == {
        "Network": "10.42.0.0/16",
        "EnableIPv6": False,
        "Backend": {"Type": "vxlan", "VNI": 1, "Port": 8472},
    }
    cni = json.loads(data["cni-conf.json"])
    assert (cni["name"], cni["cniVersion"]) == ("cbr0", "1.0.0")
    assert [p["type"] for p in cni["plugins"]] == ["flannel", "portmap", "bandwidth"]
    assert cni["plugins"][0]["delegate"] == {
        "hairpinMode": True,
        "forceAddress": True,
        "isDefaultGateway": True,
    }
    flannel = _container(name="homelab-worker-flannel")
    assert flannel["args"] == ["--ip-masq", "--kube-subnet-manager"]
    iface = {e["name"]: e for e in flannel["env"]}["FLANNELD_IFACE"]
    assert iface["valueFrom"]["configMapKeyRef"]["key"] == "flannel-iface"


def test_kube_proxy_runs_the_fleet_k3s_flag_set_in_iptables_mode() -> None:
    assert _container(name="homelab-worker-kube-proxy")["command"] == [
        "/usr/local/bin/kube-proxy",
        "--cluster-cidr=10.42.0.0/16",
        "--conntrack-max-per-core=0",
        "--conntrack-tcp-timeout-close-wait=0s",
        "--conntrack-tcp-timeout-established=0s",
        "--healthz-bind-address=127.0.0.1",
        "--proxy-mode=iptables",
        "--hostname-override=$(NODE_NAME)",
    ]
    binding = _one(kind="ClusterRoleBinding", name="homelab-worker-kube-proxy")
    assert binding["roleRef"]["name"] == "system:node-proxier"


def test_kube_router_runs_the_firewall_alone() -> None:
    assert _container(name="homelab-worker-kube-router")["args"] == [
        "--run-firewall=true",
        "--run-router=false",
        "--run-service-proxy=false",
    ]


def test_no_agent_may_read_secrets_or_write_beyond_its_own_node_status_and_events() -> None:
    writes = {"create", "update", "patch", "delete", "deletecollection", "*"}
    for role in (o for o in _objects() if o["kind"] == "ClusterRole"):
        for rule in role["rules"]:
            assert "secrets" not in rule["resources"]
            assert "*" not in rule["resources"]
            if writes & set(rule["verbs"]):
                assert set(rule["resources"]) <= {"nodes/status", "events"}


def test_every_object_carries_the_one_rollback_label() -> None:
    objects = _objects()
    assert len(objects) == 13
    for obj in objects:
        assert obj["metadata"]["labels"][_ROLLBACK_LABEL] == "true"
