"""The `apparmor_profile` role makes the kernel hold each committed profile, and says when it does not.

Kernel 7.0.0-43 labels every non-privileged container `<profile>//&unconfined`,
and containerd's built-in default profile allows signals only to the bare name,
so a gate Job could not signal its own children (livespec-dev-tooling-ddy5xu).
The role now also holds containerd's default profile at node level. What a pod
is confined by is the policy the KERNEL holds, not the file on disk, so the role
compares the two and loads on any difference.

THE ROLE IS RUN, NOT READ. Each test executes it with the `ansible-core` pin
`just ansible-drift` uses, against a one-host local inventory, a stand-in
`apparmor_parser` and `sudo`, and paths under `tmp_path`. Every value the role
reads (profile names, source and destination directories, the kernel's profile
directory) is a FIXTURE value, so no test pins a committed configuration value.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLES_PATH = _REPO_ROOT / "ansible" / "roles"
_PLAY = _REPO_ROOT / "ansible" / "ci-pool.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_TIMEOUT_SECONDS = 600
_HOST = "fixture-node"

# Fixture values: none of them is a value the role or the inventory commits.
# The second name carries dots, as a runtime's default profile name does.
_PLAIN = "fixture-workload"
_DOTTED = "fixture-runtime.default.d"
_PROFILES = (_PLAIN, _DOTTED)
_FOREIGN_POLICY = "f" * 64

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

# The stand-in parser. It logs every invocation. `-Q -K -S <file>` prints the
# file as its "compiled policy" and touches nothing. `-r -W <file>` records that
# policy as loaded, the way the kernel exposes it: `<name>.<id>/raw_sha256` and
# `mode`, with the mode taken from the state directory. Anything else exits 64.
_PARSER_STAND_IN = """#!/bin/sh
state="$(dirname "$0")/../state"
printf '%s\\n' "$*" >> "$state/argv.log"
case "$1" in
  -Q) [ "$2" = -K ] && [ "$3" = -S ] || exit 64; cat "$4"; exit 0 ;;
  -r)
    [ "$2" = -W ] || exit 64
    name="$(basename "$3")"
    mkdir -p "$state/loaded/$name.7"
    sha256sum < "$3" | cut -d' ' -f1 > "$state/loaded/$name.7/raw_sha256"
    cat "$state/mode" > "$state/loaded/$name.7/mode"
    exit 0 ;;
esac
exit 64
"""


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    root: Path
    bin_dir: Path
    state: Path
    src: Path
    dest: Path

    @property
    def loaded(self) -> Path:
        return self.state / "loaded"

    def loads(self) -> list[str]:
        log = self.state / "argv.log"
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return [line for line in lines if line.startswith("-r ")]

    def loaded_policy(self, *, name: str) -> str:
        return (self.loaded / f"{name}.7" / "raw_sha256").read_text(encoding="utf-8").strip()

    def source_policy(self, *, name: str) -> str:
        return hashlib.sha256((self.src / name).read_bytes()).hexdigest()


@dataclass(frozen=True, kw_only=True)
class _Outcome:
    returncode: int
    changed: int
    output: str


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    src = tmp_path / "src"
    dest = tmp_path / "etc-apparmor.d"
    for directory in (bin_dir, state, state / "loaded", src, dest):
        directory.mkdir()
    for name, body in (("sudo", _SUDO_STAND_IN), ("apparmor_parser", _PARSER_STAND_IN)):
        stand_in = bin_dir / name
        stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    (state / "mode").write_text("enforce\n", encoding="utf-8")
    for name in _PROFILES:
        (src / name).write_text(f"profile {name} {{\n}}\n", encoding="utf-8")
    return _Scratch(root=tmp_path, bin_dir=bin_dir, state=state, src=src, dest=dest)


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-drift \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None
    return pin[0]


def _play(*, scratch: _Scratch, check: bool = False) -> _Outcome:
    """Run the role once; return its exit code and the host's `changed=` count."""
    host_vars = {
        "apparmor_profile_names": f"[{', '.join(_PROFILES)}]",
        "apparmor_profile_src_dir": str(scratch.src),
        "apparmor_profile_dest_dir": str(scratch.dest),
        "apparmor_profile_loaded_dir": str(scratch.loaded),
        "apparmor_profile_owner": str(os.getuid()),
        "apparmor_profile_group": str(os.getgid()),
        "apparmor_profile_parser_paths": f"[{scratch.bin_dir / 'apparmor_parser'}]",
    }
    declared = "".join(f"      {key}: {value}\n" for key, value in host_vars.items())
    inventory = scratch.root / "inventory.yml"
    inventory.write_text(
        f"all:\n  hosts:\n    {_HOST}:\n      ansible_connection: local\n{declared}",
        encoding="utf-8",
    )
    play = scratch.root / "play.yml"
    play.write_text(
        "- name: fixture\n  hosts: all\n  gather_facts: false\n"
        "  roles:\n    - role: apparmor_profile\n",
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
    command = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook"]
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


def _run(*, scratch: _Scratch, check: bool = False) -> int:
    """Run the role, require it to complete, and return the `changed=` count."""
    outcome = _play(scratch=scratch, check=check)
    assert outcome.returncode == 0, f"the role must complete:\n{outcome.output}"
    return outcome.changed


def test_a_fresh_node_gets_every_profile_installed_and_loaded(*, scratch: _Scratch) -> None:
    # The recap counts tasks, not loop items: the install task and the load task.
    assert _run(scratch=scratch) == 2
    for name in _PROFILES:
        assert (scratch.dest / name).read_bytes() == (scratch.src / name).read_bytes()
        assert scratch.loaded_policy(name=name) == scratch.source_policy(name=name)
    assert scratch.loads() == [f"-r -W {scratch.dest / name}" for name in _PROFILES]


def test_a_second_apply_changes_nothing_and_loads_nothing(*, scratch: _Scratch) -> None:
    _run(scratch=scratch)
    assert _run(scratch=scratch) == 0
    assert len(scratch.loads()) == len(_PROFILES)


def test_a_drift_report_on_a_fresh_node_shows_the_pending_change_and_writes_nothing(
    *, scratch: _Scratch
) -> None:
    # The pending install, and the probe standing in for the skipped load.
    assert _run(scratch=scratch, check=True) == 2
    assert list(scratch.dest.iterdir()) == []
    assert list(scratch.loaded.iterdir()) == []
    assert scratch.loads() == []


def test_a_drift_report_on_a_converged_node_shows_nothing(*, scratch: _Scratch) -> None:
    _run(scratch=scratch)
    assert _run(scratch=scratch, check=True) == 0


def test_a_policy_the_runtime_loaded_over_ours_is_reported_and_replaced(
    *, scratch: _Scratch
) -> None:
    """The file on disk still matches, but the kernel holds someone else's policy."""
    _run(scratch=scratch)
    held = scratch.loaded / f"{_DOTTED}.7" / "raw_sha256"
    held.write_text(f"{_FOREIGN_POLICY}\n", encoding="utf-8")
    assert _run(scratch=scratch, check=True) == 1
    assert held.read_text(encoding="utf-8").strip() == _FOREIGN_POLICY
    assert _run(scratch=scratch) == 1
    assert scratch.loaded_policy(name=_DOTTED) == scratch.source_policy(name=_DOTTED)
    assert scratch.loads()[-1] == f"-r -W {scratch.dest / _DOTTED}"
    assert len(scratch.loads()) == len(_PROFILES) + 1


def test_a_changed_profile_file_is_installed_and_reloaded_alone(*, scratch: _Scratch) -> None:
    _run(scratch=scratch)
    (scratch.src / _PLAIN).write_text(f"profile {_PLAIN} {{\n  # edited\n}}\n", encoding="utf-8")
    assert _run(scratch=scratch) == 2
    assert scratch.loaded_policy(name=_PLAIN) == scratch.source_policy(name=_PLAIN)
    assert scratch.loads()[-1] == f"-r -W {scratch.dest / _PLAIN}"
    assert len(scratch.loads()) == len(_PROFILES) + 1


def test_a_profile_that_did_not_reach_enforce_mode_fails_the_play(*, scratch: _Scratch) -> None:
    (scratch.state / "mode").write_text("complain\n", encoding="utf-8")
    outcome = _play(scratch=scratch)
    assert outcome.returncode != 0, outcome.output
    assert "must be enforced" in outcome.output


def test_a_host_with_no_parser_fails_the_play_before_installing_anything(
    *, scratch: _Scratch
) -> None:
    (scratch.bin_dir / "apparmor_parser").unlink()
    outcome = _play(scratch=scratch)
    assert outcome.returncode != 0, outcome.output
    assert list(scratch.dest.iterdir()) == []


def test_ci_pool_reaches_the_role_ungated() -> None:
    entry = re.search(
        r"^    - role: apparmor_profile\n      tags: \[apparmor_profile\]\n(?P<next>.*)$",
        _PLAY.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert entry is not None
    assert not entry.group("next").startswith("      when:")
