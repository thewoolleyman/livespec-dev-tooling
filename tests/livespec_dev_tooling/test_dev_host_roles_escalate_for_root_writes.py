"""Every role wired into `ansible/dev-host.yml` escalates for its root-owned writes.

`dev-host.yml` runs as the `ubuntu` user over a local connection, so a task that writes
under `/usr/local` or `/etc`, or manages a system unit, fails with a permission error unless
it carries `become: true`. Check mode does not see that failure: drift reported clean while
the real vps apply failed (livespec-dev-tooling-fwtuxo, 2026-11-21). The sibling defect, a
sha256 pin passed to `copy`'s SHA-1 `checksum:`, is covered by
`test_ansible_copy_checksum_is_sha1.py`.

The rule is deliberately narrow so it cannot misfire: a task is in scope when it uses the
`systemd` module (system scope), or when a `copy`, `template`, `file` or `lineinfile` task's
literal `dest`/`path` starts with `/usr/local` or `/etc/`. A role may keep a task out of
scope by having it write elsewhere; it may not skip `become` on an in-scope task.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

__all__: list[str] = []

_ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
_FILE_MODULES = (
    "ansible.builtin.copy",
    "ansible.builtin.template",
    "ansible.builtin.file",
    "ansible.builtin.lineinfile",
)
_SYSTEMD = "ansible.builtin.systemd"
_ROOT_PREFIXES = ("/usr/local", "/etc/")


def _tasks(
    *, items: list[dict[str, Any]] | None, inherited: object
) -> list[tuple[dict[str, Any], object]]:
    """Flatten a task list, carrying a block's `become` down to its children."""
    found: list[tuple[dict[str, Any], object]] = []
    for item in items or []:
        escalated = item.get("become", inherited)
        if "block" in item:
            found.extend(_tasks(items=item["block"], inherited=escalated))
        else:
            found.append((item, escalated))
    return found


def _in_scope(*, task: dict[str, Any]) -> bool:
    if _SYSTEMD in task:
        return True
    for module in _FILE_MODULES:
        args = task.get(module)
        if isinstance(args, dict):
            target = str(args.get("dest") or args.get("path") or "")
            if target.startswith(_ROOT_PREFIXES):
                return True
    return False


def _unescalated(*, role: str) -> list[str]:
    offenders: list[str] = []
    role_dir = _ANSIBLE / "roles" / role
    for path in sorted([*role_dir.glob("tasks/*.yml"), *role_dir.glob("handlers/*.yml")]):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        for task, escalated in _tasks(items=loaded, inherited=None):
            if _in_scope(task=task) and escalated is not True:
                offenders.append(f"{role}/{path.parent.name}/{path.name}: {task.get('name', '?')}")
    return offenders


def test_the_rule_flags_an_unescalated_system_task() -> None:
    sample = [{"name": "x", "ansible.builtin.systemd": {"name": "u", "state": "started"}}]
    flagged = [
        t for t, e in _tasks(items=sample, inherited=None) if _in_scope(task=t) and e is not True
    ]
    assert len(flagged) == 1


def test_a_block_level_become_covers_its_tasks() -> None:
    sample = [{"become": True, "block": [{"name": "x", "ansible.builtin.systemd": {"name": "u"}}]}]
    flagged = [
        t for t, e in _tasks(items=sample, inherited=None) if _in_scope(task=t) and e is not True
    ]
    assert flagged == []


def test_every_dev_host_role_escalates_for_its_root_writes() -> None:
    plays = yaml.safe_load((_ANSIBLE / "dev-host.yml").read_text(encoding="utf-8"))
    roles = [entry["role"] for play in plays for entry in play.get("roles", [])]
    assert roles, "dev-host.yml should wire roles"
    offenders = [line for role in roles for line in _unescalated(role=role)]
    assert offenders == [], offenders
