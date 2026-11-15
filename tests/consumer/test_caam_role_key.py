"""Consumer-tier proof for the credential-rotation role key's authorized_keys entry.

Runs the caam_role_key role with the same pinned ``ansible-core`` as
``just ansible-drift`` against a fixture ``authorized_keys`` file: an undeclared key
changes nothing, check mode writes nothing, an apply adds exactly one marked
``restrict`` entry and preserves every other key, a second apply is a no-op, a
non-ed25519 key is refused before any write, and ``absent`` removes only the block.
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
_ROLE_NAME = "caam_role_key"
_HOST = "fixture-host"
_TIMEOUT_SECONDS = 600
_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixtureRoleKeyFixtureRoleKeyFixtureRoleK "
    "caam-role-key@credential-rotation-role"
)
_UNRELATED = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIUnrelatedKeyOne unrelated one\n"
    'from="198.51.100.4" ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCUnrelatedTwo unrelated two\n'
)
_BLOCK = (
    "# BEGIN ANSIBLE MANAGED caam_role_key\n"
    f"restrict {_KEY}\n"
    "# END ANSIBLE MANAGED caam_role_key\n"
)


def _ansible_core_pin() -> str:
    recipe = _JUSTFILE.read_text(encoding="utf-8")
    match = re.search(r"^ansible-drift \*args:\n(?P<body>(?:    .*\n)+)", recipe, re.MULTILINE)
    assert match is not None, "justfile must define the ansible-drift recipe"
    pin = re.search(r"ansible-core==[0-9][0-9A-Za-z.]*", match["body"])
    assert pin is not None, "ansible-drift must pin ansible-core"
    return pin[0]


def _run(
    *, root: Path, path: Path, key: str, check: bool, state: str = "present"
) -> subprocess.CompletedProcess[str]:
    inventory = root / "inventory.yml"
    inventory.write_text(
        "---\nall:\n  hosts:\n    fixture-host:\n      ansible_connection: local\n",
        encoding="utf-8",
    )
    play = root / "play.yml"
    play.write_text(
        "---\n- name: role key fixture\n  hosts: all\n  gather_facts: false\n"
        f"  roles:\n    - role: {_ROLE_NAME}\n",
        encoding="utf-8",
    )
    user = pwd.getpwuid(os.getuid()).pw_name
    variables = {
        "caam_role_key_public": key,
        "caam_role_key_user": user,
        "caam_role_key_path": str(path),
        "caam_role_key_become": False,
        "caam_role_key_state": state,
    }
    command = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook"]
    if check:
        command.extend(["--check", "--diff"])
    command.extend(["-i", str(inventory), "-e", json.dumps(variables), str(play)])
    environment = {
        key_: value
        for key_, value in os.environ.items()
        if key_ != "COVERAGE_PROCESS_START" and not key_.startswith("COV_CORE_")
    } | {
        "ANSIBLE_NOCOWS": "1",
        "ANSIBLE_RETRY_FILES_ENABLED": "False",
        "ANSIBLE_ROLES_PATH": str(_ROLES),
    }
    _ = grp.getgrgid(os.getgid())
    return subprocess.run(
        command,
        cwd=root,
        env=environment,
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


def _authorized_keys(*, root: Path) -> Path:
    path = root / "home" / "fixture" / ".ssh" / "authorized_keys"
    path.parent.mkdir(parents=True)
    path.write_text(_UNRELATED, encoding="utf-8")
    path.chmod(0o644)
    return path


def test_an_undeclared_role_key_changes_nothing(*, tmp_path: Path) -> None:
    """With the public half empty, the role is a no-op on the file."""
    path = _authorized_keys(root=tmp_path)

    assert _changed(result=_run(root=tmp_path, path=path, key="", check=False)) == 0
    assert path.read_text(encoding="utf-8") == _UNRELATED
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_a_declared_role_key_is_one_restricted_marked_entry_and_check_mode_writes_nothing(
    *, tmp_path: Path
) -> None:
    """Check mode reports and writes nothing; an apply adds the block once, idempotently."""
    path = _authorized_keys(root=tmp_path)

    assert _changed(result=_run(root=tmp_path, path=path, key=_KEY, check=True)) > 0
    assert path.read_text(encoding="utf-8") == _UNRELATED

    assert _changed(result=_run(root=tmp_path, path=path, key=_KEY, check=False)) > 0
    assert path.read_text(encoding="utf-8") == _UNRELATED + _BLOCK
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert _changed(result=_run(root=tmp_path, path=path, key=_KEY, check=False)) == 0


def test_absent_removes_only_the_role_key_block(*, tmp_path: Path) -> None:
    """The committed rollback leaves every unrelated key in place."""
    path = _authorized_keys(root=tmp_path)
    assert _changed(result=_run(root=tmp_path, path=path, key=_KEY, check=False)) > 0

    assert (
        _changed(result=_run(root=tmp_path, path=path, key=_KEY, check=False, state="absent")) > 0
    )
    assert path.read_text(encoding="utf-8") == _UNRELATED


@pytest.mark.parametrize(
    "key",
    [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCNotEd25519 not-ed25519",
        f"{_KEY}\nssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAISecondLine second",
    ],
)
def test_a_role_key_that_is_not_one_ed25519_line_is_refused_before_any_write(
    *, tmp_path: Path, key: str
) -> None:
    """A wrong key type or a smuggled second line never reaches the file."""
    path = _authorized_keys(root=tmp_path)

    result = _run(root=tmp_path, path=path, key=key, check=False)

    assert result.returncode != 0
    assert path.read_text(encoding="utf-8") == _UNRELATED
