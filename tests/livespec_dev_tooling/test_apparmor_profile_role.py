"""The `apparmor_profile` role makes the kernel hold each committed profile, and says when it does not.

Kernel 7.0.0-43 labels every non-privileged container `<profile>//&unconfined`,
and containerd's built-in default profile allows signals only to the bare name,
so a gate Job could not signal its own children (livespec-dev-tooling-ddy5xu).
The role now also holds containerd's default profile at node level. What a pod
is confined by is the policy the KERNEL holds, not the file on disk. The role
records, at its own load, the installed file's sha256 and the policy hash the
kernel then holds, and loads again whenever the node no longer matches that
record. It does NOT compare the kernel against a fresh compile: on the pool
nodes a skip-kernel-load compile hashes differently from the blob a real load
sends (measured on gamingpc-xubuntu, 2026-11-12), so the stand-in parser here
behaves the same way.

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
import shutil
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
_REJECT_MARKER = "fixture-reject-marker"
_BLOB_HEADER = b"fixture-kernel-blob\n"

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

# The stand-in parser. It logs every invocation.
#   `-Q -K -S <file>` prints the file as its "compiled policy"; touches nothing.
#       Its sha256 is NOT the hash a load records, as on a real node, so a role
#       that compared the kernel against a fresh compile would never converge.
#   `-Q -K <file>` validates: it rejects a file carrying the reject marker.
#   `-r -W <file>` records the policy as loaded, the way the kernel exposes it:
#       `<name>.<id>/raw_sha256` and `mode`, the mode from the state directory.
#       The hash is of the file behind a blob header, not of the file alone.
#   `-R` unloads the profile named by the definition on stdin.
# Anything else exits 64.
_PARSER_STAND_IN = """#!/bin/sh
state="$(dirname "$0")/../state"
printf '%s\\n' "$*" >> "$state/argv.log"
case "$1" in
  -Q)
    [ "$2" = -K ] || exit 64
    if [ "$3" = -S ]; then cat "$4"; exit 0; fi
    if grep -q 'fixture-reject-marker' "$3"; then echo "syntax error" >&2; exit 1; fi
    exit 0 ;;
  -R)
    name="$(sed -n 's/^profile \\([^ ]*\\) .*/\\1/p')"
    [ -n "$name" ] || exit 64
    rm -rf "$state/loaded/$name.7"
    exit 0 ;;
  -r)
    [ "$2" = -W ] || exit 64
    name="$(basename "$3")"
    mkdir -p "$state/loaded/$name.7"
    { printf 'fixture-kernel-blob\\n'; cat "$3"; } | sha256sum | cut -d' ' -f1 \\
      > "$state/loaded/$name.7/raw_sha256"
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

    def calls(self, *, flag: str) -> list[str]:
        log = self.state / "argv.log"
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return [line for line in lines if line.split()[0] == flag]

    def loads(self) -> list[str]:
        return self.calls(flag="-r")

    def unloads(self) -> list[str]:
        return self.calls(flag="-R")

    @property
    def records(self) -> Path:
        return self.root / "records"

    def loaded_policy(self, *, name: str) -> str:
        return (self.loaded / f"{name}.7" / "raw_sha256").read_text(encoding="utf-8").strip()

    def record(self, *, name: str) -> list[str]:
        """The record's two values: the installed file's sha256, the kernel's policy hash."""
        return (self.records / name).read_text(encoding="utf-8").split()

    def source_policy(self, *, name: str) -> str:
        return _kernel_policy(path=self.src / name)

    def source_record(self, *, name: str) -> list[str]:
        """The record a load of the source file must leave."""
        file_sha = hashlib.sha256((self.src / name).read_bytes()).hexdigest()
        return [file_sha, self.source_policy(name=name)]


def _kernel_policy(*, path: Path) -> str:
    """The hash the stand-in kernel exposes after a load of `path`."""
    return hashlib.sha256(_BLOB_HEADER + path.read_bytes()).hexdigest()


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


def _play(
    *,
    scratch: _Scratch,
    check: bool = False,
    names: tuple[str, ...] = _PROFILES,
    absent: tuple[str, ...] = (),
    committed_profiles: bool = False,
) -> _Outcome:
    """Run the role once; return its exit code and the host's `changed=` count.

    `committed_profiles` leaves the role's own profile list and source directory
    in force, so the run installs what the repository ships.
    """
    fixture_profiles = {
        "apparmor_profile_names": f"[{', '.join(names)}]",
        "apparmor_profile_src_dir": str(scratch.src),
    }
    host_vars = {
        **({} if committed_profiles else fixture_profiles),
        "apparmor_profile_absent": f"[{', '.join(absent)}]",
        "apparmor_profile_dest_dir": str(scratch.dest),
        "apparmor_profile_loaded_dir": str(scratch.loaded),
        "apparmor_profile_record_dir": str(scratch.records),
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


def _run(
    *,
    scratch: _Scratch,
    check: bool = False,
    names: tuple[str, ...] = _PROFILES,
    absent: tuple[str, ...] = (),
) -> int:
    """Run the role, require it to complete, and return the `changed=` count."""
    outcome = _play(scratch=scratch, check=check, names=names, absent=absent)
    assert outcome.returncode == 0, f"the role must complete:\n{outcome.output}"
    return outcome.changed


def test_a_fresh_node_gets_every_profile_installed_loaded_and_recorded(
    *, scratch: _Scratch
) -> None:
    # The recap counts tasks, not loop items: install, load and record.
    assert _run(scratch=scratch) == 3
    for name in _PROFILES:
        assert (scratch.dest / name).read_bytes() == (scratch.src / name).read_bytes()
        assert scratch.loaded_policy(name=name) == scratch.source_policy(name=name)
        assert scratch.record(name=name) == scratch.source_record(name=name)
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
    assert not scratch.records.exists()
    assert scratch.loads() == []


def test_a_drift_report_on_a_converged_node_shows_nothing(*, scratch: _Scratch) -> None:
    _run(scratch=scratch)
    assert _run(scratch=scratch, check=True) == 0


def test_a_policy_the_runtime_loaded_over_ours_is_reported_replaced_and_recorded_again(
    *, scratch: _Scratch
) -> None:
    """The file and the record still match, but the kernel holds someone else's policy."""
    _run(scratch=scratch)
    held = scratch.loaded / f"{_DOTTED}.7" / "raw_sha256"
    held.write_text(f"{_FOREIGN_POLICY}\n", encoding="utf-8")
    assert _run(scratch=scratch, check=True) == 1
    assert held.read_text(encoding="utf-8").strip() == _FOREIGN_POLICY
    assert scratch.record(name=_DOTTED) == scratch.source_record(name=_DOTTED)
    # The load and the record.
    assert _run(scratch=scratch) == 2
    assert scratch.loaded_policy(name=_DOTTED) == scratch.source_policy(name=_DOTTED)
    assert scratch.record(name=_DOTTED) == scratch.source_record(name=_DOTTED)
    assert scratch.loads()[-1] == f"-r -W {scratch.dest / _DOTTED}"
    assert len(scratch.loads()) == len(_PROFILES) + 1


def test_a_changed_profile_file_is_installed_and_reloaded_alone(*, scratch: _Scratch) -> None:
    _run(scratch=scratch)
    (scratch.src / _PLAIN).write_text(f"profile {_PLAIN} {{\n  # edited\n}}\n", encoding="utf-8")
    # Install, load and record.
    assert _run(scratch=scratch) == 3
    assert scratch.loaded_policy(name=_PLAIN) == scratch.source_policy(name=_PLAIN)
    assert scratch.record(name=_PLAIN) == scratch.source_record(name=_PLAIN)
    assert scratch.loads()[-1] == f"-r -W {scratch.dest / _PLAIN}"
    assert len(scratch.loads()) == len(_PROFILES) + 1


def test_a_loaded_profile_with_no_record_is_loaded_and_recorded(*, scratch: _Scratch) -> None:
    """A node that held the profile before this role kept records: the first apply."""
    _run(scratch=scratch)
    (scratch.records / _PLAIN).unlink()
    assert _run(scratch=scratch, check=True) == 1
    assert not (scratch.records / _PLAIN).exists()
    # The load and the record; the file itself is already installed.
    assert _run(scratch=scratch) == 2
    assert scratch.record(name=_PLAIN) == scratch.source_record(name=_PLAIN)
    assert scratch.loads()[-1] == f"-r -W {scratch.dest / _PLAIN}"
    assert _run(scratch=scratch) == 0
    assert len(scratch.loads()) == len(_PROFILES) + 1


def test_a_recorded_profile_the_kernel_no_longer_holds_is_loaded_again(
    *, scratch: _Scratch
) -> None:
    _run(scratch=scratch)
    shutil.rmtree(scratch.loaded / f"{_DOTTED}.7")
    assert _run(scratch=scratch) == 2
    assert scratch.loaded_policy(name=_DOTTED) == scratch.source_policy(name=_DOTTED)
    assert scratch.loads()[-1] == f"-r -W {scratch.dest / _DOTTED}"


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


def test_a_profile_the_parser_rejects_is_not_installed_and_fails_the_play(
    *, scratch: _Scratch
) -> None:
    """The candidate is compiled before it replaces the file the next boot loads."""
    _run(scratch=scratch)
    good = (scratch.dest / _PLAIN).read_bytes()
    (scratch.src / _PLAIN).write_text(f"profile {_PLAIN} {{ {_REJECT_MARKER}\n", encoding="utf-8")
    outcome = _play(scratch=scratch)
    assert outcome.returncode != 0, outcome.output
    assert (scratch.dest / _PLAIN).read_bytes() == good
    assert len(scratch.loads()) == len(_PROFILES)


def test_a_rejected_profile_never_reaches_a_fresh_node(*, scratch: _Scratch) -> None:
    (scratch.src / _DOTTED).write_text(f"profile {_DOTTED} {{ {_REJECT_MARKER}\n", encoding="utf-8")
    outcome = _play(scratch=scratch, names=(_DOTTED,))
    assert outcome.returncode != 0, outcome.output
    assert list(scratch.dest.iterdir()) == []
    assert scratch.loads() == []


def test_the_committed_profiles_install_and_load_under_their_own_names(
    *, scratch: _Scratch
) -> None:
    """The role's own list and source directory, with only the host side stood in."""
    outcome = _play(scratch=scratch, committed_profiles=True)
    assert outcome.returncode == 0, outcome.output
    installed = sorted(scratch.dest.iterdir())
    assert installed
    for path in installed:
        # The role installs, probes and unloads each profile under its file name.
        declared = re.findall(r"^profile (\S+) ", path.read_text(encoding="utf-8"), re.MULTILINE)
        assert declared == [path.name]
        policy = _kernel_policy(path=path)
        assert scratch.loaded_policy(name=path.name) == policy
        assert scratch.record(name=path.name)[1] == policy
    assert sorted(scratch.loads()) == [f"-r -W {path}" for path in installed]


def test_an_absent_profile_is_unloaded_and_its_file_and_record_removed(
    *, scratch: _Scratch
) -> None:
    _run(scratch=scratch)
    # The unload task and the removal task.
    assert _run(scratch=scratch, names=(_PLAIN,), absent=(_DOTTED,)) == 2
    assert not (scratch.dest / _DOTTED).exists()
    assert not (scratch.loaded / f"{_DOTTED}.7").exists()
    assert not (scratch.records / _DOTTED).exists()
    assert scratch.record(name=_PLAIN) == scratch.source_record(name=_PLAIN)
    assert len(scratch.unloads()) == 1
    # The profile that stays is untouched.
    assert (scratch.dest / _PLAIN).exists()
    assert scratch.loaded_policy(name=_PLAIN) == scratch.source_policy(name=_PLAIN)
    assert len(scratch.loads()) == len(_PROFILES)


def test_a_second_apply_of_an_absent_profile_changes_nothing(*, scratch: _Scratch) -> None:
    _run(scratch=scratch)
    _run(scratch=scratch, names=(_PLAIN,), absent=(_DOTTED,))
    assert _run(scratch=scratch, names=(_PLAIN,), absent=(_DOTTED,)) == 0
    assert len(scratch.unloads()) == 1


def test_a_drift_report_shows_a_pending_removal_and_writes_nothing(*, scratch: _Scratch) -> None:
    _run(scratch=scratch)
    # The probe standing in for the skipped unload, and the pending removal.
    assert _run(scratch=scratch, check=True, names=(_PLAIN,), absent=(_DOTTED,)) == 2
    assert (scratch.dest / _DOTTED).exists()
    assert scratch.loaded_policy(name=_DOTTED) == scratch.source_policy(name=_DOTTED)
    assert scratch.record(name=_DOTTED) == scratch.source_record(name=_DOTTED)
    assert scratch.unloads() == []


def test_a_profile_named_as_both_present_and_absent_fails_before_anything_is_written(
    *, scratch: _Scratch
) -> None:
    outcome = _play(scratch=scratch, absent=(_DOTTED,))
    assert outcome.returncode != 0, outcome.output
    assert "is in both" in outcome.output
    assert list(scratch.dest.iterdir()) == []
    assert scratch.loads() == []
    assert scratch.unloads() == []


def test_ci_pool_reaches_the_role_ungated() -> None:
    entry = re.search(
        r"^    - role: apparmor_profile\n      tags: \[apparmor_profile\]\n(?P<next>.*)$",
        _PLAY.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert entry is not None
    assert not entry.group("next").startswith("      when:")
