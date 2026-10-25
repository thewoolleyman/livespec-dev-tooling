"""The six node-local timers of the server node's profile, and the roles that install them.

THE QUESTION THIS FILE ANSWERS (work-item livespec-dev-tooling-xcscdz,
Definition of Done). Six systemd timers — the host-silence heartbeat, the
Kueue-webhook endpoint probe, the per-repository pool gauges, the build-cache
gauges and the sandbox-image prune — were installed on poweredge-xubuntu by TWO
HAND-RUN SHELL INSTALLERS and by nothing else. `ansible/ci-pool.yml` is the
node-provisioning stage of the runner-pool node rebuild recipe in
`SPECIFICATION/non-functional-requirements.md`, and the rebuild-from-bare-metal
scenario in `SPECIFICATION/scenarios.md` requires that "the node's storage
layout, base operating system, pinned k3s, and node-local mechanisms MUST reach
the profile's declared state with no step performed by hand". A rebuild
therefore returned a node with no heartbeat — silently, because the drift
report of a playbook that never mentioned the units reported zero changes.

So the units became roles, the installers were deleted, and this file is the
proof. It asserts three things about the committed tree and nothing about a
live host: that each of the five timers is installed by exactly one role, that
every such role is reached ONLY on the cluster's server node, and that each
timer arrives with the service it activates and the script that service runs.

WHY A READER AND NOT AN `ansible-playbook` RUN — and why the reader is text.
`ci-pool.yml` reaches a real cluster, so a test cannot run it; the sibling
`test_ci_pool_factory_only_agent_roles.py` records that reasoning in full. What
CAN be read off-host is the play's own role list and gates, which is what is in
question here. Neither Ansible, Jinja nor a YAML library is importable in this
suite (the package is dependency-free, deliberately), so the play and the roles
are matched as TEXT — and the one gate shape this file accepts is the same
`<fact> == '<literal>'` shape that sibling's vocabulary test pins the play to,
so the two readers cannot disagree about what a gate means.

WHAT IS DERIVED AND WHAT IS STATED. Which role installs a given timer is
DERIVED — the role is found by searching every committed role for the unit
name, so moving a unit between roles is still proven rather than re-described.
The five units, their services, their scripts and the two deleted installers
are STATED, because the Definition of Done states them and because a unit
silently dropped from the set has to fail somewhere.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_PLAY = _ANSIBLE / "ci-pool.yml"
_ROLES = _ANSIBLE / "roles"
_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_CI_RUNNER = _REPO_ROOT / "ci-runner"
_OBSERVABILITY = _CI_RUNNER / "observability"
_PRUNE_DIR = _CI_RUNNER / "k3s" / "phase2" / "warm-cache" / "sandbox-image-prune"
_CI_RUNNER_README = _CI_RUNNER / "README.md"

# The six timers of the Definition of Done, each with the service it activates
# and the committed script that service's ExecStart runs. Stated, because the
# item states them; the ROLE that carries each one is derived below.
_TIMERS: dict[str, tuple[str, Path]] = {
    "ci-runner-heartbeat.timer": (
        "ci-runner-heartbeat.service",
        _OBSERVABILITY / "ci-runner-heartbeat.sh",
    ),
    "ci-kueue-webhook-probe.timer": (
        "ci-kueue-webhook-probe.service",
        _OBSERVABILITY / "ci-kueue-webhook-probe.sh",
    ),
    "ci-pool-attributed-gauges.timer": (
        "ci-pool-attributed-gauges.service",
        _OBSERVABILITY / "ci-pool-attributed-gauges.sh",
    ),
    "ci-k3s-control-plane-telemetry.timer": (
        "ci-k3s-control-plane-telemetry.service",
        _OBSERVABILITY / "ci-k3s-control-plane-telemetry.sh",
    ),
    "ci-cache-gauges.timer": (
        "ci-cache-gauges.service",
        _OBSERVABILITY / "ci-cache-gauges.sh",
    ),
    "prune-sandbox-images.timer": (
        "prune-sandbox-images.service",
        _PRUNE_DIR / "prune-sandbox-images.sh",
    ),
}

# The two hand-run installers the roles replace, and the commit each one is
# recoverable from — the last commit that touched it before the deletion. The
# citation follows the convention `ci-runner/README.md` already uses for the
# retired rootless-podman pool: a deletion records where the bytes went, in the
# tree, so a reader does not have to bisect for them.
_DELETED_INSTALLERS: dict[Path, str] = {
    _OBSERVABILITY / "install-observability.sh": "c13617d0",
    _PRUNE_DIR / "install-sandbox-image-prune.sh": "356e0454",
}

# The gate that means "the cluster's server node", and the only gate this file
# accepts on a role that installs one of the five units.
_SERVER_GATE = "cluster_role == 'server'"

# The claim the `observability/` row of ci-runner/README.md makes about how the
# live unit copies are installed and updated. The phrase is deliberately short
# of the sentence's end: what is asserted is WHICH installer the claim names,
# not the wording it names it in.
_SANCTIONED_WAY = "only sanctioned way to install"
_OBSERVABILITY_ROW = re.compile(r"^\| `observability/` \|.*$", re.MULTILINE)

_ROLE_ENTRY = re.compile(
    r"^    - role: (?P<role>\w+)$(?P<body>(?:\n(?:      .*|))*)",
    re.MULTILINE,
)
_WHEN_LINE = re.compile(r"^      when: (?P<expression>.+)$", re.MULTILINE)
_CI_POOL_BLOCK = re.compile(
    r"^        ci_pool:\n          hosts:\n(?P<body>(?:.*\n)*?)^        \S", re.MULTILINE
)
_INVENTORY_HOST = re.compile(
    r"^            (?P<host>[\w-]+):$(?P<body>(?:\n(?:              .*|))*)",
    re.MULTILINE,
)
_CLUSTER_ROLE = re.compile(r"^              cluster_role: (?P<role>\w+)$", re.MULTILINE)


def _role_gates() -> dict[str, str | None]:
    """Every `roles:` entry of the play, as `role -> gate-or-None`."""
    gates = {
        match["role"]: (found["expression"].strip() if found else None)
        for match in _ROLE_ENTRY.finditer(_PLAY.read_text(encoding="utf-8"))
        for found in [_WHEN_LINE.search(match["body"])]
    }
    assert gates, (
        f"{_PLAY.name} must declare its roles as `    - role: <name>` entries; a role this "
        f"reader cannot find is a converge nothing here proves"
    )
    return gates


def _role_text(*, role: str) -> str:
    """Every committed YAML line of one role, as one searchable body."""
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((_ROLES / role).rglob("*.yml"))
    )


def _installing_role(*, unit: str) -> str:
    """The one committed role that names `unit` — derived, so a move still proves."""
    named = sorted(
        role.name
        for role in _ROLES.iterdir()
        if role.is_dir() and unit in _role_text(role=role.name)
    )
    assert len(named) == 1, (
        f"exactly one role under ansible/roles/ must name {unit}; {named or 'no role'} does. "
        f"Zero means a rebuild by ansible/ci-pool.yml returns a node without it — the silence "
        f"this item exists to close — and two means two roles converge the same unit, so which "
        f"copy wins depends on the play's order rather than on anything declared"
    )
    return named[0]


def _server_hosts() -> list[str]:
    """Every `ci_pool` host the inventory declares a server, so "the server node" is concrete."""
    block = _CI_POOL_BLOCK.search(_INVENTORY.read_text(encoding="utf-8"))
    assert block is not None, (
        f"{_INVENTORY.name} must declare a `ci_pool` group with a `hosts:` mapping — it is what "
        f"ansible/ci-pool.yml targets, and a play with no hosts converges nothing"
    )
    return sorted(
        match["host"]
        for match in _INVENTORY_HOST.finditer(block["body"])
        for role in [_CLUSTER_ROLE.search(match["body"])]
        if role is not None and role["role"] == "server"
    )


def _observability_row() -> str:
    """The `observability/` row of ci-runner/README.md — the page's own answer for the tier."""
    row = _OBSERVABILITY_ROW.search(_CI_RUNNER_README.read_text(encoding="utf-8"))
    assert row is not None, (
        f"{_CI_RUNNER_README.relative_to(_REPO_ROOT)} must keep its `observability/` row in "
        f"the Files table: it is where the tier's units, and how they are installed, are "
        f"described for an operator"
    )
    return row.group()


def test_each_of_the_six_timers_is_installed_by_a_role_the_play_reaches() -> None:
    """The assertion the rebuild recipe needs: no unit is left to a hand-run installer."""
    gates = _role_gates()
    for unit in _TIMERS:
        role = _installing_role(unit=unit)
        assert role in gates, (
            f"ansible/ci-pool.yml must include the role {role}, which installs {unit}; its "
            f"roles are {sorted(gates)}. A role no playbook targets is unreachable by "
            f"`just ansible-apply` and invisible to `just ansible-drift`, which is exactly how "
            f"these units drifted out of a rebuilt node while the drift report stayed clean"
        )


def test_every_role_that_installs_one_is_reached_only_on_the_cluster_server_node() -> None:
    """Three of the five need the admin kubeconfig, and the pool has exactly one server.

    The pool gauges and the prune read the cluster with the k3s ADMIN kubeconfig,
    which only a server holds; the Kueue probe reads a scoped credential only the
    server's converge renders. An agent would install units that fail-closed on
    every tick, which is a red unit reporting nothing about the agent.
    """
    servers = _server_hosts()
    assert len(servers) == 1, (
        f"the inventory's ci_pool group must declare exactly one server for 'the cluster's "
        f"server node' to name a host; it declares {servers}"
    )
    gates = _role_gates()
    for unit in _TIMERS:
        role = _installing_role(unit=unit)
        assert gates[role] == _SERVER_GATE, (
            f"the role {role}, which installs {unit}, must be gated in ansible/ci-pool.yml on "
            f"`{_SERVER_GATE}` so it is reached on {servers[0]} alone; its gate is "
            f"{gates[role]!r}. The gate lives in the ONE play rather than inside the role "
            f"because the rebuild recipe requires one procedure a reader can answer "
            f"'what does this node get' from"
        )


def test_each_timer_arrives_with_the_service_it_activates_and_that_service_script() -> None:
    """A timer without its service is a tick with nothing to run; a service without its
    script is a unit that fails on every tick."""
    for unit, (service, script) in _TIMERS.items():
        role = _installing_role(unit=unit)
        text = _role_text(role=role)
        assert service in text, (
            f"the role {role} installs {unit} but never names {service}, the unit that timer "
            f"activates. A timer whose service is absent fires into nothing, and systemd "
            f"reports that as a failed activation rather than as a missing install"
        )
        assert script.is_file(), (
            f"{script.relative_to(_REPO_ROOT)} must stay committed: it is the ExecStart of "
            f"{service}, and the role installs a COPY of it onto the node"
        )
        assert script.name in text, (
            f"the role {role} installs {unit} and {service} but never names {script.name}, "
            f"the script {service} runs. The installed script is a COPY, so the role that "
            f"carries the unit is the only thing that can keep it in step with the source"
        )


def test_control_plane_and_pool_queue_reads_use_the_scoped_kubeconfig() -> None:
    """Only ClusterQueue reads may use the collector identity in the legacy emitter."""
    control_plane = (_OBSERVABILITY / "ci-k3s-control-plane-telemetry.service").read_text(
        encoding="utf-8"
    )
    assert "Environment=KUBECONFIG=/etc/otel-collector/kubeconfig" in control_plane
    assert "/etc/rancher/k3s/k3s.yaml" not in control_plane

    pool_unit = (_OBSERVABILITY / "ci-pool-attributed-gauges.service").read_text(encoding="utf-8")
    pool_script = (_OBSERVABILITY / "ci-pool-attributed-gauges.sh").read_text(encoding="utf-8")
    assert "Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml" in pool_unit
    assert "Environment=CI_POOL_KUEUE_KUBECONFIG=/etc/otel-collector/kubeconfig" in pool_unit
    assert 'KUBECONFIG="${KUEUE_KUBECONFIG}"' in pool_script
    assert "kc_kueue get clusterqueues" in pool_script


def test_clusterqueue_resource_points_keep_queue_attribution_for_every_flavor(
    tmp_path: Path,
) -> None:
    """Quota and usage points retain queue identity beside their flavor/resource labels."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    payload = tmp_path / "metrics.json"
    kube_log = tmp_path / "kubectl.log"

    def executable(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    executable(
        bin_dir / "kubectl",
        """#!/usr/bin/env bash
printf '%s|%s\\n' "${KUBECONFIG:-}" "$*" >> "$KUBECTL_LOG"
case "$*" in
  *clusterqueues*)
    printf '%s\\n' 'livespec-dev-tooling-cq|default:ci-runner.io/churn-slot=4 spot:cpu=8|default:ci-runner.io/churn-slot=3 spot:cpu=2|1|2'
    ;;
esac
""",
    )
    executable(
        bin_dir / "curl",
        """#!/usr/bin/env bash
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-d" ]; then
    printf '%s' "$2" > "$OTLP_CAPTURE"
    exit 0
  fi
  shift
done
""",
    )

    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "KUBECTL_LOG": str(kube_log),
        "OTLP_CAPTURE": str(payload),
        "KUBECONFIG": "/etc/rancher/k3s/k3s.yaml",
        "CI_POOL_KUEUE_KUBECONFIG": "/etc/otel-collector/kubeconfig",
        "CI_POOL_KUBECTL": "kubectl",
    }
    completed = subprocess.run(
        ["bash", str(_OBSERVABILITY / "ci-pool-attributed-gauges.sh")],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    metrics = {
        metric["name"]: metric["gauge"]["dataPoints"]
        for metric in json.loads(payload.read_text(encoding="utf-8"))["resourceMetrics"][0][
            "scopeMetrics"
        ][0]["metrics"]
    }
    expected = {
        ("default", "ci-runner.io/churn-slot"),
        ("spot", "cpu"),
    }
    for name in (
        "livespec.ci_pool.queue_resource_quota",
        "livespec.ci_pool.queue_resource_usage",
    ):
        observed = set()
        for point in metrics[name]:
            attrs = {
                attribute["key"]: attribute["value"]["stringValue"]
                for attribute in point["attributes"]
            }
            assert attrs["ci.queue"] == "livespec-dev-tooling-cq"
            assert attrs["ci.repository"] == "thewoolleyman/livespec-dev-tooling"
            observed.add((attrs["kueue.flavor"], attrs["k8s.resource"]))
        assert observed == expected

    kube_reads = kube_log.read_text(encoding="utf-8")
    assert "/etc/otel-collector/kubeconfig|" in kube_reads
    assert "/etc/otel-collector/kubeconfig|--request-timeout=15s get clusterqueues" in kube_reads


def test_each_timer_is_armed_by_the_role_that_installs_it() -> None:
    """Installed is not enabled. The host-silence heartbeat has to be FIRING for the
    dead-man trigger to mean anything, so arming belongs to the same role."""
    for unit in _TIMERS:
        role = _installing_role(unit=unit)
        text = _role_text(role=role)
        for armed in ("enabled: true", "state: started"):
            assert armed in text, (
                f"the role {role} must arm {unit} with `{armed}`, not merely write the unit "
                f"file. A node whose timers are installed and not enabled is indistinguishable "
                f"from a node that was never provisioned, because both are silent"
            )


def test_the_two_hand_run_installers_are_gone_and_say_where_they_went() -> None:
    """Deleting them is the point: a surviving installer is a second way to install,
    and the shell way is the one that a rebuild does not perform."""
    roles = sorted({_installing_role(unit=unit) for unit in _TIMERS})
    citations = "\n".join(_role_text(role=role) for role in roles)
    for installer, pre_deletion_commit in _DELETED_INSTALLERS.items():
        relative = installer.relative_to(_REPO_ROOT)
        assert not installer.exists(), (
            f"{relative} must be deleted: it installs units ansible/ci-pool.yml now installs, "
            f"so leaving it is a second source for the live copies — and the one a rebuild by "
            f"the recipe never runs"
        )
        assert pre_deletion_commit in citations, (
            f"the roles that replace {relative} — {roles} — must cite "
            f"{pre_deletion_commit}, the commit it is recoverable from, the way "
            f"ci-runner/README.md cites the rootless-podman pool's. Deleted bytes a reader "
            f"has to bisect for are deleted knowledge"
        )


def test_the_ci_runner_readme_names_the_role_rather_than_the_deleted_installer() -> None:
    """The page an operator reads to learn how the observability units are installed.

    Asserted as WHICH ONE THE CLAIM NAMES, not as the absence of the installer's
    name. The page must still record that the installer existed and where its
    bytes went — that is the convention this same page already uses for the
    retired rootless-podman pool, and a deletion a reader has to bisect for is
    deleted knowledge. So the test reads the sanctioned-way claim itself and
    asks which installer is named closest in front of it.
    """
    relative = _CI_RUNNER_README.relative_to(_REPO_ROOT)
    row = _observability_row()
    assert _SANCTIONED_WAY in row, (
        f"the `observability/` row of {relative} must say what the {_SANCTIONED_WAY!r} the "
        f"live unit copies is. That claim is the whole point of the row for an operator, and "
        f"a row that does not make it leaves a reader to guess between a role and a script"
    )
    claim = row[: row.index(_SANCTIONED_WAY)]
    role = _installing_role(unit="ci-runner-heartbeat.timer")
    assert claim.rfind(role) > claim.rfind("install-observability.sh"), (
        f"the sanctioned-way claim in the `observability/` row of {relative} must name the "
        f"ansible/ci-pool.yml role {role}, not the deleted install-observability.sh. The "
        f"script is gone, so an operator who follows the page to it reaches for a file that "
        f"is not there — while the role is reached by the same "
        f"`just ansible-apply ansible/ci-pool.yml` a node rebuild already runs"
    )
    recorded = sorted(commit for commit in _DELETED_INSTALLERS.values() if commit in row)
    assert recorded, (
        f"and the row must still record the commit the deleted installer is recoverable from "
        f"(one of {sorted(_DELETED_INSTALLERS.values())}), the way this page records the "
        f"rootless-podman pool's b179cef0. A deletion a reader has to bisect for is a "
        f"deletion of the knowledge too"
    )
