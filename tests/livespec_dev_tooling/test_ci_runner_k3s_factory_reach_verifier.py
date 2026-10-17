"""`verify-factory-reach.sh` renders a node-pinned factory Job and names what it probes.

WHY THIS FILE EXISTS (work-item livespec-dev-tooling-sszvvw, livespec plan
`factory-worker-nodes-gitops`, epic `livespec-sqvj7p`, plan assertion 7). The
plan needs a REPEATABLE proof that a `factory`-namespace pod on a named node
reaches the telemetry receiver, and pulls the sandbox image.
`ci-runner/k3s/phase2/factory/DERIVATION.md` "The tailnet" defers exactly that
question here by name. A proof nobody can re-run is a measurement, not a check,
so the artifact is committed beside the manifests it probes from.

THE BEADS DOLT TENANT IS NO LONGER ONE OF THOSE ENDPOINTS (work-item
livespec-dev-tooling-5iep7h, freeze ruling R78 of 2026-10-16, which amended plan
assertion 7). DERIVATION.md had recorded that an hp Docker sandbox could NOT
reach the tenant on 2026-10-13 and left proving the reach PER NODE here; the
committed run of 2026-10-16 (gate `20261016T191450Z-326561`) then found every
covered node refused at `beads-dolt-tenant 100.89.189.118:3307` while its pod
RAN — so the image pulled, and because the probe is fail-fast the telemetry
receiver was never reached at all. R78 ruled that ledger access stays HOST-SIDE
with the dispatcher, so no factory pod is given a route to the tenant. A probe
kept for an endpoint nothing is meant to reach fails every run forever AND hides
every endpoint behind it, which is the measurement that run actually took.

WHY A PYTEST FILE AND NOT ONLY A SHELL SUITE. The sibling convention in that
directory is a `*-exit-tests.sh` beside each script, but nothing in `just check`
runs those suites, so a regression in one is a regression nobody is told about —
the same reasoning `test_ci_runner_k3s_factory_node_label.py` records. These
assertions ride the gated suite instead, over the same `--dry-run` an operator
reads and over the same probe program the pod runs.

HOW IT STAYS OFF EVERY CLUSTER. The dry-run cases run on a scratch PATH of
TRIPWIRES for `kubectl` and its neighbours and assert the tripwire log stayed
empty, so a dry run that contacted a cluster fails here rather than mutating
one. The three cases that exercise the script's REPORTING run against a FAKE
`kubectl` that answers from a canned Job log — the host-captured leg of the
Definition of Done is the live cluster's to answer, and faking it here would
claim an observation this tree cannot make.

WHY THE PROBE IS A SEPARATE COMMITTED SCRIPT. The reachability verdict is the
whole point of the check, and a verdict embedded only as a YAML string is a
program no test can run. `factory-reach-probe.sh` is therefore committed on its
own, exercised here against REAL loopback sockets, and asserted to be embedded
in the rendered Job VERBATIM — so the bytes these tests run are the bytes the
pod runs.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
from collections.abc import Iterator
from itertools import takewhile
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "factory"
_SCRIPT = _FACTORY_DIR / "verify-factory-reach.sh"
_PROBE = _FACTORY_DIR / "factory-reach-probe.sh"
_ENDPOINTS = _FACTORY_DIR / "factory-reach-endpoints.env"
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

# This repository's own committed Dolt connection, which is where the endpoint
# R78 dropped took its port from. READ rather than spelled: the assertion is
# that no committed endpoint names the tenant, and a literal here would still
# agree with an entry that moved the tenant to the port `.beads/config.yaml`
# actually commits.
_BEADS_CONFIG = _REPO_ROOT / ".beads" / "config.yaml"

# The endpoint R78 left in the set, and the ruling that left it. The file has to
# record WHY the other one went, because the next reader's obvious repair for a
# one-endpoint probe set is to put the tenant back.
_TELEMETRY_RECEIVER = "telemetry-receiver"
_RULING = "R78"

# The identity and the bounds `./factory-namespace.yaml` and
# `./factory-rbac.yaml` declare. Spelled here rather than read back out of them
# because the whole assertion is that the rendered Job lands INSIDE them: a
# manifest that read its own namespace from the same file would agree with any
# rename and prove nothing about where the pod runs.
_NAMESPACE = "factory"
_SERVICE_ACCOUNT = "sandbox-launcher"
_HOSTNAME_LABEL = "kubernetes.io/hostname"
_TOLERATION_KEY = "node-role/ci"

# The two nodes the Definition of Done names. hp carries the
# `node-role/ci=factory:NoSchedule` taint its committed profile declares;
# gmktec carries none, and the toleration is asserted on BOTH renders anyway —
# a toleration is inert on an untainted node, and one render shape for every
# node is what keeps a fourth node from needing a fourth code path.
_HP = "hp-xubuntu"
_GMKTEC = "gmktec-xubuntu"

# The column the embedded probe's block scalar starts at.
_BLOCK_INDENT = 14

# What a dry run must not reach for. `kubectl` is the one that matters; the
# others are its neighbours in this tree's scripts, so a future step that
# shells out to one is caught by the same log.
_TRIPWIRE_TOOLS = ("kubectl", "helm", "k3s", "curl")

_CONTAINER_IMAGE = re.compile(r"^\s*image:\s*(?P<image>\S+)\s*$")


def _expected_image() -> str:
    """The ONE container image this repository's own CI workflow declares.

    The check renders the sandbox image the fleet currently pins, and that pin
    moves with every release — so it is READ from the committed workflow rather
    than spelled anywhere, exactly as `../gates/render-gate-job.sh` reads it.
    A constant here would assert the renderer agrees with this file instead of
    with the pin.
    """
    lines = _CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
    images: set[str] = set()
    for index, line in enumerate(lines[:-1]):
        match = _CONTAINER_IMAGE.match(lines[index + 1])
        if line.strip() == "container:" and match is not None:
            images.add(match["image"])
    assert len(images) == 1, (
        f"{_CI_WORKFLOW.relative_to(_REPO_ROOT)} must declare exactly one container "
        f"image for this reader to assert against; found {sorted(images)}"
    )
    return images.pop()


def _committed_endpoints() -> list[str]:
    """Every `NAME=HOST:PORT` entry of the committed endpoint configuration."""
    assert _ENDPOINTS.is_file(), (
        f"{_ENDPOINTS.relative_to(_REPO_ROOT)} must be committed: the work-item requires "
        f"the endpoints to be arguments or committed configuration and never memorised, "
        f"so an endpoint literal in the script body is the defect this file forbids"
    )
    entries = [
        line.strip()
        for line in _ENDPOINTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert entries, f"{_ENDPOINTS.relative_to(_REPO_ROOT)} must name at least one endpoint"
    return entries


def _committed_endpoint_targets() -> dict[str, str]:
    """The committed endpoint configuration as `NAME -> HOST:PORT`."""
    return {entry.split("=", 1)[0]: entry.split("=", 1)[1] for entry in _committed_endpoints()}


def _beads_tenant_port() -> str:
    """The Dolt port this repository's `.beads/config.yaml` commits for its tenant."""
    ports = re.findall(
        r"^dolt\.server-port:\s*(\d+)\s*$",
        _BEADS_CONFIG.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert len(ports) == 1, (
        f"{_BEADS_CONFIG.relative_to(_REPO_ROOT)} must commit exactly one "
        f"`dolt.server-port` for this reader to assert against; found {ports}"
    )
    return ports[0]


def _write_executable(*, path: Path, lines: list[str]) -> None:
    """One scratch `/bin/sh` stand-in, written and made executable."""
    _ = path.write_text("".join(f"{line}\n" for line in ["#!/bin/sh", *lines]), encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def tripwire_path(*, tmp_path: Path) -> tuple[str, Path]:
    """A PATH whose cluster-reaching tools append to a log instead of running."""
    bin_dir = tmp_path / "tripwirebin"
    bin_dir.mkdir()
    log = tmp_path / "tripwire.log"
    for tool in _TRIPWIRE_TOOLS:
        _write_executable(
            path=bin_dir / tool, lines=[f'printf "{tool} %s\\n" "$*" >> "{log}"', "exit 0"]
        )
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}", log


@pytest.fixture
def fake_kubectl(*, tmp_path: Path) -> tuple[str, Path]:
    """A PATH whose `kubectl` answers the four verbs the check runs, from fixtures.

    `apply` consumes the manifest on stdin and succeeds; `wait` exits
    `FACTORY_REACH_FAKE_WAIT_RC`; `get` prints
    `FACTORY_REACH_FAKE_WAITING_REASON` (the pod's waiting reason, which is how
    an image-pull failure is told apart from a probe that ran and refused); and
    `logs` prints the canned Job log whose path this fixture returns.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    logs = tmp_path / "job.log"
    _write_executable(
        path=bin_dir / "kubectl",
        lines=[
            'case "$1" in',
            "  apply) cat > /dev/null; exit 0 ;;",
            '  logs) cat "$FACTORY_REACH_FAKE_LOGS"; exit 0 ;;',
            "  get) printf '%s' \"${FACTORY_REACH_FAKE_WAITING_REASON:-}\"; exit 0 ;;",
            '  wait) exit "${FACTORY_REACH_FAKE_WAIT_RC:-0}" ;;',
            "esac",
            "exit 0",
        ],
    )
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}", logs


@pytest.fixture
def listening_port() -> Iterator[int]:
    """A loopback port with a real listener behind it for the whole test."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        yield int(sock.getsockname()[1])


def _write_job_log(*, logs: Path, lines: list[str]) -> None:
    """A canned Job log for the fake `kubectl logs` to print, one line per entry."""
    _ = logs.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def _closed_port() -> int:
    """A loopback port with nothing behind it: a bound socket's port, released."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(*, argv: list[str], path: str, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    """One script run on a scratch PATH, returning its code and merged output."""
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "PATH": path, **(extra_env or {})},
    )
    return completed.returncode, completed.stdout + completed.stderr


def _dry_run(*, node: str, tripwire: tuple[str, Path]) -> str:
    """`verify-factory-reach.sh --dry-run --node <node>`, which contacts nothing."""
    code, output = _run(argv=["bash", str(_SCRIPT), "--dry-run", "--node", node], path=tripwire[0])
    assert code == 0, (
        f"`verify-factory-reach.sh --dry-run --node {node}` must exit 0 and print the "
        f"manifest it would submit — a check an operator cannot read before running is "
        f"one they cannot trust:\n{output}"
    )
    return output


def _assert_job_shape(*, manifest: str, node: str) -> None:
    """The Job shape the Definition of Done names, for one node."""
    for required in (
        "kind: Job",
        f"namespace: {_NAMESPACE}",
        f"serviceAccountName: {_SERVICE_ACCOUNT}",
        "nodeSelector:",
        f"{_HOSTNAME_LABEL}: {node}",
        f"key: {_TOLERATION_KEY}",
        "effect: NoSchedule",
        f"image: {_expected_image()}",
    ):
        assert required in manifest, (
            f"the --node {node} manifest must carry `{required}`: a Job that is not pinned "
            f"to the node, cannot tolerate its taint, runs under another identity or runs "
            f"another image proves nothing about THAT node's reach;\nmanifest={manifest}"
        )
    for entry in _committed_endpoints():
        assert entry in manifest, (
            f"the --node {node} manifest must NAME the endpoint `{entry}` it will probe: "
            f"an operator reading the dry run has to see what is about to be reached for;"
            f"\nmanifest={manifest}"
        )


def _embedded_probe(*, manifest: str) -> str:
    """The probe program the rendered Job carries, dedented out of its block scalar."""
    lines = manifest.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == "- |"]
    assert len(starts) == 1, (
        f"the manifest must carry exactly one block scalar (`- |`) holding the probe "
        f"program; found {len(starts)}, so this reader cannot locate it"
    )
    body = takewhile(
        lambda line: not line.strip() or line.startswith(" " * _BLOCK_INDENT),
        lines[starts[0] + 1 :],
    )
    return "".join(f"{line[_BLOCK_INDENT:]}\n" for line in body)


# --- the endpoint set itself (livespec-dev-tooling-5iep7h, ruling R78) -------


def test_the_committed_endpoints_drop_the_beads_tenant_and_keep_the_telemetry_receiver() -> None:
    """R78's endpoint set: the telemetry receiver, and no route to the ledger.

    Ledger access stays HOST-SIDE with the dispatcher, which reaches the tenant
    through the `with-livespec-env.sh` credential wrapper, and the tenant
    password never enters a sandbox — so a factory pod is given no route to it.
    A probe for an endpoint nothing is meant to reach does not merely fail: the
    probe is fail-fast, so it HIDES every endpoint behind it, and the committed
    run of 2026-10-16 reported exactly that — three nodes refused at the tenant
    with the telemetry receiver never reached.

    Asserted over the NAMES and the TARGETS both, because the defect this
    forbids has two spellings: the entry coming back under its own name, and the
    tenant coming back under some other name on the port `.beads/config.yaml`
    commits for it.
    """
    targets = _committed_endpoint_targets()
    assert _TELEMETRY_RECEIVER in targets, (
        f"{_ENDPOINTS.relative_to(_REPO_ROOT)} must still name the `{_TELEMETRY_RECEIVER}` "
        f"endpoint: reaching the receiver a dispatch projects into its sandbox is what plan "
        f"assertion 7 still asks a factory pod to prove; names={sorted(targets)}"
    )
    tenant_port = _beads_tenant_port()
    for name, target in targets.items():
        assert "beads" not in name and "dolt" not in name, (
            f"{_ENDPOINTS.relative_to(_REPO_ROOT)} must name NO beads Dolt tenant endpoint; "
            f"`{name}={target}` does. R78 (2026-10-16) ruled that ledger access stays "
            f"host-side with the dispatcher, so no factory pod gets a route to the tenant "
            f"and no probe of one belongs in a check that stops at its first refusal"
        )
        assert not target.endswith(f":{tenant_port}"), (
            f"`{name}={target}` targets the Dolt port `.beads/config.yaml` commits "
            f"({tenant_port}), so it is the tenant endpoint under another name — which R78 "
            f"removed from this set rather than renamed"
        )
    recorded = _ENDPOINTS.read_text(encoding="utf-8")
    assert _RULING in recorded, (
        f"{_ENDPOINTS.relative_to(_REPO_ROOT)} must cite ruling `{_RULING}` where the tenant "
        f"entry used to be: a one-endpoint probe set with no record of why reads like an "
        f"omission, and putting the tenant back is the next reader's obvious repair"
    )
    assert "The tailnet" in recorded, (
        'and ./DERIVATION.md "The tailnet", which derives the egress rule these endpoints '
        "have to sit inside and records the 2026-10-13 reads they came from"
    )


# --- the Definition of Done's first two assertions -------------------------


def test_the_hp_dry_run_prints_a_factory_job_pinned_and_tolerating_hps_taint(
    *, tripwire_path: tuple[str, Path]
) -> None:
    """hp-xubuntu's dry run prints the pinned, tolerating, sandbox-image Job."""
    _assert_job_shape(manifest=_dry_run(node=_HP, tripwire=tripwire_path), node=_HP)


def test_the_gmktec_dry_run_prints_a_factory_job_pinned_and_tolerating_the_ci_taint(
    *, tripwire_path: tuple[str, Path]
) -> None:
    """gmktec-xubuntu's dry run prints the same shape, pinned to gmktec.

    The toleration is asserted here too even though gmktec's committed profile
    carries an EMPTY `NODE_TAINTS`: one render shape for every node is what
    keeps the check from growing a per-node code path, and a toleration for a
    taint a node does not carry changes nothing about where the pod lands.
    """
    _assert_job_shape(manifest=_dry_run(node=_GMKTEC, tripwire=tripwire_path), node=_GMKTEC)


def test_a_dry_run_contacts_no_cluster(*, tripwire_path: tuple[str, Path]) -> None:
    """Neither dry run invokes `kubectl` or any of its neighbours."""
    for node in (_HP, _GMKTEC):
        _ = _dry_run(node=node, tripwire=tripwire_path)
    assert not tripwire_path[1].exists(), (
        f"a --dry-run must print a manifest and reach nothing; the tripwire log recorded "
        f"{tripwire_path[1].read_text(encoding='utf-8')!r}"
    )


def test_the_rendered_job_runs_the_committed_probe_verbatim(
    *, tripwire_path: tuple[str, Path]
) -> None:
    """The Job's embedded program is `factory-reach-probe.sh`, byte for byte.

    This is what ties the probe cases below to the pod: they run the committed
    file, and a rendered Job carrying a DIFFERENT program would make every one
    of them a proof about something the cluster never executes.
    """
    assert _PROBE.is_file(), f"{_PROBE.relative_to(_REPO_ROOT)} must be committed"
    embedded = _embedded_probe(manifest=_dry_run(node=_HP, tripwire=tripwire_path))
    assert embedded == _PROBE.read_text(
        encoding="utf-8"
    ), f"the rendered Job must embed {_PROBE.name} verbatim; embedded={embedded!r}"


# --- the Definition of Done's third assertion ------------------------------


def test_the_probe_stops_at_the_first_unreachable_endpoint(*, listening_port: int) -> None:
    """The probe names the FIRST unreachable endpoint and probes no further."""
    closed = _closed_port()
    code, output = _run(
        argv=[
            "bash",
            str(_PROBE),
            f"{_TELEMETRY_RECEIVER}=127.0.0.1:{listening_port}",
            f"second-endpoint=127.0.0.1:{closed}",
            f"never-probed=127.0.0.1:{closed}",
        ],
        path=os.environ["PATH"],
        extra_env={"FACTORY_REACH_CONNECT_TIMEOUT_SECONDS": "5"},
    )
    assert code != 0, f"a refused endpoint must fail the probe;\n{output}"
    assert f"UNREACHABLE second-endpoint at 127.0.0.1:{closed}" in output, output
    assert "never-probed" not in output, (
        f"the probe must stop at the FIRST unreachable endpoint, so a later one is never "
        f"reported;\n{output}"
    )
    assert "ALL ENDPOINTS REACHED" not in output, output


def test_the_probe_exits_zero_only_when_every_endpoint_is_reachable(*, listening_port: int) -> None:
    """Every endpoint reached exits 0; probing NOTHING is refused rather than green."""
    code, output = _run(
        argv=[
            "bash",
            str(_PROBE),
            f"{_TELEMETRY_RECEIVER}=127.0.0.1:{listening_port}",
            f"second-endpoint=127.0.0.1:{listening_port}",
        ],
        path=os.environ["PATH"],
    )
    assert code == 0, f"every endpoint was reachable, so the probe must exit 0;\n{output}"
    assert "ALL ENDPOINTS REACHED" in output, output

    empty_code, empty_output = _run(argv=["bash", str(_PROBE)], path=os.environ["PATH"])
    assert empty_code != 0, (
        f"a probe handed no endpoints must refuse: reporting success for having reached "
        f"nothing is the one green this check must never print;\n{empty_output}"
    )


def test_the_check_names_the_first_unreachable_endpoint_from_the_job_log(
    *, fake_kubectl: tuple[str, Path]
) -> None:
    """A failed probe makes the check exit non-zero, naming that endpoint."""
    path, logs = fake_kubectl
    _write_job_log(logs=logs, lines=["UNREACHABLE telemetry-receiver at 100.89.189.118:35129"])
    code, output = _run(
        argv=["bash", str(_SCRIPT), "--node", _HP],
        path=path,
        extra_env={"FACTORY_REACH_FAKE_LOGS": str(logs), "FACTORY_REACH_FAKE_WAIT_RC": "1"},
    )
    assert code != 0, f"an unreachable endpoint must fail the check;\n{output}"
    assert "telemetry-receiver at 100.89.189.118:35129" in output, output


def test_the_check_names_the_image_when_the_pull_is_what_failed(
    *, fake_kubectl: tuple[str, Path]
) -> None:
    """An `ImagePullBackOff` pod fails the check naming the image, not an endpoint.

    The pull is not probed by the pod — a kubelet pulls before the container
    exists — so the only evidence of it is the pod's waiting reason. Without
    this arm a pull failure would surface as "no verdict", which reads like a
    broken check rather than an image nobody can fetch.
    """
    path, logs = fake_kubectl
    _write_job_log(logs=logs, lines=[])
    code, output = _run(
        argv=["bash", str(_SCRIPT), "--node", _HP],
        path=path,
        extra_env={
            "FACTORY_REACH_FAKE_LOGS": str(logs),
            "FACTORY_REACH_FAKE_WAIT_RC": "1",
            "FACTORY_REACH_FAKE_WAITING_REASON": "ImagePullBackOff",
        },
    )
    assert code != 0, f"a pod that cannot pull the sandbox image must fail the check;\n{output}"
    assert _expected_image() in output, output
    assert "ImagePullBackOff" in output, output


def test_the_check_exits_zero_when_the_job_log_carries_the_probe_verdict(
    *, fake_kubectl: tuple[str, Path]
) -> None:
    """Exit 0 requires the probe's own all-reached verdict in the Job log.

    Asserted against the VERDICT line rather than against the Job merely
    completing: a container that exited 0 without probing — a changed command,
    a shell that died after its last `reached` line — would otherwise be read
    as a reach this check never observed.
    """
    path, logs = fake_kubectl
    _write_job_log(
        logs=logs,
        lines=[
            "reached telemetry-receiver at 100.89.189.118:35129",
            "ALL ENDPOINTS REACHED",
        ],
    )
    code, output = _run(
        argv=["bash", str(_SCRIPT), "--node", _HP],
        path=path,
        extra_env={"FACTORY_REACH_FAKE_LOGS": str(logs)},
    )
    assert code == 0, f"every endpoint reached and the image pulled, so exit 0;\n{output}"

    _write_job_log(logs=logs, lines=["reached telemetry-receiver at 100.89.189.118:35129"])
    truncated_code, truncated_output = _run(
        argv=["bash", str(_SCRIPT), "--node", _HP],
        path=path,
        extra_env={"FACTORY_REACH_FAKE_LOGS": str(logs)},
    )
    assert truncated_code != 0, (
        f"a Job log with no all-reached verdict must NOT exit 0: silence is not a pass;"
        f"\n{truncated_output}"
    )
