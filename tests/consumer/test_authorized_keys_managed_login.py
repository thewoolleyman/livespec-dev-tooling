"""Consumer-tier proof for managed ordinary-login OpenSSH authorized keys.

The role writes into an account's existing ``authorized_keys`` file, which is
not exclusively Ansible-owned.  These fixtures therefore execute the role with
the same pinned ``ansible-core`` as ``just ansible-drift`` and hold its actual
file effects: check mode does not write, applies change only marked entries or an adopted
hand-placed line for a declared blob, and a second apply is a no-op.
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
_ROLE = _ROLES / "authorized_keys_managed_login"
_ROLE_NAME = "authorized_keys_managed_login"
_HOST = "fixture-host"
_TIMEOUT_SECONDS = 600
_MARKER = "# {mark} ANSIBLE MANAGED authorized_keys_managed_login: {name}"
_KEY_BLOB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDvo4a+h0iJJh98xFo0369SmLAhtkEddesiVlnGIR2HZ"
_PUBLIC_KEY = _KEY_BLOB + " ubuntu@hetzner-xubuntu"


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


def _fixture_vars(*, path: Path, entries: list[dict[str, str]]) -> dict[str, object]:
    user = pwd.getpwuid(os.getuid()).pw_name
    return {
        "authorized_keys_managed_login_entries": entries,
        "authorized_keys_managed_login_group": grp.getgrgid(os.getgid()).gr_name,
        "authorized_keys_managed_login_path": str(path),
        "authorized_keys_managed_login_user": user,
    }


def _run(
    *, root: Path, path: Path, entries: list[dict[str, str]], check: bool
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
            json.dumps(_fixture_vars(path=path, entries=entries)),
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


def _entry() -> dict[str, str]:
    return {"name": "hetzner-xubuntu-session", "public_key": _PUBLIC_KEY}


def _expected_block(*, entry: dict[str, str]) -> str:
    return "\n".join(
        [
            _MARKER.format(mark="BEGIN", name=entry["name"]),
            "no-X11-forwarding " + entry["public_key"],
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


_UNRELATED = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIUnrelatedKeyOne unrelated one\n"
    'from="198.51.100.4" ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCUnrelatedTwo unrelated two\n'
)


def test_a_managed_login_entry_preserves_unrelated_keys_and_check_mode_writes_nothing(
    *, tmp_path: Path
) -> None:
    """The login key is marked, appended after unrelated keys, and check mode writes nothing."""
    assert _ROLE.is_dir(), f"{_ROLE_NAME} must exist before it can converge a file"
    path = _authorized_keys(root=tmp_path, text=_UNRELATED)
    entry = _entry()

    check = _run(root=tmp_path, path=path, entries=[entry], check=True)

    assert _changed(result=check) > 0
    assert path.read_text(encoding="utf-8") == _UNRELATED
    assert stat.S_IMODE(path.stat().st_mode) == 0o644

    assert _changed(result=_run(root=tmp_path, path=path, entries=[entry], check=False)) > 0
    assert path.read_text(encoding="utf-8") == _UNRELATED + _expected_block(entry=entry)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_second_apply_is_a_no_op(*, tmp_path: Path) -> None:
    """Adoption never deletes the managed line, so a repeat apply changes nothing."""
    path = _authorized_keys(root=tmp_path, text=_UNRELATED)
    entry = _entry()

    assert _changed(result=_run(root=tmp_path, path=path, entries=[entry], check=False)) > 0
    after_first = path.read_text(encoding="utf-8")

    assert _changed(result=_run(root=tmp_path, path=path, entries=[entry], check=False)) == 0
    assert path.read_text(encoding="utf-8") == after_first


def test_an_unmarked_line_for_the_same_blob_is_replaced_without_a_duplicate(
    *, tmp_path: Path
) -> None:
    """A hand-placed line for the declared blob is adopted into the marked entry."""
    original = _UNRELATED + _PUBLIC_KEY + "\n"
    path = _authorized_keys(root=tmp_path, text=original)
    entry = _entry()

    assert _changed(result=_run(root=tmp_path, path=path, entries=[entry], check=False)) > 0

    assert path.read_text(encoding="utf-8") == _UNRELATED + _expected_block(entry=entry)
    assert path.read_text(encoding="utf-8").count(_KEY_BLOB) == 1


def test_an_absent_entry_removes_only_its_block(*, tmp_path: Path) -> None:
    """state: absent is the rollback: the marked block goes, other lines stay."""
    path = _authorized_keys(root=tmp_path, text=_UNRELATED)
    entry = _entry()
    _changed(result=_run(root=tmp_path, path=path, entries=[entry], check=False))

    gone = entry | {"state": "absent"}
    assert _changed(result=_run(root=tmp_path, path=path, entries=[gone], check=False)) > 0

    assert path.read_text(encoding="utf-8") == _UNRELATED


def test_empty_account_vars_refuse_before_changing_anything(*, tmp_path: Path) -> None:
    """With the account, group and path empty the role refuses and writes nothing."""
    path = _authorized_keys(root=tmp_path, text=_UNRELATED)
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(
        "---\nall:\n  hosts:\n    fixture-host:\n      ansible_connection: local\n      ansible_become: false\n",
        encoding="utf-8",
    )
    play = tmp_path / "play.yml"
    play.write_text(
        "---\n- name: refusal fixture\n  hosts: all\n  gather_facts: false\n"
        f"  roles:\n    - role: {_ROLE_NAME}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", "-i", str(inventory), str(play)],
        cwd=tmp_path,
        env=_fixture_environment(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )

    assert result.returncode != 0
    assert "must be declared" in result.stdout + result.stderr
    assert path.read_text(encoding="utf-8") == _UNRELATED


@pytest.mark.parametrize(
    "bad_key",
    ["", "ssh-ed25519", "notakey AAAAC3Nza", "ssh-ed25519 not*base64!", "x y"],
)
@pytest.mark.parametrize("check", [False, True])
def test_a_malformed_public_key_refuses_and_leaves_the_file_unchanged(
    *, tmp_path: Path, bad_key: str, check: bool
) -> None:
    """A key that is not a type plus a base64 body never reaches the adopt regexp."""
    original = _UNRELATED + "\n"
    path = _authorized_keys(root=tmp_path, text=original)
    entry = {"name": "bad", "public_key": bad_key}

    result = _run(root=tmp_path, path=path, entries=[entry], check=check)

    assert result.returncode != 0
    assert "not a key type followed by a base64 body" in result.stdout + result.stderr
    assert path.read_text(encoding="utf-8") == original


def test_placing_the_block_before_adopting_keeps_one_copy_and_is_repeatable(
    *, tmp_path: Path
) -> None:
    """A hand-placed line in the middle is replaced by the block; a repeat apply changes nothing."""
    hand = _PUBLIC_KEY + " hand placed\n"
    original = (
        _UNRELATED.splitlines(keepends=True)[0] + hand + _UNRELATED.splitlines(keepends=True)[1]
    )
    path = _authorized_keys(root=tmp_path, text=original)
    entry = _entry()

    assert _changed(result=_run(root=tmp_path, path=path, entries=[entry], check=False)) > 0

    final = path.read_text(encoding="utf-8")
    assert final == _UNRELATED + _expected_block(entry=entry)
    assert final.count(_KEY_BLOB) == 1
    assert _changed(result=_run(root=tmp_path, path=path, entries=[entry], check=False)) == 0
