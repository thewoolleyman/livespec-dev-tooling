"""`ansible/dev-host.yml` stages each pinned Fabro client build and refuses an unsafe entry.

Covers the `SPECIFICATION/scenarios.md` scenario of that name (v088). Its sibling
`test_dev_host_fabro_client_builds_section` holds the committed declaration and
the role's documentation to the `## Dev host Fabro client builds` section those
Thens exercise. Work-item `livespec-dev-tooling-lirki2`.

WHY THE ROLE IS CONVERGED AND NOT READ. Every claim the scenario makes is a claim
about what a converge DOES: whether the build arrives at its path with the right
mode and owner, whether a second converge changes nothing, whether a digest that
no longer matches refuses while leaving the earlier build in place, and whether
each unsafe entry is refused BEFORE anything is written. None of that is settled
by what the YAML says — it is decided by Jinja resolution, by Ansible's task
ordering, and by `readlink`'s and `stat`'s answers about a real filesystem. So the
committed role runs, under the same `ansible-core` pin `just ansible-apply`
resolves, exactly as the sibling `test_fabro_factory_registry_role` runs that
role.

AND IT IS A REAL CONVERGE, NOT `--check`. That sibling uses `--check` with a
re-pointed destination because its claims are about RENDERED BYTES. These claims
are about FILE STATE — a mode, an owner, an inode that survived a rename, a
second run that changed nothing — and `--check` applies none of it. Every path a
converge below touches is derived from that run's own `tmp_path` and the owner is
the account pytest already runs as, so the converge needs no privilege and can
reach nothing of the machine's: the hazard `tests_host_path_free` exists to
refuse is not "a test that writes" but "a test whose verdict moves with the host".

WHY EVERY REFUSAL ARM ALSO ASSERTS THAT NOTHING WAS WRITTEN. The section's
"Refused before writing" clause is an ORDERING claim, and a refusal that arrives
after an earlier entry's build went live satisfies the words "it refused" while
leaving the host in a state no inventory describes. So each arm declares a VALID
entry beside the unsafe one and asserts that valid entry's path is still absent.
That entry would install cleanly on its own, so a role which validated per-entry
and installed as it went leaves it behind and fails here.

WHY THE DRIFT ARM REWRITES THE SOURCE RATHER THAN THE DIGEST. That is the drift
which actually happens: the source path is inside a mutable state tree under a
home directory, so the build there changes without anyone editing the inventory.
Rewriting the declared digest instead would prove only that two strings differ.
"""

from __future__ import annotations

import grp
import hashlib
import json
import os
import pwd
import re
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration


_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ANSIBLE = _REPO_ROOT / "ansible"
_PLAYBOOK = _ANSIBLE / "dev-host.yml"
_LEGACY_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"

_TIMEOUT_SECONDS = 600
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==\d+\.\d+\.\d+")
_ROLE_TAG = "fabro_client"
_OTHER_DEV_HOST_TAG = "dev_host_retention"
_VALIDATE_TASK = "Validate every declared Fabro client build before anything is written"

# One synthetic group, named for what it is. The real `dev_hosts` name is not
# reused: a fixture answering to it could be mistaken for the committed inventory
# in a failure message, and nothing here is about the real group.
_GROUP = "synthetic_dev_hosts"
_HOST = "a-synthetic-dev-host"

_PLAY = f"""---
- name: Stage the synthetic host's declared Fabro client builds
  hosts: {_GROUP}
  gather_facts: false
  roles:
    - role: fabro_client
"""

# `ansible_connection: local` is also what makes the synthetic host the CONTROL
# NODE, which is how the committed inventory binds `vps` — so the source-denotes-
# a-path refusal is reachable here exactly as it is there. `ansible_become: false`
# overrides the role's task-level `become: true` (a connection variable wins on
# ansible-core 2.21.4), so the converge needs no privilege.
_INVENTORY = f"""---
{_GROUP}:
  hosts:
    {_HOST}:
      ansible_connection: local
      ansible_become: false
"""


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


def _ansible(*, cwd: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """`ansible-playbook` at the pinned version, with the committed roles on its path."""
    return subprocess.run(
        ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=os.environ | {"ANSIBLE_ROLES_PATH": str(_ANSIBLE / "roles"), "ANSIBLE_NOCOWS": "1"},
    )


def _digest(*, text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _owner() -> str:
    """The account this test already runs as — the one owner it can assert on.

    Read from the process, never from a host file: the role asks the host for this
    account's primary group, so the owner has to be an account that really exists,
    and the running one is the only such account a test may assume.
    """
    return pwd.getpwuid(os.getuid()).pw_name


def _primary_group() -> str:
    return grp.getgrgid(pwd.getpwnam(_owner()).pw_gid).gr_name


def _staged(*, root: Path, name: str, body: str) -> dict[str, str]:
    """One control-node source under `root`, and the entry that declares it.

    The source is plain text rather than a binary: nothing in the role executes
    it, every rule it exercises is about digests, modes, owners and inodes, and a
    readable body makes a failure message say WHICH build landed.
    """
    source = root / "control-node" / name / "fabro"
    source.parent.mkdir(parents=True, exist_ok=True)
    _ = source.write_text(body, encoding="utf-8")
    return {
        "path": str(root / "host" / name / "fabro"),
        "source": str(source),
        "sha256": _digest(text=body),
    }


def _converge(
    *,
    tmp_path: Path,
    name: str,
    builds: list[dict[str, str]],
    host_vars: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Converge the committed role over the synthetic host; return the whole run."""
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    inventory = root / "hosts.yml"
    _ = inventory.write_text(_INVENTORY, encoding="utf-8")
    play = root / "play.yml"
    _ = play.write_text(_PLAY, encoding="utf-8")
    extra: dict[str, object] = {
        "fabro_client_builds": builds,
        "fabro_client_owner": _owner(),
        **(host_vars or {}),
    }
    return _ansible(cwd=root, argv=["-i", str(inventory), "-e", json.dumps(extra), str(play)])


def _changed(*, run: subprocess.CompletedProcess[str]) -> int:
    """The host's `changed=` count out of the play recap."""
    recap = re.search(rf"^{re.escape(_HOST)}\s*:.*?changed=(?P<n>\d+)", run.stdout, re.MULTILINE)
    assert recap is not None, run.stdout + run.stderr
    return int(recap["n"])


def _list_tasks(*, tags: list[str] | None) -> str:
    argv = ["-i", str(_LEGACY_INVENTORY), "--list-tasks", str(_PLAYBOOK)]
    if tags is not None:
        argv += ["--tags", ",".join(tags)]
    done = _ansible(cwd=_REPO_ROOT, argv=argv)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def _unsafe_arm(
    *, arm: str, root: Path, unsafe: dict[str, str]
) -> tuple[dict[str, str], dict[str, object]]:
    """The unsafe entry of one arm, and the host variables it needs.

    Split in two because the arms are two KINDS. The shape arms are refused from
    the declaration alone and need no host at all; the rest are refused because of
    something the host holds, which has to be set up beside the entry that names
    it — and reading the pair together is how a reader sees what makes each unsafe.
    """
    shaped = _unsafe_shape(arm=arm, unsafe=unsafe)
    if shaped is not None:
        return shaped, {}
    return _unsafe_host_state(arm=arm, root=root, unsafe=unsafe)


def _unsafe_shape(*, arm: str, unsafe: dict[str, str]) -> dict[str, str] | None:
    """The arms whose entry is unsafe on its own terms, or `None` for the others."""
    if arm == "relative":
        return {**unsafe, "path": "relative/fabro"}
    if arm == "short-digest":
        return {**unsafe, "sha256": "abc123"}
    if arm == "missing-key":
        return {key: value for key, value in unsafe.items() if key != "source"}
    return None


def _unsafe_host_state(
    *, arm: str, root: Path, unsafe: dict[str, str]
) -> tuple[dict[str, str], dict[str, object]]:
    """The arms whose unsafety is a fact about the host, set up here beside the entry."""
    if arm == "duplicate":
        target = root / "host" / "valid"
        target.mkdir(parents=True, exist_ok=True)
        alias = root / "host" / "alias"
        alias.symlink_to(target)
        return {**unsafe, "path": str(alias / "fabro")}, {}
    if arm == "symlink":
        link = Path(unsafe["path"])
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(unsafe["source"])
        return unsafe, {}
    if arm == "server-binary":
        home = root / "server-home"
        return {**unsafe, "path": str(home / ".fabro" / "bin" / "fabro")}, {
            "fabro_server_host_home": str(home),
            "fabro_server_instances": [{"unit_name": "fabro-server", "port": 32276}],
        }
    if arm == "incoming-clash":
        # A leftover symbolic link where this entry's staging file goes, pointing
        # at the valid entry's path — the shape a hand repair leaves behind. The
        # atomic write would then land ON a live build, destroying the one property
        # the stage-verify-rename exists to give.
        staging = Path(f"{unsafe['path']}.incoming")
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.symlink_to(root / "host" / "valid" / "fabro")
        return unsafe, {}
    if arm == "ancestor":
        blocker = root / "host" / "blocked"
        blocker.parent.mkdir(parents=True, exist_ok=True)
        _ = blocker.write_text("not a directory\n", encoding="utf-8")
        return {**unsafe, "path": str(blocker / "deeper" / "fabro")}, {}
    assert arm == "source-is-path", f"unknown refusal arm {arm!r}"
    return {**unsafe, "path": unsafe["source"]}, {}


def test_a_converge_installs_each_declared_build_and_a_second_one_changes_nothing(
    *, tmp_path: Path
) -> None:
    """The scenario's first two Thens, over two converges of the committed role.

    TWO entries, because one would not exercise the duplicate-path comparison the
    role runs on every converge, and because the scenario's Given is two. The
    second converge's `changed=0` is the whole of the second Then: a role that
    re-copied an undrifted build, or re-chowned a directory it does not own,
    reports a change here and the inventory would no longer describe a settled
    host.
    """
    builds = [
        _staged(root=tmp_path / "first", name="legacy", body="legacy-client-0.254\n"),
        _staged(root=tmp_path / "first", name="petri", body="petri-client-0.382\n"),
    ]
    first = _converge(tmp_path=tmp_path, name="first", builds=builds)
    assert first.returncode == 0, first.stdout + first.stderr
    for entry in builds:
        placed = Path(entry["path"])
        assert placed.is_file(), f"{entry['path']} must hold the declared build:\n{first.stdout}"
        assert _digest(text=placed.read_text(encoding="utf-8")) == entry["sha256"]
        assert oct(placed.stat().st_mode)[-4:] == "0755", f"{entry['path']} must be mode 0755"
        assert pwd.getpwuid(placed.stat().st_uid).pw_name == _owner()
        assert grp.getgrgid(placed.stat().st_gid).gr_name == _primary_group()
        assert not Path(f"{entry['path']}.incoming").exists(), (
            "the staging file must not survive the rename: a leftover `.incoming` is a "
            "whole copy of the build that nothing names and nothing retires"
        )
    second = _converge(tmp_path=tmp_path, name="first", builds=builds)
    assert second.returncode == 0, second.stdout + second.stderr
    assert _changed(run=second) == 0, (
        "a second converge with unchanged inventory on an undrifted host must change "
        f"nothing at all:\n{second.stdout}"
    )


def test_a_source_that_no_longer_hashes_to_its_digest_refuses_and_keeps_both_builds(
    *, tmp_path: Path
) -> None:
    """The scenario's second Given and both its Thens, driven through a real drift.

    Both paths are asserted to still hold the FIRST converge's builds — not merely
    the refused one — because a role that refused per-entry would have replaced the
    other on the way past.
    """
    builds = [
        _staged(root=tmp_path / "drift", name="legacy", body="legacy-client-0.254\n"),
        _staged(root=tmp_path / "drift", name="petri", body="petri-client-0.382\n"),
    ]
    installed = _converge(tmp_path=tmp_path, name="drift", builds=builds)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    _ = Path(builds[1]["source"]).write_text("petri-rebuilt-differently\n", encoding="utf-8")
    refused = _converge(tmp_path=tmp_path, name="drift", builds=builds)
    assert refused.returncode != 0
    assert (
        builds[1]["source"] in refused.stdout
    ), f"the refusal must name the entry it refused:\n{refused.stdout}"
    for entry in builds:
        held = Path(entry["path"]).read_text(encoding="utf-8")
        assert _digest(text=held) == entry["sha256"], (
            f"{entry['path']} must still be the build the earlier converge installed; a "
            f"refusal that replaced it first is not a refusal:\n{refused.stdout}"
        )


@pytest.mark.parametrize(
    ("arm", "reason"),
    [
        ("duplicate", "two entries' paths denote one file through a symlinked parent"),
        ("symlink", "the declared path is itself a symbolic link on the host"),
        ("server-binary", "the declared path denotes a fabro_server instance's binary_path"),
        ("incoming-clash", "the declared path's staging file denotes another entry's path"),
        ("source-is-path", "the source resolves to its own path on the control node"),
        ("ancestor", "an ancestor of the declared path exists and is not a directory"),
        ("relative", "the declared path is not absolute"),
        ("short-digest", "the declared digest is not 64 hexadecimal digits"),
        ("missing-key", "the entry omits its source"),
    ],
)
def test_each_unsafe_entry_is_refused_before_anything_is_written(
    *, tmp_path: Path, arm: str, reason: str
) -> None:
    """The scenario's third Given — every member of it — and the shape rules beside it."""
    root = tmp_path / arm
    valid = _staged(root=root, name="valid", body="valid-client\n")
    unsafe, host_vars = _unsafe_arm(
        arm=arm, root=root, unsafe=_staged(root=root, name="unsafe", body="unsafe-client\n")
    )
    run = _converge(tmp_path=tmp_path, name=arm, builds=[valid, unsafe], host_vars=host_vars)
    assert run.returncode != 0, f"{reason} must refuse the converge:\n{run.stdout}"
    assert not Path(valid["path"]).exists(), (
        f"{reason} must refuse BEFORE anything is written, so the valid entry beside it "
        f"must not have been installed:\n{run.stdout}"
    )


def test_the_dev_host_play_reaches_the_role_and_it_carries_its_own_tag() -> None:
    """The section's "a role that `ansible/dev-host.yml` includes" clause.

    Read off a real `--list-tasks` run of the committed play rather than off its
    text, so the role has to resolve and reach its own tasks; and asserted absent
    under another dev-host tag, so `--tags fabro_client` converges this and only
    this.
    """
    every = _list_tasks(tags=None)
    assert _VALIDATE_TASK in every, (
        "ansible/dev-host.yml must include the fabro_client role: a hand-staged client "
        f"build is not provisioned state and no drift report sees it:\n{every}"
    )
    assert _ROLE_TAG not in _list_tasks(tags=[_OTHER_DEV_HOST_TAG]), (
        "the role must carry its own tag, so converging one other dev-host control does "
        "not restage a client build and `--tags fabro_client` can converge it alone"
    )
