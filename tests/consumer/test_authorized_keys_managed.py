"""Consumer-tier proof for managed, forward-only OpenSSH authorized keys.

The role writes into an account's existing ``authorized_keys`` file, which is
not exclusively Ansible-owned.  These fixtures therefore execute the role with
the same pinned ``ansible-core`` as ``just ansible-drift`` and hold its actual
file effects: check mode does not write, applies change only marked entries or
explicitly-retired key blobs, and a second apply is a no-op.

The live OpenSSH refusal probes require the VPS and are host-captured.  The
offline assertions here cover the committed provisioning behaviour that leads
up to those probes.
"""

from __future__ import annotations

import grp
import json
import os
import pwd
import re
import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLES = _REPO_ROOT / "ansible" / "roles"
_ROLE = _ROLES / "authorized_keys_managed"
_ROLE_NAME = "authorized_keys_managed"
_HOST = "fixture-host"
_TIMEOUT_SECONDS = 600
_MARKER = "# {mark} ANSIBLE MANAGED authorized_keys_managed: {name}"
_DOLT_PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBcvdQPDguJ+Yq79xWTm4ZqBcm8J1MsZLsr/ah3IAo9 "
    "hetzner-xubuntu dolt-tunnel"
)
_RETIRED_BLOB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _ansible_core_pin() -> str:
    recipe = _JUSTFILE.read_text(encoding="utf-8")
    match = re.search(r"^ansible-drift \*args:\n(?P<body>(?:    .*\n)+)", recipe, re.MULTILINE)
    assert match is not None, "justfile must define the ansible-drift recipe"
    pin = re.search(r"ansible-core==[0-9][0-9A-Za-z.]*", match["body"])
    assert pin is not None, "ansible-drift must pin ansible-core"
    return pin[0]


def _fixture_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {
        "ANSIBLE_NOCOWS": "1",
        "ANSIBLE_RETRY_FILES_ENABLED": "False",
        "ANSIBLE_ROLES_PATH": str(_ROLES),
    }


def _fixture_vars(
    *, path: Path, entries: list[dict[str, str]], retired: list[str]
) -> dict[str, object]:
    user = pwd.getpwuid(os.getuid()).pw_name
    return {
        "authorized_keys_managed_entries": entries,
        "authorized_keys_managed_group": grp.getgrgid(os.getgid()).gr_name,
        "authorized_keys_managed_path": str(path),
        "authorized_keys_managed_retired_keys": retired,
        "authorized_keys_managed_user": user,
    }


def _run(
    *, root: Path, path: Path, entries: list[dict[str, str]], retired: list[str], check: bool
) -> subprocess.CompletedProcess[str]:
    inventory = root / "inventory.yml"
    inventory.write_text(
        "---\nall:\n  hosts:\n    fixture-host:\n      ansible_connection: local\n      ansible_become: false\n",
        encoding="utf-8",
    )
    play = root / "play.yml"
    play.write_text(
        "---\n- name: authorized keys fixture\n  hosts: all\n  gather_facts: false\n"
        f"  roles:\n    - role: {_ROLE_NAME}\n",
        encoding="utf-8",
    )
    command = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook"]
    if check:
        command.extend(["--check", "--diff"])
    command.extend(
        [
            "-i",
            str(inventory),
            "-e",
            json.dumps(_fixture_vars(path=path, entries=entries, retired=retired)),
            str(play),
        ]
    )
    return subprocess.run(
        command,
        cwd=root,
        env=_fixture_environment(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )


def _changed(*, result: subprocess.CompletedProcess[str]) -> int:
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    recap = re.search(rf"^{_HOST}\s*:.*?\bchanged=(?P<count>\d+)", output, re.MULTILINE)
    assert recap is not None, output
    return int(recap["count"])


def _entry(
    *, name: str = "hetzner-xubuntu-dolt-tunnel", key: str = _DOLT_PUBLIC_KEY
) -> dict[str, str]:
    return {"name": name, "permitopen": "127.0.0.1:3307", "public_key": key}


def _expected_block(*, entry: dict[str, str]) -> str:
    return "\n".join(
        [
            _MARKER.format(mark="BEGIN", name=entry["name"]),
            'restrict,port-forwarding,permitopen="127.0.0.1:3307",'
            'permitlisten="invalid.invalid:1",'
            'command="/usr/bin/setpriv --pdeathsig KILL /usr/bin/sleep infinity" '
            + entry["public_key"],
            _MARKER.format(mark="END", name=entry["name"]),
            "",
        ]
    )


def _authorized_keys(*, root: Path, text: str) -> Path:
    path = root / "home" / "fixture" / ".ssh" / "authorized_keys"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o644)
    return path


def test_a_managed_forward_only_entry_preserves_unrelated_keys_and_check_mode_writes_nothing(
    *, tmp_path: Path
) -> None:
    """The declared local forward is narrow, marked, repeatable, and non-invasive."""
    assert _ROLE.is_dir(), f"{_ROLE_NAME} must exist before it can converge an authorized_keys file"
    unrelated = (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIUnrelatedKeyOne unrelated one\n"
        'from="198.51.100.4" ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCUnrelatedTwo unrelated two\n'
    )
    path = _authorized_keys(root=tmp_path, text=unrelated)
    entry = _entry()

    check = _run(root=tmp_path, path=path, entries=[entry], retired=[], check=True)

    assert _changed(result=check) > 0
    assert path.read_text(encoding="utf-8") == unrelated
    assert stat.S_IMODE(path.stat().st_mode) == 0o644

    assert (
        _changed(result=_run(root=tmp_path, path=path, entries=[entry], retired=[], check=False))
        > 0
    )
    assert path.read_text(encoding="utf-8") == unrelated + _expected_block(entry=entry)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert (
        _changed(result=_run(root=tmp_path, path=path, entries=[entry], retired=[], check=False))
        == 0
    )


def test_a_declared_retired_blob_removes_only_its_hand_placed_line(*, tmp_path: Path) -> None:
    """Retirement keys identify a public key's type and body, never its mutable options."""
    unrelated_before = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIUnrelatedKeyOne unrelated one\n"
    retired_line = (
        'restrict,port-forwarding,permitlisten="127.0.0.1:2223",command="/bin/false" '
        + _RETIRED_BLOB
        + " homelab-debug-tunnel\n"
    )
    unrelated_after = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCUnrelatedTwo unrelated two\n"
    original = unrelated_before + retired_line + unrelated_after
    path = _authorized_keys(root=tmp_path, text=original)

    check = _run(root=tmp_path, path=path, entries=[], retired=[_RETIRED_BLOB], check=True)

    assert _changed(result=check) > 0
    assert path.read_text(encoding="utf-8") == original
    assert (
        _changed(
            result=_run(root=tmp_path, path=path, entries=[], retired=[_RETIRED_BLOB], check=False)
        )
        > 0
    )
    assert path.read_text(encoding="utf-8") == unrelated_before + unrelated_after
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert (
        _changed(
            result=_run(root=tmp_path, path=path, entries=[], retired=[_RETIRED_BLOB], check=False)
        )
        == 0
    )


@pytest.mark.parametrize("check", [False, True])
def test_a_key_cannot_be_managed_and_retired_in_the_same_converge(
    *, tmp_path: Path, check: bool
) -> None:
    """The conflict fails before either check mode or an apply can touch the file."""
    original = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIUnrelatedKeyOne unrelated one\n"
    path = _authorized_keys(root=tmp_path, text=original)
    entry = _entry()
    key_blob = " ".join(entry["public_key"].split()[:2])

    result = _run(root=tmp_path, path=path, entries=[entry], retired=[key_blob], check=check)

    assert result.returncode != 0
    assert key_blob in result.stdout + result.stderr
    assert path.read_text(encoding="utf-8") == original
