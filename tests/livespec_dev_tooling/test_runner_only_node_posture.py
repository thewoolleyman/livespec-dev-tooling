"""The runner-only node posture's provisioning half: work volumes, cold starts, the sweep root.

livespec-dev-tooling-zreev4. A `CI_NODE_FACILITIES=runner-only` node takes CI
runner pods without carrying the pool's storage tiers. The parser and the
storage stage are graded in `test_hp_xubuntu_profile_and_storage_refusals.py`
and the play's role gating in `test_ci_pool_factory_only_agent_roles.py`. This
file grades what those two do not reach:

- every runner-only profile's RUNNER_WORKVOL_DIR is that node's own entry in the
  local-path provisioner's `nodePathMap`, and nothing else is, so runner volumes
  on that node land where its profile says and nowhere the profile does not name;
- the provisioner's committed `setup` script, run against a node path that holds
  no warm tree and no published externals (what a runner-only node's directory
  holds), leaves the new volume empty but for its seeded stamp, and writable;
- the play hands the same directory to the storage sweep and the container hook.

The setup script is EXECUTED under `/bin/sh` against a scratch node path, as
`test_local_path_setup_rerun_keeps_seed.py` does; nothing here touches a host.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_PROFILES = _REPO / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"
_PROVISIONER = (
    _REPO
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "local-path-provisioner"
    / "local-path-provisioner.yaml"
)
_PLAY = _REPO / "ansible" / "ci-pool.yml"
_SWEEP_TASKS = _REPO / "ansible" / "roles" / "storage_sweep" / "tasks" / "main.yml"
_SWEEP_DEFAULTS = _REPO / "ansible" / "roles" / "storage_sweep" / "defaults" / "main.yml"

_DEFAULT_NODE = "DEFAULT_PATH_FOR_NON_LISTED_NODES"
_DEFAULT_PATH = "/var/lib/rancher/k3s/storage"
_CONFIG_JSON = re.compile(r"^  config\.json: \|-\n(?P<body>.*?)\n  [a-z]", re.MULTILINE | re.DOTALL)
_SETUP_SCRIPT = re.compile(r"^  setup: \|-\n(?P<body>.*?)\n  [a-z]", re.MULTILINE | re.DOTALL)


def _profile_value(*, text: str, key: str) -> str:
    found = re.findall(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return found[0] if found else ""


def _runner_only_workvols() -> dict[str, str]:
    """Each runner-only profile's node name mapped to its RUNNER_WORKVOL_DIR."""
    workvols: dict[str, str] = {}
    for profile in sorted(_PROFILES.glob("*.env")):
        text = profile.read_text(encoding="utf-8")
        if _profile_value(text=text, key="CI_NODE_FACILITIES") == "runner-only":
            workvols[_profile_value(text=text, key="NODE_NAME")] = _profile_value(
                text=text, key="RUNNER_WORKVOL_DIR"
            )
    return workvols


def _node_path_map() -> dict[str, list[str]]:
    match = _CONFIG_JSON.search(_PROVISIONER.read_text(encoding="utf-8"))
    assert match is not None, f"no `config.json: |-` block in {_PROVISIONER}"
    config = json.loads("\n".join(line[4:] for line in match["body"].splitlines()))
    return {entry["node"]: entry["paths"] for entry in config["nodePathMap"]}


def test_hp_is_a_committed_runner_only_node() -> None:
    """The control that keeps the lockstep test below from passing on an empty set."""
    assert "hp-xubuntu" in _runner_only_workvols(), (
        f"hp-xubuntu's committed profile must declare CI_NODE_FACILITIES=runner-only "
        f"(livespec-dev-tooling-zreev4); runner-only profiles={_runner_only_workvols()}"
    )


def test_each_runner_only_node_has_its_own_work_volume_path_and_no_other_node_does() -> None:
    """nodePathMap and the runner-only profiles name the same nodes and the same paths."""
    node_paths = _node_path_map()
    assert node_paths.get(_DEFAULT_NODE) == [_DEFAULT_PATH], (
        f"every node the map does not list keeps the bundled default {_DEFAULT_PATH}, which "
        f"a `full` node's ci-workvols tier is bound onto; got {node_paths}"
    )
    listed = {node: paths for node, paths in node_paths.items() if node != _DEFAULT_NODE}
    expected = {node: [workvol] for node, workvol in _runner_only_workvols().items()}
    assert listed == expected, (
        f"the provisioner must give each runner-only node exactly its profile's "
        f"RUNNER_WORKVOL_DIR, and list no other node: a runner-only node left off the map "
        f"would put its runner volumes on {_DEFAULT_PATH}, which its profile does not name, "
        f"and a listed node that is not runner-only would be a second answer for a node "
        f"whose volumes live on its tier; map={listed} profiles={expected}"
    )


def _setup_script() -> str:
    match = _SETUP_SCRIPT.search(_PROVISIONER.read_text(encoding="utf-8"))
    assert match is not None, f"no `setup: |-` block in {_PROVISIONER}"
    return "\n".join(line[4:] for line in match["body"].splitlines()) + "\n"


def test_a_volume_on_a_runner_only_node_path_starts_unseeded_and_writable(tmp_path: Path) -> None:
    """No warm tree and no published externals under the node path: a cold, writable volume.

    A runner-only node's work-volume directory holds neither: the warm-cache
    CronJob writes `.warm` only on the cache-tier carrier, and its filesystem need
    not support the reflink the externals seed uses.
    """
    node = tmp_path / "runner-workvols"
    node.mkdir()
    script = tmp_path / "setup"
    script.write_text(_setup_script(), encoding="utf-8")
    vol_dir = node / "pvc-0000_arc-runners_runner-x-work"
    completed = subprocess.run(
        ["/bin/sh", str(script)],
        env={
            **os.environ,
            "VOL_DIR": str(vol_dir),
            "VOL_MODE": "Filesystem",
            "VOL_SIZE_BYTES": "0",
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert sorted(entry.name for entry in vol_dir.iterdir()) == [".livespec-volume-seeded"], (
        f"a volume provisioned where no warm tree or externals copy exists must carry no "
        f"seed at all, only the setup script's completion stamp; it holds "
        f"{sorted(entry.name for entry in vol_dir.iterdir())}"
    )
    mode = stat.S_IMODE(vol_dir.stat().st_mode)
    assert mode & 0o777 == 0o777, (
        f"and it must be writable by the runner, as every work volume is (mode 2777); "
        f"got {oct(mode)}"
    )


def test_the_play_hands_the_work_volume_directory_to_the_sweep_and_the_hook() -> None:
    """The same profile fact reaches the two roles that act on the node's volume root."""
    play = _PLAY.read_text(encoding="utf-8")
    assert 'storage_sweep_storage_root: "{{ ci_pool_runner_workvol_dir }}"' in play, (
        "the play must pass the profile's RUNNER_WORKVOL_DIR to storage_sweep, so the "
        "boot-time sweep clears the directory a runner-only node's volumes live in"
    )
    assert re.search(
        r"container_hook_storage_root: >-\n\s+\{\{ ci_pool_runner_workvol_dir if "
        r"ci_pool_runner_workvol_dir else '/var/lib/rancher/k3s/storage' \}\}",
        play,
    ), (
        "the play must root the container hook's externals in the runner-only node's "
        "work-volume directory, where the provisioner's setup script looks for them"
    )


def test_the_sweep_renders_a_storage_root_drop_in_only_when_one_is_given() -> None:
    """A non-empty root gets an Environment= drop-in; an empty one removes it."""
    defaults = _SWEEP_DEFAULTS.read_text(encoding="utf-8")
    assert 'storage_sweep_storage_root: ""' in defaults, (
        "the sweep's storage root must default to '' so every node that names no "
        "runner work-volume directory keeps the script's own default and no drop-in"
    )
    tasks = _SWEEP_TASKS.read_text(encoding="utf-8")
    assert "Environment=STORAGE_ROOT={{ storage_sweep_storage_root }}" in tasks
    assert "RequiresMountsFor={{ storage_sweep_storage_root }}" in tasks
    assert "when: storage_sweep_storage_root | length > 0" in tasks
    assert "when: storage_sweep_storage_root | length == 0" in tasks


_KUEUE_DIR = _REPO / "ci-runner" / "k3s" / "phase2" / "kueue"
_DERIVATION = _KUEUE_DIR / "DERIVATION.md"
_NOMINAL_QUOTA = re.compile(r"^\s+nominalQuota: (?P<quota>\d+)\s*$", re.MULTILINE)


def _cohort_quota_total() -> int:
    return sum(
        int(match["quota"])
        for path in sorted(_KUEUE_DIR.glob("cluster-queue-livespec*.yaml"))
        for match in _NOMINAL_QUOTA.finditer(path.read_text(encoding="utf-8"))
    )


def test_the_rebalance_moves_eight_slots_from_poweredge_to_hp_and_keeps_the_total_at_44() -> None:
    """hp's 8 churn slots came from poweredge, so the cohort total and its quotas did not move.

    The 450-point JIT startup budget caps a cold start at about 45 mint pairs and
    nothing else in the pool caps it, so opening hp could not ADD capacity
    (DERIVATION.md "The rebalance at C = 44 — hp-xubuntu opened runner-only
    (2026-11-03)").
    """
    capacities = {
        profile.stem: int(
            _profile_value(text=profile.read_text(encoding="utf-8"), key="ADMISSION_CAPACITY_C")
        )
        for profile in sorted(_PROFILES.glob("*.env"))
    }
    assert capacities == {
        "gmktec-xubuntu": 18,
        "hp-xubuntu": 8,
        "poweredge-xubuntu": 18,
    }, (
        f'the cores-derived split is poweredge 27, gmktec 12, hp 5 (DERIVATION.md "Per-node '
        f'churn slots derived from cores (2026-11-04)"); got {capacities}'
    )
    assert sum(capacities.values()) == 44 == _cohort_quota_total(), (
        f"the profiles must still sum to 44 and equal the ten cohort quotas; "
        f"profiles={sum(capacities.values())} quotas={_cohort_quota_total()}"
    )
    assert (
        "## The rebalance at C = 44 — hp-xubuntu opened runner-only (2026-11-03)"
        in _DERIVATION.read_text(encoding="utf-8")
    )
