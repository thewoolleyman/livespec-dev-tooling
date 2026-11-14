"""Every ci_pool node gets the ghcr pull mirror's node half through the committed apply.

livespec-dev-tooling-e2gv6n, Definition of Done bullet 2: on hp-xubuntu and on
gmktec-xubuntu, containerd resolves ghcr.io pulls through the pool's registry
mirror, as that node's /etc/rancher/k3s/registries.yaml declares. Until this role
nothing committed installed that file: poweredge-xubuntu carried a hand-installed
copy and the two agents none. The role wraps the committed installer,
`warm-cache/registry-mirror/install-registry-mirror.sh`, so the endpoint
derivation and the refusal to overwrite a foreign file stay in one place.

What is RUN here: the committed installer, exactly as the role invokes it (its
`--dry-run` drift read over a profile carrying the two keys the role renders from
each committed ci_pool profile, against a scratch K3S_CONFIG_ROOT), so the
endpoint each node gets and the plan states the role's `changed_when` reads are
measured rather than described. What is READ: the play entry and the role's
tasks, for placement, the drift contract and the absence of any restart. The file
taking effect at a node's next k3s start stays host-captured.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAY = _REPO_ROOT / "ansible" / "ci-pool.yml"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "registry_mirror_node"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_INSTALLER = (
    _REPO_ROOT
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "warm-cache"
    / "registry-mirror"
    / "install-registry-mirror.sh"
)
_PROFILES = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"
_INVENTORY = _REPO_ROOT / "ansible" / "inventory" / "legacy.yml"
# The plan line the role's changed_when reads, in the role's own regex.
_PLAN_STATE = re.compile(r"\(currently: ([a-z-]+)\)")
_MARKER = "# registries.yaml — the NODE-side half of the ghcr pull-through cache"


def _ci_pool_hosts() -> list[str]:
    block = re.search(
        r"^        ci_pool:\n          hosts:\n(?P<body>(?:.*\n)*?)^        \S",
        _INVENTORY.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert block is not None
    return re.findall(r"^            ([\w-]+):$", block["body"], re.MULTILINE)


def _profile_key(*, host: str, key: str) -> str:
    """The role's own read: `regex_findall('^KEY=(.*)$') | first | default('')`."""
    found = re.findall(
        rf"^{key}=(.*)$", (_PROFILES / f"{host}.env").read_text(encoding="utf-8"), re.MULTILINE
    )
    return found[0] if found else ""


def _plan(*, tmp_path: Path, host: str) -> subprocess.CompletedProcess[str]:
    """The installer's --dry-run, invoked as the role invokes it, for one host."""
    profile = tmp_path / f"{host}.profile.env"
    profile.write_text(
        f"CLUSTER_ROLE={_profile_key(host=host, key='CLUSTER_ROLE')}\n"
        f"CLUSTER_JOIN_ADDRESS={_profile_key(host=host, key='CLUSTER_JOIN_ADDRESS')}\n",
        encoding="utf-8",
    )
    config_root = tmp_path / f"{host}-k3s"
    config_root.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(_INSTALLER), "--dry-run", str(profile)],
        env=os.environ | {"K3S_CONFIG_ROOT": str(config_root)},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _state(plan: subprocess.CompletedProcess[str]) -> str:
    found = _PLAN_STATE.findall(plan.stdout)
    assert len(found) == 1, plan.stdout + plan.stderr
    return found[0]


def _rendered(plan: subprocess.CompletedProcess[str]) -> str:
    """The rendered file the dry run prints, one `  | ` line per file line."""
    return "".join(
        line.removeprefix("  | ").removeprefix("  |") + "\n"
        for line in plan.stdout.splitlines()
        if line.startswith("  |")
    )


def test_every_ci_pool_node_derives_the_mirror_endpoint_for_its_role(*, tmp_path: Path) -> None:
    """The server reaches the mirror on loopback; each agent at the carrier's address."""
    hosts = _ci_pool_hosts()
    assert {"poweredge-xubuntu", "gmktec-xubuntu", "hp-xubuntu"} <= set(hosts), hosts
    for host in hosts:
        plan = _plan(tmp_path=tmp_path, host=host)
        assert plan.returncode == 0, plan.stdout + plan.stderr
        assert _state(plan) == "absent", plan.stdout
        if _profile_key(host=host, key="CLUSTER_ROLE") == "server":
            expected = "http://127.0.0.1:5001"
        else:
            join = _profile_key(host=host, key="CLUSTER_JOIN_ADDRESS")
            expected = (
                "http://" + join.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0] + ":5001"
            )
        assert f'      - "{expected}"' in _rendered(
            plan
        ), f"{host} must point ghcr.io at {expected}:\n{plan.stdout}"
        mirrors = _rendered(plan).split("\nmirrors:\n", 1)[1]
        assert mirrors == f'  ghcr.io:\n    endpoint:\n      - "{expected}"\n', (
            "only ghcr.io is mirrored, through exactly one endpoint, so every other "
            f"registry and containerd's default-endpoint fallback are untouched:\n{mirrors}"
        )


def test_the_plan_states_drive_the_roles_drift_report(*, tmp_path: Path) -> None:
    """absent -> changed; the installer's own file -> unchanged; a foreign file -> refused."""
    host = "gmktec-xubuntu"
    plan = _plan(tmp_path=tmp_path, host=host)
    assert _state(plan) == "absent"
    installed = tmp_path / f"{host}-k3s" / "registries.yaml"
    installed.write_text(_rendered(plan), encoding="utf-8")
    assert _MARKER in installed.read_text(encoding="utf-8")
    assert (
        _state(_plan(tmp_path=tmp_path, host=host)) == "ours-unchanged"
    ), "a node carrying exactly the installer's rendering must read as no drift"
    installed.write_text(_rendered(plan).replace("5001", "5999"), encoding="utf-8")
    assert (
        _state(_plan(tmp_path=tmp_path, host=host)) == "ours"
    ), "the installer's own file with a stale endpoint must read as drift to rewrite"
    installed.write_text("mirrors: {}\n", encoding="utf-8")
    refused = _plan(tmp_path=tmp_path, host=host)
    assert refused.returncode != 0, "a hand-written registries.yaml must fail the plan"
    assert "Refusing to overwrite" in refused.stderr


def test_ci_pool_runs_the_role_on_every_node_right_after_the_k3s_start_configuration() -> None:
    play = _PLAY.read_text(encoding="utf-8")
    roles = re.findall(r"^    - role: (\w+)$", play, re.MULTILINE)
    assert roles[:2] == ["k3s_config", "registry_mirror_node"], roles[:3]
    entry = re.search(r"^    - role: registry_mirror_node\n((?:      .*\n)+)", play, re.MULTILINE)
    assert entry is not None
    assert "      tags: [registry_mirror_node]\n" in entry[1]
    assert "when:" not in entry[1], (
        "the mirror's node half goes on EVERY ci_pool node, the server included; the "
        "installer reads the node's role itself"
    )


def test_the_role_wraps_the_committed_installer_and_restarts_nothing() -> None:
    tasks = _TASKS.read_text(encoding="utf-8")
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert "ci-runner/k3s/phase2/warm-cache/registry-mirror" in defaults
    assert "registry_mirror_node_installer: install-registry-mirror.sh" in defaults
    assert "registry_mirror_node_template: registries.yaml.template" in defaults
    assert _INSTALLER.is_file()
    # The drift read: the installer's own dry run, run under --check too, with any
    # state but ours-unchanged reported as a change.
    plan = re.search(
        r"^- name: Plan the registries\.yaml install.*?\n(?P<body>(?:  .*\n|\n)+?)(?=^- name:)",
        tasks,
        re.MULTILINE,
    )
    assert plan is not None
    body = plan["body"]
    assert "      - --dry-run\n" in body
    assert "  check_mode: false\n" in body
    assert "'ours-unchanged'" in body and _PLAN_STATE.pattern.replace("\\", "") in body.replace(
        "\\", ""
    )
    # Never a restart: no service module, no handler, no notify, no k3s verb.
    for forbidden in ("systemd", "ansible.builtin.service", "notify:", "restart", "k3s-agent"):
        assert forbidden not in "\n".join(
            line for line in tasks.splitlines() if not line.lstrip().startswith("#")
        ), f"the role must never restart k3s or containerd; found {forbidden!r}"
    assert not (_ROLE / "handlers").exists()
