"""Retiring four sandbox-play roles on one host (`<role>_state: absent`).

WHY IT EXISTS (2026-11-02). hp-xubuntu left `sandbox_hosts` to become a Kubernetes
factory worker (plan gmktec-factory-placement). The units that sccache_redis,
otel_receiver, storage_reclaim and container_reclaim installed there serve nothing
now, and the fleet host guard forbids removing them by hand. So each role gained a
committed retirement: `<role>_state: absent` runs its tasks/retire.yml and ends the
role before its install half (livespec-dev-tooling-j53hzi).

WHAT THESE TESTS HOLD THEM TO, BY RUNNING THEM. Each committed role is RUN, not
read, under the same `ansible-core` pin `just ansible-apply` uses. Its unit
directory is redirected into a temporary directory that holds no unit, and
`ansible_become=false` keeps the run inside it. A retiring host must:
- converge without error, and without reaching the install half, which would
  reinstall the units, probe the container daemon or look up service accounts;
- converge a second time with no change.
Stopping and disabling a unit that IS present calls the real systemd, which no
test may touch. The host-captured proof on the work item covers that half on the
host itself.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLES = _REPO_ROOT / "ansible" / "roles"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_TIMEOUT_SECONDS = 600

# Each role, the variable that redirects where it keeps its units, and the name of
# the FIRST task of its install half: a retiring run must never print it.
_ROLES_UNDER_TEST = {
    "sccache_redis": ("sccache_redis_unit_dir", "Refuse an empty value in any field"),
    "otel_receiver": (
        "otel_receiver_unit_path",
        "Refuse a receiver configuration this role cannot install safely",
    ),
    "storage_reclaim": ("storage_reclaim_unit_dir", "Look up the account that owns the worktrees"),
    "container_reclaim": (
        "container_reclaim_unit_dir",
        "Look up the account the reclaim service will run as",
    ),
}


def _ansible_core_pin() -> str:
    """The `ansible-core==<version>` pin the `ansible-apply` recipe resolves."""
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, f"{_JUSTFILE} must carry the `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _run(*, tmp_path: Path, role: str) -> tuple[int, str]:
    unit_var, _ = _ROLES_UNDER_TEST[role]
    units = tmp_path / "units"
    units.mkdir(exist_ok=True)
    unit_value = str(units / "otel-receiver.service") if unit_var.endswith("_path") else str(units)
    play_vars = {
        "ansible_become": False,
        f"{role}_state": "absent",
        unit_var: unit_value,
        # Turned on so that, were the install half reached, it would run rather than
        # end the role at its own off switch.
        "otel_receiver_enabled": True,
    }
    playbook = tmp_path / "retire.yml"
    header = (
        "- hosts: localhost",
        "  connection: local",
        "  gather_facts: false",
        f"  vars: {json.dumps(play_vars)}",
        "  roles:",
        f"    - role: {role}",
        f"      tags: [{role}]",
    )
    _ = playbook.write_text("\n".join(header) + "\n", encoding="utf-8")
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            "localhost,",
            str(playbook),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(_ROLES)},
    )
    return completed.returncode, completed.stdout + completed.stderr


def _changed_count(output: str) -> int:
    recap = re.search(r"localhost\s*:\s*ok=\d+\s+changed=(?P<changed>\d+)", output)
    assert recap is not None, output
    return int(recap["changed"])


@pytest.mark.parametrize("role", sorted(_ROLES_UNDER_TEST))
def test_a_retiring_host_never_reaches_the_install_half(*, tmp_path: Path, role: str) -> None:
    code, output = _run(tmp_path=tmp_path, role=role)
    assert code == 0, output
    _, first_install_task = _ROLES_UNDER_TEST[role]
    assert first_install_task not in output, (
        f"a host retiring {role} must end the role before its install half, which would "
        f"reinstall what the retirement removes:\n{output}"
    )
    assert f"Look for the units {role} installed on this host" in output, output


@pytest.mark.parametrize("role", sorted(_ROLES_UNDER_TEST))
def test_a_second_retiring_converge_changes_nothing(*, tmp_path: Path, role: str) -> None:
    first, output = _run(tmp_path=tmp_path, role=role)
    assert first == 0, output
    second, output = _run(tmp_path=tmp_path, role=role)
    assert second == 0, output
    assert _changed_count(output) == 0, output
