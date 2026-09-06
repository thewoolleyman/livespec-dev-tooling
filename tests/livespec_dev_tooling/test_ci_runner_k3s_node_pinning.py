"""Two-node preconditions in the `ci-runner/k3s/` converge tree.

The pool is one node today, so four workloads that mount a hostPath on that
node's storage tiers — the sccache redis, the crates proxy, the PyPI files
proxy and the warm-cache CronJob — used to carry no node pin, and the
cache-telemetry endpoint every job pod posts to was the literal cni0 gateway
of node 0. Both are silent-wrong-answer shapes once a second node joins: an
unpinned pod mounts an EMPTY directory and reports Ready, and a pod on node 1
posts spans to an address that does not exist there at all (flannel gives each
node its own /24, so node 1's gateway is 10.42.1.1) — into the emitter's
bounded, fail-soft, deliberately silent timeout.

Neither failure is observable from inside the cluster once it happens, and
neither is reachable on the single-node pool that exists now, so these tests
are the only thing standing between the manifests and the regression. They
read the REAL manifests and scripts, and they RUN each converge script's
`--dry-run` (which is why the dry-run must touch nothing: this suite is not
the node and has no cluster).

Plan: livespec `k3s-on-gmktec-for-vps-usage`, carrier R3.
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
)
_HOOK_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
_PROVISION = _K3S / "provision-k3s.sh"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"

# Each converge script paired with a fragment of the apply its --dry-run must
# print, so "supports the flag" cannot pass on a flag that prints nothing.
_CONVERGE_SCRIPTS = (
    (_PHASE2 / "sccache" / "converge-sccache-redis.sh", "kubectl apply -f"),
    (_PHASE2 / "crates-proxy" / "converge-crates-proxy.sh", "kubectl apply -f"),
    (_PHASE2 / "warm-cache" / "converge-warm-cache.sh", "kubectl apply -f"),
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

# The downward-API declaration and the two endpoints derived from it.
_HOST_IP_FIELD_REF = re.compile(
    r"- name: CI_RUNNER_NODE_HOST_IP\n"
    r" +valueFrom:\n"
    r" +fieldRef:\n"
    r" +fieldPath: status\.hostIP$",
    re.MULTILINE,
)
_DERIVED_ENDPOINT = "value: http://$(CI_RUNNER_NODE_HOST_IP):4319"
_ENDPOINT_VARS = ("CI_CACHE_OTLP_ENDPOINT", "LIVESPEC_SANDBOX_OTEL_ENDPOINT")

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


def test_the_cache_telemetry_endpoint_is_derived_per_node() -> None:
    """Both endpoints come from a `status.hostIP` fieldRef declared before them."""
    text = _read(path=_HOOK_TEMPLATE)
    field_ref = _HOST_IP_FIELD_REF.search(text)
    assert field_ref is not None, (
        "hook-pod-template.yaml must declare CI_RUNNER_NODE_HOST_IP from a "
        "status.hostIP fieldRef"
    )
    for name in _ENDPOINT_VARS:
        declaration = f"- name: {name}\n"
        assert declaration in text, f"hook-pod-template.yaml must set {name}"
        at = text.index(declaration)
        assert text[at:].startswith(f"{declaration}          {_DERIVED_ENDPOINT}\n"), (
            f"{name} must be {_DERIVED_ENDPOINT!r} — a literal address is the "
            "wrong node's, or no node's, from a second node"
        )
        assert field_ref.start() < at, (
            f"CI_RUNNER_NODE_HOST_IP must be declared BEFORE {name}: Kubernetes "
            "expands $(VAR) only against env vars earlier in the same list"
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
