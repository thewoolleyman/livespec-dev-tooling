"""Serving-CSR approval of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

No built-in approver signs a `kubernetes.io/kubelet-serving` CSR, and a worker is never given
CSR-approve rights, so `homelab-worker/enrollment/approve-serving-csr.sh` approves each one from
the operator's side after checking it. These generate real PKCS#10 requests with `openssl` and
serve them through a stub `kubectl`, then assert that only a request matching the worker's
identity, usages, names and Node addresses is approved, and every other one is named with its
reason.
"""

from __future__ import annotations

import base64
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []


def _mock_hosts(root: Path, *names: str) -> Path:
    """A hosts directory declaring only the made-up hosts the test names."""
    hosts = root / "hosts"
    hosts.mkdir(parents=True, exist_ok=True)
    for name in names:
        (hosts / f"{name}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    return hosts


_APPROVE = (
    Path(__file__).resolve().parents[2] / "homelab-worker" / "enrollment" / "approve-serving-csr.sh"
)
_HOST = "alpha"
_DOMAIN = "tailnet.test"
_WORKER = f"{_HOST}-homelab-worker"
_USER = f"system:node:{_WORKER}"
_NODE_IP = "100.101.102.103"
_GOOD_USAGES = ("digital signature", "key encipherment", "server auth")


@dataclass(frozen=True, kw_only=True)
class _Cluster:
    root: Path
    bin_dir: Path
    approved: Path


@pytest.fixture
def cluster(tmp_path: Path) -> _Cluster:
    root = tmp_path / "cluster"
    root.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    made = _Cluster(root=root, bin_dir=bin_dir, approved=tmp_path / "approved.log")
    (root / "node-ips").write_text(f"{_NODE_IP}\n", encoding="utf-8")
    (root / "list").write_text("", encoding="utf-8")
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(
        "#!/bin/bash\n"
        f'root="{root}"\n'
        'case "$1 $2" in\n'
        '  "get node")\n'
        '    if [ -f "$root/lookup-error" ]; then cat "$root/lookup-error" >&2; exit 1; fi\n'
        '    if [ ! -f "$root/node-ips" ]; then\n'
        '      echo "Error from server (NotFound): nodes \\"$3\\" not found" >&2; exit 1\n'
        "    fi\n"
        '    cat "$root/node-ips" ;;\n'
        '  "get csr")\n'
        '    if [ "$3" = "-o" ]; then cat "$root/list"\n'
        '    elif [ "$5" = "jsonpath={.spec.request}" ]; then cat "$root/$3.request"\n'
        '    else cat "$root/$3.usages"; fi ;;\n'
        f'  "certificate approve") echo "$3" >> "{made.approved}" ;;\n'
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IXUSR)
    return made


def _add_csr(
    *,
    cluster: _Cluster,
    name: str,
    subject: str = f"/O=system:nodes/CN={_USER}",
    sans: str = f"DNS:{_WORKER},IP:{_NODE_IP}",
    usages: tuple[str, ...] = _GOOD_USAGES,
    username: str = _USER,
    signer: str = "kubernetes.io/kubelet-serving",
    conditions: str = "",
) -> None:
    key = cluster.root / f"{name}.key"
    pem = subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:prime256v1",
            "-nodes",
            "-keyout",
            str(key),
            "-subj",
            subject,
            "-addext",
            f"subjectAltName={sans}",
        ],
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout
    (cluster.root / f"{name}.request").write_text(base64.b64encode(pem).decode(), encoding="utf-8")
    (cluster.root / f"{name}.usages").write_text(
        "".join(f"{u}\n" for u in usages), encoding="utf-8"
    )
    with (cluster.root / "list").open("a", encoding="utf-8") as listing:
        listing.write(f"{name}\t{signer}\t{username}\t{conditions}\n")


def _approve(*, cluster: _Cluster) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_APPROVE), _HOST],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{cluster.bin_dir}:/usr/bin:/bin:/opt/homebrew/bin",
            "HOMELAB_WORKER_HOSTS_DIR": str(_mock_hosts(cluster.root, _HOST)),
            "TAILNET_DOMAIN": _DOMAIN,
        },
        check=False,
        timeout=60,
    )


def _approved(*, cluster: _Cluster) -> list[str]:
    if not cluster.approved.exists():
        return []
    return cluster.approved.read_text(encoding="utf-8").splitlines()


def test_a_matching_serving_csr_is_approved(cluster: _Cluster) -> None:
    _add_csr(
        cluster=cluster,
        name="csr-good",
        sans=f"DNS:{_WORKER},DNS:{_WORKER}.{_DOMAIN},IP:{_NODE_IP}",
    )
    result = _approve(cluster=cluster)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _approved(cluster=cluster) == ["csr-good"]


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"sans": f"DNS:{_WORKER},IP:10.0.0.9"}, "IP SAN 10.0.0.9 is not an InternalIP"),
        (
            {"sans": f"DNS:{_WORKER},DNS:kubernetes.default,IP:{_NODE_IP}"},
            "DNS SAN kubernetes.default",
        ),
        ({"sans": f"DNS:other-node,IP:{_NODE_IP}"}, f"DNS SANs do not include {_WORKER}"),
        ({"sans": f"DNS:{_WORKER}"}, "no IP SAN"),
        ({"usages": ("digital signature", "client auth")}, "usages do not include server auth"),
        ({"usages": (*_GOOD_USAGES, "client auth")}, "usage 'client auth' is not allowed"),
        ({"subject": "/O=system:masters/CN=" + _USER}, "is not in O=system:nodes"),
        ({"subject": "/O=system:nodes/CN=system:node:other-node"}, f"is not CN={_USER}"),
    ],
)
def test_a_serving_csr_that_does_not_match_the_worker_is_refused_by_name(
    cluster: _Cluster, override: dict[str, object], reason: str
) -> None:
    _add_csr(cluster=cluster, name="csr-bad", **override)  # type: ignore[arg-type]
    result = _approve(cluster=cluster)
    assert result.returncode != 0
    assert "REFUSED csr-bad: " in result.stderr
    assert reason in result.stderr
    assert _approved(cluster=cluster) == []


def test_csrs_from_another_requester_another_signer_or_already_decided_are_left_alone(
    cluster: _Cluster,
) -> None:
    _add_csr(cluster=cluster, name="csr-other-node", username="system:node:peer-node-1")
    _add_csr(
        cluster=cluster, name="csr-client", signer="kubernetes.io/kube-apiserver-client-kubelet"
    )
    _add_csr(cluster=cluster, name="csr-decided", conditions="Approved")
    result = _approve(cluster=cluster)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no pending kubelet-serving CSR" in result.stdout
    assert _approved(cluster=cluster) == []


def test_no_csr_is_approved_for_a_worker_whose_node_is_not_registered(cluster: _Cluster) -> None:
    (cluster.root / "node-ips").unlink()
    _add_csr(cluster=cluster, name="csr-good")
    result = _approve(cluster=cluster)
    assert result.returncode != 0
    assert "is not registered" in result.stderr
    assert _approved(cluster=cluster) == []


def test_a_failed_node_lookup_is_reported_as_the_error_not_as_an_absent_node(
    cluster: _Cluster,
) -> None:
    (cluster.root / "lookup-error").write_text(
        "error: error parsing jsonpath: unclosed action\n", encoding="utf-8"
    )
    _add_csr(cluster=cluster, name="csr-good")
    result = _approve(cluster=cluster)
    assert result.returncode != 0
    assert "is not registered" not in result.stderr
    assert "error parsing jsonpath" in result.stderr
    assert _approved(cluster=cluster) == []
