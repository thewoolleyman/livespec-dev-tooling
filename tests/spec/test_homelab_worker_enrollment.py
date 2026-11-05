"""Enrollment of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

"The worker MUST join the fleet through standard Kubernetes TLS bootstrap with a short-lived,
narrowly scoped bootstrap credential ... Enrollment material MUST NOT be stored in an image
layer, in Git, in a command argument or in a logged or inspect-visible environment variable."

These read `homelab-worker/enrollment/rbac.yaml` and run
`homelab-worker/enrollment/mint-bootstrap-token.sh` under the system `/bin/bash` against a
stub `kubectl` that records its arguments and its stdin:

- the bootstrap group may only create its CSRs and have its kubelet client CSR auto-approved,
  and renewal is bound per declared worker, never to every node;
- the minted token authenticates only in that group and expires, reaches `kubectl` on stdin
  rather than in an argument, and lands only in a mode-0600 kubeconfig pinning the API server
  and its CA;
- an undeclared host, a non-https server or an existing output file is refused before any
  cluster change.
"""

from __future__ import annotations

import re
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

__all__: list[str] = []

_ENROLLMENT = Path(__file__).resolve().parents[2] / "homelab-worker" / "enrollment"
_MINT = _ENROLLMENT / "mint-bootstrap-token.sh"
_GROUP = "system:bootstrappers:homelab-worker"


@dataclass(frozen=True, kw_only=True)
class _Operator:
    bin_dir: Path
    argv_log: Path
    stdin_log: Path
    ca: Path
    out: Path


@pytest.fixture
def operator(tmp_path: Path) -> _Operator:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    made = _Operator(
        bin_dir=bin_dir,
        argv_log=tmp_path / "kubectl-argv.log",
        stdin_log=tmp_path / "kubectl-stdin.log",
        ca=tmp_path / "server-ca.crt",
        out=tmp_path / "out" / "bootstrap-kubeconfig",
    )
    made.out.parent.mkdir()
    made.ca.write_text(
        "-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n", encoding="utf-8"
    )
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(
        f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{made.argv_log}"\ncat >> "{made.stdin_log}"\n',
        encoding="utf-8",
    )
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IXUSR)
    return made


def _mint(
    *, operator: _Operator, host: str = "macbook-m4-max", server: str = "https://127.0.0.1:6550"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_MINT), host, server, str(operator.ca), str(operator.out)],
        capture_output=True,
        text=True,
        env={"PATH": f"{operator.bin_dir}:/usr/bin:/bin"},
        check=False,
        timeout=60,
    )


def _docs() -> list[str]:
    return (_ENROLLMENT / "rbac.yaml").read_text(encoding="utf-8").split("\n---\n")


def test_the_bootstrap_group_may_only_request_csrs_and_have_its_client_csr_auto_approved() -> None:
    bound = {}
    for doc in _docs():
        name = re.search(r"^  name: (\S+)$", doc, flags=re.MULTILINE)
        role = re.search(r"^  name: (system:\S+)$", doc.split("roleRef:")[1], flags=re.MULTILINE)
        assert name
        assert role
        bound[name.group(1)] = (role.group(1), doc.split("subjects:")[1])
    assert bound["homelab-worker-bootstrap"][0] == "system:node-bootstrapper"
    assert bound["homelab-worker-autoapprove-client"][0] == (
        "system:certificates.k8s.io:certificatesigningrequests:nodeclient"
    )
    for binding in ("homelab-worker-bootstrap", "homelab-worker-autoapprove-client"):
        assert f"name: {_GROUP}" in bound[binding][1]
        assert "kind: User" not in bound[binding][1]
    renew_role, renew_subjects = bound["homelab-worker-autorenew-client"]
    assert renew_role.endswith(":selfnodeclient")
    assert "system:nodes" not in renew_subjects
    assert re.findall(r"name: (\S+)", renew_subjects) == [
        "system:node:macbook-m4-max-homelab-worker",
        "system:node:macbook-air-homelab-worker",
    ]
    assert (
        "serving"
        not in (_ENROLLMENT / "rbac.yaml").read_text(encoding="utf-8").split("apiVersion")[1]
    )


def test_a_minted_token_is_short_lived_scoped_and_kept_out_of_arguments_and_output(
    operator: _Operator,
) -> None:
    result = _mint(operator=operator)
    assert result.returncode == 0, result.stdout + result.stderr
    secret = operator.stdin_log.read_text(encoding="utf-8")
    token_id = re.search(r'token-id: "([a-z0-9]{6})"', secret)
    token_secret = re.search(r'token-secret: "([a-z0-9]{16})"', secret)
    expiration = re.search(r'expiration: "([0-9T:-]+Z)"', secret)
    assert token_id
    assert token_secret
    assert expiration
    assert f"name: bootstrap-token-{token_id.group(1)}" in secret
    assert "type: bootstrap.kubernetes.io/token" in secret
    assert f'auth-extra-groups: "{_GROUP}"' in secret
    assert 'usage-bootstrap-authentication: "true"' in secret
    assert "usage-bootstrap-signing" not in secret
    expires = datetime.strptime(expiration.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    minutes = (expires - datetime.now(timezone.utc)).total_seconds() / 60
    assert 55 <= minutes <= 61
    assert operator.argv_log.read_text(encoding="utf-8").splitlines() == ["apply -f -"]
    assert token_secret.group(1) not in result.stdout + result.stderr
    assert token_id.group(1) in result.stdout
    kubeconfig = operator.out.read_text(encoding="utf-8")
    assert f"token: {token_id.group(1)}.{token_secret.group(1)}" in kubeconfig
    assert "server: https://127.0.0.1:6550" in kubeconfig
    assert "certificate-authority-data: " in kubeconfig
    assert stat.S_IMODE(operator.out.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("host", "server", "message"),
    [
        ("macbook-pro", "https://127.0.0.1:6550", "is not declared"),
        ("macbook-m4-max", "http://127.0.0.1:6550", "is not an https:// URL"),
    ],
)
def test_an_undeclared_host_or_plain_http_server_is_refused_before_any_cluster_change(
    operator: _Operator, host: str, server: str, message: str
) -> None:
    result = _mint(operator=operator, host=host, server=server)
    assert result.returncode != 0
    assert message in result.stderr
    assert not operator.argv_log.exists()
    assert not operator.out.exists()


def test_an_existing_bootstrap_kubeconfig_is_never_overwritten(operator: _Operator) -> None:
    operator.out.write_text("kept\n", encoding="utf-8")
    result = _mint(operator=operator)
    assert result.returncode != 0
    assert "refusing to overwrite" in result.stderr
    assert operator.out.read_text(encoding="utf-8") == "kept\n"
    assert not operator.argv_log.exists()
