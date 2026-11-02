"""`docker_sandbox_slice` — retiring the envelope on one host (`docker_sandbox_slice_state: absent`).

WHY IT EXISTS (2026-11-02). hp-xubuntu leaves the Fabro factory role (plan
gmktec-factory-placement, item livespec-dev-tooling-2yn4yb) and is being reworked into a
Kubernetes factory worker. Its Docker sandbox envelope has to go, but the role's documented
rollback was a set of hand steps the fleet host guard forbids, and gmktec-xubuntu still
uses the role. So a host now leaves the envelope through the committed role.

WHAT THESE TESTS HOLD IT TO, BY RUNNING IT. The committed role is RUN, not read, under the
same `ansible-core` pin `just ansible-apply` uses. The host's daemon.json, the slice unit
directory and the pending-restart marker are all redirected into a temporary directory,
and `ansible_become=false` keeps the run inside it. A retiring host must:
- lose exactly `cgroup-parent` from daemon.json and keep every other key;
- record the drained restart it is owed;
- never reach the install half of the role, which would put the slice back;
- converge a second time with no change.
The drained-restart tag itself restarts dockerd, so no test selects it.
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
_SLICE = "fabro-sandbox.slice"


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


def _run(*, tmp_path: Path, state: str) -> tuple[int, str]:
    play_vars = {
        "ansible_become": False,
        "docker_sandbox_slice_state": state,
        "docker_sandbox_slice_daemon_config": str(tmp_path / "daemon.json"),
        "docker_sandbox_slice_unit_dir": str(tmp_path / "units"),
        "docker_sandbox_slice_pending_restart_marker": str(tmp_path / "marker" / "restart-pending"),
    }
    playbook = tmp_path / "retire.yml"
    header = (
        "- hosts: localhost",
        "  connection: local",
        "  gather_facts: false",
        f"  vars: {json.dumps(play_vars)}",
        "  roles:",
        "    - role: docker_sandbox_slice",
        "      tags: [docker_sandbox_slice]",
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


def test_retiring_removes_only_cgroup_parent_and_records_the_owed_restart(
    *, tmp_path: Path
) -> None:
    daemon = tmp_path / "daemon.json"
    _ = daemon.write_text(
        json.dumps({"cgroup-parent": _SLICE, "log-level": "warn", "live-restore": True}),
        encoding="utf-8",
    )
    code, output = _run(tmp_path=tmp_path, state="absent")
    assert code == 0, output
    assert json.loads(daemon.read_text(encoding="utf-8")) == {
        "log-level": "warn",
        "live-restore": True,
    }
    marker = tmp_path / "marker" / "restart-pending"
    assert marker.is_file(), output
    assert "RETIRING" in marker.read_text(encoding="utf-8")
    assert not (tmp_path / "units" / _SLICE).exists(), (
        "a retiring host must never reach the install half of the role, which writes the "
        f"slice unit back:\n{output}"
    )


def test_a_second_retiring_converge_changes_nothing(*, tmp_path: Path) -> None:
    daemon = tmp_path / "daemon.json"
    _ = daemon.write_text(json.dumps({"cgroup-parent": _SLICE}), encoding="utf-8")
    first, output = _run(tmp_path=tmp_path, state="absent")
    assert first == 0, output
    second, output = _run(tmp_path=tmp_path, state="absent")
    assert second == 0, output
    assert _changed_count(output) == 0, output
    assert (
        tmp_path / "marker" / "restart-pending"
    ).is_file(), "only the drained restart clears the marker; a later converge must leave it"


def test_a_retiring_host_whose_daemon_never_named_the_slice_is_left_alone(
    *, tmp_path: Path
) -> None:
    daemon = tmp_path / "daemon.json"
    original = json.dumps({"log-level": "warn"})
    _ = daemon.write_text(original, encoding="utf-8")
    code, output = _run(tmp_path=tmp_path, state="absent")
    assert code == 0, output
    assert daemon.read_text(encoding="utf-8") == original
    assert not (tmp_path / "marker" / "restart-pending").exists(), output


def test_an_unrecognised_state_is_refused_before_anything_is_written(*, tmp_path: Path) -> None:
    daemon = tmp_path / "daemon.json"
    original = json.dumps({"cgroup-parent": _SLICE})
    _ = daemon.write_text(original, encoding="utf-8")
    code, output = _run(tmp_path=tmp_path, state="retired")
    assert code != 0, output
    assert "docker_sandbox_slice_state" in output, output
    assert daemon.read_text(encoding="utf-8") == original
