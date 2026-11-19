"""Consumer-tier proof for the homelab-worker script delivery play.

`ansible/homelab-worker-scripts.yml` (livespec-dev-tooling-qpmzxa) puts the
committed homelab-worker scripts, at the release tag the play is applied from,
on a worker's macOS host, so a host leg can name that tag as its build and no
by-hand `git` runs on the Mac. These tests read the committed play, role and
inventory, because the live apply is a host action no test run may take.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAY = _REPO_ROOT / "ansible" / "homelab-worker-scripts.yml"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "homelab_worker_scripts"
_INVENTORY = _REPO_ROOT / "ansible" / "inventory" / "legacy.yml"


def _tasks() -> list[dict[str, object]]:
    """Every task of the role in order, with a block's tasks flattened in place."""
    flat: list[dict[str, object]] = []
    for task in yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")):
        flat.append(task)
        flat.extend(task.get("block", []))
        flat.extend(task.get("always", []))
    return flat


def _defaults() -> dict[str, object]:
    return yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))


def _group_hosts(node: object, found: dict[str, set[str]]) -> None:
    if not isinstance(node, dict):
        return
    for name, body in node.items():
        if not isinstance(body, dict):
            continue
        hosts = body.get("hosts")
        if isinstance(hosts, dict):
            found[name] = set(hosts)
        _group_hosts(body, found)


def test_the_play_selects_only_the_homelab_workers_group_and_runs_the_one_role() -> None:
    (play,) = yaml.safe_load(_PLAY.read_text(encoding="utf-8"))
    assert play["hosts"] == "homelab_workers"
    assert [role["role"] for role in play["roles"]] == ["homelab_worker_scripts"]


def test_the_worker_host_has_its_own_group_and_stays_in_the_memory_guard_group() -> None:
    groups: dict[str, set[str]] = {}
    _group_hosts(yaml.safe_load(_INVENTORY.read_text(encoding="utf-8")), groups)
    assert "macbook-m4-max" in groups["homelab_workers"]
    assert "macbook-m4-max.perch-rudd.ts.net" in groups["interactive_claude_macs"]


def test_a_confirmation_that_does_not_name_the_host_ends_the_host_before_any_read() -> None:
    tasks = _tasks()
    end_index = next(i for i, task in enumerate(tasks) if "ansible.builtin.meta" in task)
    assert tasks[end_index]["ansible.builtin.meta"] == "end_host"
    assert tasks[end_index]["when"] == "homelab_worker_scripts_confirm != inventory_hostname"
    assert end_index <= 1
    assert _defaults()["homelab_worker_scripts_confirm"] == ""


def test_only_a_release_tag_head_is_accepted_and_the_check_runs_under_drift_too() -> None:
    describe = next(t for t in _tasks() if "Read the release tag" in str(t["name"]))
    assert "--exact-match" in describe["ansible.builtin.command"]["argv"]
    assert describe["check_mode"] is False
    assert describe["delegate_to"] == "localhost"
    assert _defaults()["homelab_worker_scripts_tag_pattern"] == r"^v[0-9]+\.[0-9]+\.[0-9]+$"


def test_files_come_from_the_tags_objects_not_the_working_tree() -> None:
    text = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "archive --format=tar" in text
    assert "ansible.builtin.find" in text


def test_the_scripts_and_the_phase2_files_they_source_are_both_delivered() -> None:
    assert _defaults()["homelab_worker_scripts_paths"] == [
        "homelab-worker",
        "ci-runner/k3s/phase2",
    ]


def test_each_file_is_delivered_preserving_mode_and_the_tag_is_recorded_beside_them() -> None:
    tasks = _tasks()
    copy = next(t for t in tasks if "Deliver each committed file" in str(t["name"]))
    assert copy["ansible.builtin.copy"]["mode"] == "preserve"
    record = next(t for t in tasks if "Record the tag" in str(t["name"]))
    assert record["ansible.builtin.copy"]["dest"].endswith("/RELEASE_TAG")


def test_the_scratch_directory_is_removed_in_an_always_section() -> None:
    tasks = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    block = next(t for t in tasks if "block" in t)
    assert [t["ansible.builtin.file"]["state"] for t in block["always"]] == ["absent"]


def test_nothing_in_the_role_reads_or_changes_a_git_clone_on_the_host() -> None:
    host_side = [
        task
        for task in _tasks()
        if task.get("delegate_to") != "localhost"
        and "ansible.builtin.meta" not in task
        and "block" not in task
    ]
    for task in host_side:
        text = yaml.safe_dump(task).replace("RELEASE_TAG", "")
        assert "git" not in text, task["name"]
    assert "workspace" not in str(_defaults()["homelab_worker_scripts_root"])
