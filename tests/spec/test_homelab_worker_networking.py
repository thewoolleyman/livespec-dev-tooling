"""Worker-class networking of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

The worker runs upstream kubelet and containerd with no K3s agent, so the three networking agents
K3s embeds (flannel, kube-proxy and kube-router) run on it as DaemonSets from
`homelab-worker/networking/`. These parse those manifests and assert:

- every DaemonSet selects only the worker class, runs on the host network and tolerates the
  admission hold, so it never doubles an embedded agent on a K3s node;
- each image is pinned by digest;
- flannel's pod network is the one kube-proxy treats as the cluster CIDR, flannel's interface comes
  from the per-cluster ConfigMap, kube-proxy names its node by NODE_NAME, and kube-router runs the
  firewall alone;

No assertion restates a fleet value (versions, addresses, CIDRs, interfaces): those are
configuration, and a test pinning them breaks on every legitimate change.
- each agent reaches the API server through one per-cluster ConfigMap, never the kubernetes
  Service it would otherwise depend on, and no agent may read Secrets;
- every object carries the one rollback label.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

_NETWORKING = Path(__file__).resolve().parents[2] / "homelab-worker" / "networking"
_ROLLBACK_LABEL = "homelab-worker.livespec.dev/networking"
_AGENTS = ("homelab-worker-flannel", "homelab-worker-kube-proxy", "homelab-worker-kube-router")
_DIGEST = re.compile(r"^[^@\s]+:[^@\s]+@sha256:[0-9a-f]{64}$")


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


@pytest.mark.parametrize("name", _AGENTS)
def test_each_agent_runs_only_on_the_worker_class_on_the_host_network(name: str) -> None:
    pod = _one(kind="DaemonSet", name=name)["spec"]["template"]["spec"]
    assert pod["nodeSelector"] == {"homelab-worker.livespec.dev/class": "worker"}
    assert pod["hostNetwork"] is True
    assert {"operator": "Exists", "effect": "NoSchedule"} in pod["tolerations"]
    assert pod["serviceAccountName"] == name
    for container in pod.get("initContainers", []) + pod["containers"]:
        assert _DIGEST.match(container["image"]), container["image"]


@pytest.mark.parametrize("name", _AGENTS)
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
    assert set(cluster) == {"api-server-host", "api-server-port", "flannel-iface"}
    assert all(isinstance(v, str) and v for v in cluster.values())
    assert cluster["api-server-port"].isdigit()


def _cluster_cidr() -> str:
    [flag] = [
        a
        for a in _container(name="homelab-worker-kube-proxy")["command"]
        if a.startswith("--cluster-cidr=")
    ]
    return flag.removeprefix("--cluster-cidr=")


def test_flannel_pod_network_is_kube_proxys_cluster_cidr() -> None:
    data = _one(kind="ConfigMap", name="homelab-worker-flannel")["data"]
    net = json.loads(data["net-conf.json"])
    assert net["Network"] == _cluster_cidr()
    assert net["Backend"]["Type"] == "vxlan"
    cni = json.loads(data["cni-conf.json"])
    assert cni["plugins"][0]["type"] == "flannel"
    flannel = _container(name="homelab-worker-flannel")
    assert "--kube-subnet-mgr" in flannel["args"]
    iface = {e["name"]: e for e in flannel["env"]}["FLANNELD_IFACE"]
    assert iface["valueFrom"]["configMapKeyRef"] == {
        "name": "homelab-worker-cluster",
        "key": "flannel-iface",
    }


def test_kube_proxy_names_its_node_by_node_name_with_an_explicit_proxy_mode() -> None:
    command = _container(name="homelab-worker-kube-proxy")["command"]
    assert "--hostname-override=$(NODE_NAME)" in command
    assert any(a.startswith("--proxy-mode=") for a in command)
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
    assert objects
    for obj in objects:
        assert obj["metadata"]["labels"][_ROLLBACK_LABEL] == "true"
