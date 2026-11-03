"""The dev-host play disables only proactive memory compaction.

`kcompactd0` consumed about 106% of one CPU on the development VPS while
proactive compaction repeatedly chased a fragmentation target that pinned and
unmovable pages could not meet.  The persistent remedy is a documented sysctl
drop-in: it prevents that proactive pass while preserving on-demand compaction
at watermark pressure and direct compaction.

This runs the committed role against a temporary sysctl directory.  A fake
``sysctl`` executable makes the handler observable without attempting to
write the sandbox's deliberately read-only ``/proc/sys`` namespace.  Therefore
the test proves the repository-owned parts of the contract — bytes, application
path, and idempotence — while the post-play kernel reading remains host-captured.
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

pytestmark = pytest.mark.integration


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLE_NAME = "dev_host_compaction"
_ROLE = _ANSIBLE / "roles" / _ROLE_NAME
_PLAY = _ANSIBLE / "dev-host.yml"
_DROPIN_NAME = "90-dev-host-disable-proactive-compaction.conf"
_DROPIN_LINE = "vm.compaction_proactiveness = 0"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_HOST = "synthetic-dev-host"
_TIMEOUT_SECONDS = 600


def _ansible_core_pin() -> str:
    """The exact ansible-core version that the committed apply recipe uses."""
    recipe = _JUSTFILE.read_text(encoding="utf-8")
    match = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        recipe,
        re.MULTILINE,
    )
    assert match is not None, "justfile must define the ansible-apply recipe"
    pin = _ANSIBLE_CORE_PIN.search(match["body"])
    assert pin is not None, "ansible-apply must pin ansible-core"
    return pin[0]


def _converge(
    *, root: Path, sysctl_dir: Path, sysctl_bin: Path
) -> subprocess.CompletedProcess[str]:
    """Apply the committed role once to a synthetic localhost."""
    inventory = root / "hosts.yml"
    inventory.write_text(
        f"---\nall:\n  hosts:\n    {_HOST}:\n      ansible_connection: local\n"
        "      ansible_become: false\n",
        encoding="utf-8",
    )
    play = root / "play.yml"
    play.write_text(
        f"---\n- name: Converge proactive-compaction policy\n  hosts: all\n"
        "  gather_facts: false\n  roles:\n"
        f"    - role: {_ROLE_NAME}\n",
        encoding="utf-8",
    )
    variables = json.dumps(
        {
            "dev_host_compaction_sysctl_dir": str(sysctl_dir),
            "dev_host_compaction_sysctl_bin": str(sysctl_bin),
            "dev_host_compaction_owner": _invoking_owner(),
            "dev_host_compaction_group": _invoking_group(),
        }
    )
    return subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(inventory),
            "-e",
            variables,
            str(play),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
        env=os.environ | {"ANSIBLE_ROLES_PATH": str(_ANSIBLE / "roles"), "ANSIBLE_NOCOWS": "1"},
    )


def _changed(*, run: subprocess.CompletedProcess[str]) -> int:
    """The synthetic host's changed count from an Ansible recap."""
    recap = re.search(rf"^{_HOST}\s*:.*?changed=(?P<count>\d+)", run.stdout, re.MULTILINE)
    assert recap is not None, run.stdout + run.stderr
    return int(recap["count"])


def _set_sysctl_calls(*, monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """Set or clear the fake sysctl log location for one converge case."""
    if value is None:
        monkeypatch.delenv("SYSCTL_CALLS", raising=False)
    else:
        monkeypatch.setenv("SYSCTL_CALLS", value)


def _invoking_owner() -> str:
    """The account that can own files in an unprivileged test run."""
    return pwd.getpwuid(os.getuid()).pw_name


def _invoking_group() -> str:
    """The primary group of the account that runs this test."""
    return grp.getgrgid(os.getgid()).gr_name


def _assert_dropin_metadata(*, dropin: Path) -> None:
    """The synthetic drop-in belongs to the unprivileged test account."""
    assert pwd.getpwuid(dropin.stat().st_uid).pw_name == _invoking_owner()
    assert grp.getgrgid(dropin.stat().st_gid).gr_name == _invoking_group()
    assert stat.S_IMODE(dropin.stat().st_mode) == 0o644


@pytest.mark.parametrize("prior_sysctl_calls", [None, "pre-existing-sysctl-calls"])
def test_the_dev_host_play_converges_the_documented_proactive_compaction_dropin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior_sysctl_calls: str | None
) -> None:
    """The drop-in reaches the host, applies now, and is unchanged on a second apply."""
    _set_sysctl_calls(monkeypatch=monkeypatch, value=prior_sysctl_calls)

    assert _ROLE.is_dir(), (
        "ansible/dev-host.yml needs a dev_host_compaction role: otherwise the measured "
        "proactive-compaction setting remains a hand-applied sysctl"
    )

    root = tmp_path / "converge"
    root.mkdir()
    sysctl_dir = root / "etc" / "sysctl.d"
    sysctl_dir.mkdir(parents=True)
    calls = root / "sysctl.calls"
    sysctl_bin = root / "sysctl"
    sysctl_bin.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$SYSCTL_CALLS"\n',
        encoding="utf-8",
    )
    sysctl_bin.chmod(0o755)

    old_calls = os.environ.get("SYSCTL_CALLS")
    os.environ["SYSCTL_CALLS"] = str(calls)
    try:
        first = _converge(root=root, sysctl_dir=sysctl_dir, sysctl_bin=sysctl_bin)
        second = _converge(root=root, sysctl_dir=sysctl_dir, sysctl_bin=sysctl_bin)
    finally:
        if old_calls is None:
            del os.environ["SYSCTL_CALLS"]
        else:
            os.environ["SYSCTL_CALLS"] = old_calls

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    dropin = sysctl_dir / _DROPIN_NAME
    assert dropin.read_text(encoding="utf-8").endswith(f"{_DROPIN_LINE}\n")
    _assert_dropin_metadata(dropin=dropin)
    assert calls.read_text(encoding="utf-8") == f"--load {sysctl_dir / _DROPIN_NAME}\n"
    assert _changed(run=second) == 0, second.stdout + second.stderr
    assert os.environ.get("SYSCTL_CALLS") == prior_sysctl_calls


def test_the_role_is_a_tagged_dev_host_converge_and_records_its_safety_rationale() -> None:
    """The live-kernel change is explicit, scoped, and explained in the installed file."""
    play = _PLAY.read_text(encoding="utf-8")
    assert re.search(
        rf"^    - role: {_ROLE_NAME}$\n^      tags: \[{_ROLE_NAME}\]$",
        play,
        re.MULTILINE,
    ), play

    dropin = _ROLE / "files" / _DROPIN_NAME
    text = dropin.read_text(encoding="utf-8")
    assert _DROPIN_LINE in text, text
    assert "106%" in text and "kcompactd0" in text, text
    assert "on-demand compaction" in text and "direct compaction" in text, text

    defaults = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "dev_host_compaction_owner: root" in defaults, defaults
    assert "dev_host_compaction_group: root" in defaults, defaults
    assert 'owner: "{{ dev_host_compaction_owner }}"' in tasks, tasks
    assert 'group: "{{ dev_host_compaction_group }}"' in tasks, tasks
    assert 'mode: "0644"' in tasks, tasks
