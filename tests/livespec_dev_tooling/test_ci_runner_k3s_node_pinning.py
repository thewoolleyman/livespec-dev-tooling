"""Two-node preconditions in the `ci-runner/k3s/` converge tree.

The pool is one node today, so four workloads that mount a hostPath on that
node's storage tiers — the sccache redis, the crates proxy, the PyPI files
proxy and the warm-cache CronJob — used to carry no node pin, and the
cache-telemetry endpoint every job pod posts to was the literal cni0 gateway
of node 0. Both are silent-wrong-answer shapes once a second node joins: an
unpinned pod mounts an EMPTY directory and reports Ready, and a pod on node 1
posts spans to an address that does not exist there at all (flannel gives each
node its own /24) — into the emitter's bounded, fail-soft, deliberately silent
timeout.

The endpoint's FIRST repair, a `status.hostIP` fieldRef, was silently wrong in
the same shape and on the node that already existed: the node's LAN address is
not where the keyless `otlp/pods` receiver listens, and that receiver's cni0-
only bind IS its access control, so widening it is not available as a fix.
Measured on `poweredge-xubuntu` 2026-09-07: a POST to the cni0 gateway
returned 200 and a POST to the node's InternalIP was refused, for a month, with
no error and no rows. So the endpoint is now derived IN THE POD from the pod's
own default route — which IS its node's cni0 bridge — and the tests below both
pin that shape in the manifest and RUN the derivation.

None of these failures is observable from inside the cluster once it happens,
and one of them was not reachable on the single-node pool that exists now, so
these tests are the only thing standing between the manifests and the
regression. They read the REAL manifests and scripts, they RUN the emitter's
derivation against a stubbed routing table, and they RUN each converge script's
`--dry-run` (which is why the dry-run must touch nothing: this suite is not
the node and has no cluster).

Plan: livespec `k3s-on-gmktec-for-vps-usage`, carriers R3 and R7.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_PHASE2 = _K3S / "phase2"

# The label the hostPath singletons pin to. NOT `k3s-role=arc-runner-host`:
# that is the RUNNER role, which every node joining the pool carries — including
# the second node the pin exists to exclude.
_TIER_CARRIER_KEY = "ci-runner.io/cache-tier-carrier"
_TIER_CARRIER_LABEL = f"{_TIER_CARRIER_KEY}=true"

_HOSTPATH_SINGLETONS = (
    _PHASE2 / "sccache" / "sccache-redis.yaml",
    _PHASE2 / "crates-proxy" / "crates-proxy.yaml",
    _PHASE2 / "warm-cache" / "pypi-proxy" / "pypi-proxy.yaml",
    _PHASE2 / "warm-cache" / "warm-cache-cronjob.yaml",
    _PHASE2 / "warm-cache" / "registry-mirror" / "registry-mirror.yaml",
)
_HOOK_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
_EMITTER = _PHASE2 / "cache-telemetry" / "ci-cache-span.sh"
_PROVISION = _K3S / "provision-k3s.sh"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"

# Each converge script paired with a fragment of the apply its --dry-run must
# print, so "supports the flag" cannot pass on a flag that prints nothing.
_CONVERGE_SCRIPTS = (
    (_PHASE2 / "sccache" / "converge-sccache-redis.sh", "kubectl apply -f"),
    (_PHASE2 / "crates-proxy" / "converge-crates-proxy.sh", "kubectl apply -f"),
    (_PHASE2 / "warm-cache" / "converge-warm-cache.sh", "kubectl apply -f"),
    (
        _PHASE2 / "warm-cache" / "registry-mirror" / "converge-registry-mirror.sh",
        "kubectl apply -f",
    ),
    (
        _PHASE2 / "arc" / "converge-hook-pod-template.sh",
        "kubectl create configmap arc-hook-pod-template",
    ),
)

# The node-0 CNI gateway the telemetry endpoint was written as until carrier R3.
_RETIRED_ENDPOINT_HOST = b"10.42.0.1"

# `nodeSelector:` at any indent, immediately followed by the tier-carrier key
# indented one level further — i.e. the key is IN that selector, not merely
# somewhere in the file.
_PINNED = re.compile(
    r"^(?P<indent> +)nodeSelector:\n(?P=indent)  " + re.escape(_TIER_CARRIER_KEY) + r': "true"$',
    re.MULTILINE,
)

# The in-pod derivation: postStart publishes the endpoint, the emitter reads it
# back, and the cargo shim — which can read nothing but an env var — reaches it
# through a hosts alias whose NAME is the same on every node.
_PUBLISH_CALL = "/opt/ci-runner/bin/ci-cache-span publish-endpoint"
_OTLP_ALIAS = "otlp-collector.ci-runner.internal"
_SANDBOX_ENDPOINT = (
    f"- name: LIVESPEC_SANDBOX_OTEL_ENDPOINT\n          value: http://{_OTLP_ALIAS}:4319\n"
)
# The address that is NOT the pod's, and the declaration that resolved to it.
_RETIRED_HOST_IP_TOKENS = ("status.hostIP", "CI_RUNNER_NODE_HOST_IP")
# poweredge-xubuntu's cni0 gateway, and therefore what a pod's default route
# reads there. A LITERAL here and a DERIVATION in the pool: the acceptance
# criterion names the measured address, and this suite is the only place that
# can hold the pool to it without a cluster.
_STUB_GATEWAY = "10.42.0.1"

# A whole nodeSelector block: its keys are the lines indented DEEPER than the
# `nodeSelector:` line itself, which is what stops the match running on into
# the sibling fields of the pod spec.
_SELECTOR_BLOCK = re.compile(
    r"^(?P<indent> +)nodeSelector:\n(?P<keys>(?:(?P=indent) +\S+:.*\n)+)", re.MULTILINE
)


def _read(*, path: Path) -> str:
    """The file's text, with a failure message naming it when it is missing."""
    assert path.is_file(), f"expected {path} to exist"
    return path.read_text(encoding="utf-8")


def _dry_run(*, script: Path) -> subprocess.CompletedProcess[str]:
    """Run `<script> --dry-run` with no KUBECONFIG and no cluster in reach."""
    return subprocess.run(
        ["bash", str(script), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        cwd=_REPO_ROOT,
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
    )


def test_every_hostpath_singleton_pins_to_the_cache_tier_carrier_label() -> None:
    """All four workloads select the node whose disks their hostPaths are on."""
    for manifest in _HOSTPATH_SINGLETONS:
        text = _read(path=manifest)
        pins = _PINNED.findall(text)
        assert len(pins) == 1, (
            f"{manifest.name} must carry exactly one nodeSelector on "
            f"{_TIER_CARRIER_KEY}; found {len(pins)}"
        )
        assert "NODE PINNING" in text, (
            f"{manifest.name} must document the pin choice in its header "
            "(a bare selector does not say why it is not k3s-role)"
        )


def test_the_pin_is_not_the_runner_role_label() -> None:
    """No singleton pins to `k3s-role`, which a second pool node also carries."""
    for manifest in _HOSTPATH_SINGLETONS:
        blocks = [m.group("keys") for m in _SELECTOR_BLOCK.finditer(_read(path=manifest))]
        keys = [line.split(":")[0].strip() for block in blocks for line in block.splitlines()]
        assert keys == [_TIER_CARRIER_KEY], (
            f"{manifest.name} selects {keys}; the pin must be exactly "
            f"[{_TIER_CARRIER_KEY}] — k3s-role=arc-runner-host is the runner "
            "role and does not distinguish the tier carrier"
        )


def test_provision_and_the_boot_converge_set_the_label_idempotently() -> None:
    """`kubectl label --overwrite` — the form a re-run patches instead of failing."""
    for script in (_PROVISION, _BOOT_CONVERGE):
        text = _read(path=script)
        assert _TIER_CARRIER_LABEL in text, f"{script.name} must set {_TIER_CARRIER_LABEL}"
        assert "--overwrite" in text, (
            f"{script.name} must set the label with --overwrite; a bare "
            "`kubectl label` fails on the second run and is not idempotent"
        )
        assert "findmnt" in text, (
            f"{script.name} must condition the label on the ci-cache tier being "
            "mounted here, or a second node running it would label itself too"
        )


def test_the_cache_telemetry_endpoint_is_derived_in_the_pod_not_from_the_host_ip() -> None:
    """No `status.hostIP` anywhere; postStart publishes, and the shim gets a name."""
    text = _read(path=_HOOK_TEMPLATE)
    # Comments are out of scope for the same reason markdown is below: the
    # design record has to be able to name what it replaced, and a comment
    # configures nothing.
    declared = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for token in _RETIRED_HOST_IP_TOKENS:
        assert token not in declared, (
            f"hook-pod-template.yaml still carries {token} — status.hostIP is "
            "the node's LAN address, which the keyless otlp/pods receiver "
            "deliberately does not bind, so every span posted there is refused"
        )
    assert "- name: CI_CACHE_OTLP_ENDPOINT\n" not in declared, (
        "CI_CACHE_OTLP_ENDPOINT must NOT be set in the manifest: no value "
        "expressible here is correct, and leaving it unset is what makes an "
        "underivable endpoint a skip rather than a POST at a refused address"
    )
    assert _PUBLISH_CALL in text, (
        f"postStart must call {_PUBLISH_CALL!r} — the derivation from the "
        "pod's own default route is the endpoint's only source"
    )
    assert _SANDBOX_ENDPOINT in text, (
        "LIVESPEC_SANDBOX_OTEL_ENDPOINT must name the hosts alias "
        f"{_OTLP_ALIAS}: the cargo shim is baked into a pinned image and reads "
        "an env var and nothing else, so the value is per-node by NAME"
    )


def _stub(*, bin_dir: Path, name: str, body: str) -> None:
    """Write an executable `name` stub into `bin_dir`, first on the emitter's PATH."""
    path = bin_dir / name
    _ = path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _emit(
    *, args: list[str], bin_dir: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run the REAL emitter with `bin_dir` shadowing `ip` (and `python3`) on PATH."""
    return subprocess.run(
        ["sh", str(_EMITTER), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=_REPO_ROOT,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": "/nonexistent", **env},
    )


def _derivation_fixture(*, tmp_path: Path, ip_body: str, route_table: str) -> dict[str, str]:
    """A stubbed pod: a routing table, a hosts file, a state dir, a fake python3.

    The `python3` stub is the SKIP oracle: the emitter reaches python only when
    it has an endpoint to post to, so the sentinel's absence is proof that
    emission was skipped rather than attempted and swallowed by the fail-soft
    contract (which would look identical from the exit code alone).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir=bin_dir, name="ip", body=ip_body)
    _stub(
        bin_dir=bin_dir,
        name="python3",
        body='printf "%s" "${CI_CACHE_OTLP_ENDPOINT:-}" > "${EMIT_SENTINEL}"',
    )
    _ = (tmp_path / "route").write_text(route_table, encoding="utf-8")
    _ = (tmp_path / "hosts").write_text("127.0.0.1 localhost\n", encoding="utf-8")
    return {
        "CI_CACHE_STATE_DIR": str(tmp_path / "state"),
        "CI_CACHE_HOSTS_FILE": str(tmp_path / "hosts"),
        "CI_CACHE_PROC_NET_ROUTE": str(tmp_path / "route"),
        "EMIT_SENTINEL": str(tmp_path / "emitted"),
    }


def test_the_endpoint_is_derived_from_the_pods_own_default_gateway(*, tmp_path: Path) -> None:
    """`publish-endpoint` reads the default route and both consumers get it."""
    env = _derivation_fixture(
        tmp_path=tmp_path,
        ip_body=f'echo "default via {_STUB_GATEWAY} dev eth0"',
        route_table="Iface\tDestination\tGateway\n",
    )
    bin_dir = tmp_path / "bin"
    published = _emit(args=["publish-endpoint"], bin_dir=bin_dir, env=env)
    assert published.returncode == 0, published.stderr
    expected = f"http://{_STUB_GATEWAY}:4319"
    assert published.stdout.strip() == expected
    assert (tmp_path / "state" / "otlp_endpoint").read_text(encoding="utf-8") == expected
    assert f"{_STUB_GATEWAY} {_OTLP_ALIAS}\n" in (tmp_path / "hosts").read_text(encoding="utf-8"), (
        "the hosts alias is how the baked cargo shim — which reads an env var "
        "and nothing else — reaches its own node's collector"
    )
    # And the emitter posts THERE, with no endpoint in its environment at all.
    ended = _emit(args=["job-end"], bin_dir=bin_dir, env=env)
    assert ended.returncode == 0, ended.stderr
    assert (tmp_path / "emitted").read_text(encoding="utf-8") == expected


def test_emission_is_skipped_not_failed_when_there_is_no_default_route(*, tmp_path: Path) -> None:
    """No route to derive from: nothing published, nothing posted, exit 0."""
    env = _derivation_fixture(
        tmp_path=tmp_path,
        ip_body="exit 0",
        route_table="Iface\tDestination\tGateway\neth0\t0A2A0000\t00000000\n",
    )
    bin_dir = tmp_path / "bin"
    published = _emit(args=["publish-endpoint"], bin_dir=bin_dir, env=env)
    assert published.returncode == 0, published.stderr
    assert published.stdout == ""
    assert not (tmp_path / "state" / "otlp_endpoint").exists()
    assert _OTLP_ALIAS not in (tmp_path / "hosts").read_text(encoding="utf-8")
    ended = _emit(args=["job-end"], bin_dir=bin_dir, env=env)
    assert ended.returncode == 0, ended.stderr
    assert not (tmp_path / "emitted").exists(), (
        "the emitter must SKIP when no endpoint was derived, not POST into a "
        "refused address and swallow the failure — the silent-loss shape this "
        "whole derivation exists to end"
    )


def test_no_manifest_or_script_under_ci_runner_carries_the_retired_gateway() -> None:
    """The literal is unfixable by editing it; its absence is the fix holding.

    Scoped to what is APPLIED or EXECUTED. Markdown is deliberately out of
    scope: the design record has to be able to name the address it replaced,
    and prose configures nothing.
    """
    offenders = [
        path.relative_to(_REPO_ROOT)
        for path in sorted((_REPO_ROOT / "ci-runner").rglob("*"))
        if path.is_file() and path.suffix != ".md" and _RETIRED_ENDPOINT_HOST in path.read_bytes()
    ]
    assert offenders == [], (
        f"{offenders} still carry {_RETIRED_ENDPOINT_HOST.decode()} — the cni0 "
        "gateway of node 0, which is not an address at all on node 1"
    )


def test_every_converge_script_dry_run_prints_its_apply_and_touches_nothing() -> None:
    """--dry-run exits 0 with no kubectl, no KUBECONFIG and no root."""
    for script, expected_apply in _CONVERGE_SCRIPTS:
        done = _dry_run(script=script)
        assert done.returncode == 0, (
            f"{script.name} --dry-run exited {done.returncode}\n"
            f"stdout:\n{done.stdout}\nstderr:\n{done.stderr}"
        )
        assert f"would run: {expected_apply}" in done.stdout, (
            f"{script.name} --dry-run must PRINT the apply it would run; got:\n" f"{done.stdout}"
        )
        assert (
            "DRY RUN: nothing was applied." in done.stdout
        ), f"{script.name} --dry-run must say plainly that it applied nothing"
