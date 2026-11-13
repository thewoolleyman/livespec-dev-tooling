"""The `k3s_config` role's user.slice CPU weight: written, removed, and reloaded once.

Work-item `livespec-dev-tooling-wsjl7j`. A pool node that is also somebody's
workstation gives its local login sessions (user.slice) a declared share of the
CPU against the pods (kubepods.slice). The role carries that as a host variable
and a systemd drop-in.

THE ROLE IS RUN, NOT READ. Each test executes the role's own tasks with the
`ansible-core` pin `just ansible-apply` uses, narrowed to the lever's tag exactly
as an operator narrows it, against a one-host local inventory, a stand-in `sudo`
and `systemctl`, and paths under `tmp_path`. Every value the role reads (the
weight, the drop-in directory, the owner) is a FIXTURE value, so no test pins a
committed configuration value: the weight a real host declares can change with
no test to edit.

THE STAND-IN `systemctl` ANSWERS `daemon-reload` AND NOTHING ELSE. Any other
verb exits non-zero and fails the apply, so a future edit that restarted a unit
from these tasks would break every test here instead of passing quietly.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLES_PATH = _REPO_ROOT / "ansible" / "roles"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_TIMEOUT_SECONDS = 600
_HOST = "fixture-node"
_TAG = "k3s_user_slice_cpu_weight"
_VARIABLE = "k3s_config_user_slice_cpu_weight"
_DROP_IN = "50-cpu-weight.conf"

# Fixture weights: neither is a value the role or the inventory commits.
_WEIGHT = "321"
_OTHER_WEIGHT = "654"

_SUDO_STAND_IN = """#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    -u) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
exec "$@"
"""

_SYSTEMCTL_STAND_IN = """#!/bin/sh
state="$(dirname "$0")/../state"
printf '%s\\n' "$*" >> "$state/systemctl.log"
[ "$*" = daemon-reload ] && exit 0
printf 'stand-in systemctl: unexpected invocation: %s\\n' "$*" >&2
exit 64
"""


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    root: Path
    bin_dir: Path
    state: Path
    drop_in_dir: Path

    @property
    def drop_in(self) -> Path:
        return self.drop_in_dir / _DROP_IN

    def systemctl_calls(self) -> list[str]:
        log = self.state / "systemctl.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@dataclass(frozen=True, kw_only=True)
class _Outcome:
    returncode: int
    changed: int
    output: str


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    for name, body in (("sudo", _SUDO_STAND_IN), ("systemctl", _SYSTEMCTL_STAND_IN)):
        stand_in = bin_dir / name
        _ = stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    return _Scratch(
        root=tmp_path, bin_dir=bin_dir, state=state, drop_in_dir=tmp_path / "user.slice.d"
    )


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None
    return pin[0]


def _apply(*, scratch: _Scratch, weight: str, check: bool = False) -> _Outcome:
    """Run the role once, narrowed to the lever's tag; return what the host's recap says."""
    host_vars = {
        _VARIABLE: f'"{weight}"',
        "k3s_config_user_slice_drop_in_dir": str(scratch.drop_in_dir),
        "k3s_config_user_slice_drop_in_owner": str(os.getuid()),
        "k3s_config_user_slice_drop_in_group": str(os.getgid()),
    }
    declared = "".join(f"      {key}: {value}\n" for key, value in host_vars.items())
    inventory = scratch.root / "inventory.yml"
    _ = inventory.write_text(
        f"all:\n  hosts:\n    {_HOST}:\n      ansible_connection: local\n{declared}",
        encoding="utf-8",
    )
    play = scratch.root / "play.yml"
    _ = play.write_text(
        (
            "- name: fixture\n  hosts: all\n  gather_facts: false\n"
            "  roles:\n    - role: k3s_config\n"
        ),
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "ANSIBLE_ROLES_PATH": str(_ROLES_PATH),
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
        }
    )
    command = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", "--tags", _TAG]
    if check:
        command += ["--check", "--diff"]
    completed = subprocess.run(
        [*command, "-i", str(inventory), str(play)],
        cwd=scratch.root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    output = completed.stdout + completed.stderr
    recap = re.search(rf"^{_HOST}\s+: .*?\bchanged=(?P<changed>\d+)\b", output, re.MULTILINE)
    assert recap is not None, output
    return _Outcome(returncode=completed.returncode, changed=int(recap["changed"]), output=output)


def _drop_in_settings(*, scratch: _Scratch) -> list[str]:
    """The drop-in's effective lines: what systemd reads once comments are dropped."""
    return [
        line
        for line in scratch.drop_in.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def test_a_declared_weight_is_written_as_a_slice_drop_in_and_reloaded_once(
    *, scratch: _Scratch
) -> None:
    outcome = _apply(scratch=scratch, weight=_WEIGHT)
    assert outcome.returncode == 0, outcome.output
    assert _drop_in_settings(scratch=scratch) == ["[Slice]", f"CPUWeight={_WEIGHT}"]
    assert scratch.systemctl_calls() == ["daemon-reload"]
    # The directory and the drop-in (a reload reports no change of its own):
    # nothing else in the role ran.
    assert outcome.changed == 2, outcome.output


def test_a_second_apply_of_the_same_weight_changes_nothing_and_reloads_nothing(
    *, scratch: _Scratch
) -> None:
    assert _apply(scratch=scratch, weight=_WEIGHT).returncode == 0
    outcome = _apply(scratch=scratch, weight=_WEIGHT)
    assert (outcome.returncode, outcome.changed) == (0, 0), outcome.output
    assert scratch.systemctl_calls() == ["daemon-reload"]


def test_a_changed_weight_rewrites_the_drop_in_and_reloads_once_more(*, scratch: _Scratch) -> None:
    assert _apply(scratch=scratch, weight=_WEIGHT).returncode == 0
    outcome = _apply(scratch=scratch, weight=_OTHER_WEIGHT)
    assert outcome.returncode == 0, outcome.output
    assert _drop_in_settings(scratch=scratch) == ["[Slice]", f"CPUWeight={_OTHER_WEIGHT}"]
    assert scratch.systemctl_calls() == ["daemon-reload", "daemon-reload"]


def test_an_empty_weight_removes_the_drop_in_and_reloads_once(*, scratch: _Scratch) -> None:
    assert _apply(scratch=scratch, weight=_WEIGHT).returncode == 0
    outcome = _apply(scratch=scratch, weight="")
    assert outcome.returncode == 0, outcome.output
    assert not scratch.drop_in.exists()
    assert scratch.systemctl_calls() == ["daemon-reload", "daemon-reload"]
    # The removal alone; the emptied directory stays.
    assert outcome.changed == 1, outcome.output


def test_an_empty_weight_on_a_node_with_no_drop_in_changes_nothing(*, scratch: _Scratch) -> None:
    outcome = _apply(scratch=scratch, weight="")
    assert (outcome.returncode, outcome.changed) == (0, 0), outcome.output
    assert not scratch.drop_in_dir.exists()
    assert scratch.systemctl_calls() == []


@pytest.mark.parametrize("refused", ["0", "10001", "heavy"])
def test_a_weight_systemd_would_not_accept_is_refused_before_anything_is_written(
    *, scratch: _Scratch, refused: str
) -> None:
    outcome = _apply(scratch=scratch, weight=refused)
    assert outcome.returncode != 0, outcome.output
    assert _VARIABLE in outcome.output
    assert not scratch.drop_in_dir.exists()
    assert scratch.systemctl_calls() == []


def test_a_drift_report_shows_the_pending_weight_and_changes_nothing(*, scratch: _Scratch) -> None:
    outcome = _apply(scratch=scratch, weight=_WEIGHT, check=True)
    assert outcome.returncode == 0, outcome.output
    assert outcome.changed > 0, outcome.output
    assert not scratch.drop_in_dir.exists()
    assert scratch.systemctl_calls() == []
