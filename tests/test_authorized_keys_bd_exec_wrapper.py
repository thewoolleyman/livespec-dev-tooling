"""Behavioural tests for the bd exec forced-command wrapper (tbhqye, route A).

The shipped wrapper hard-codes its three paths so that no environment variable
sshd could set can redirect it. These tests run a temporary copy whose three
constant lines are rewritten to point at a temp tree and a stub command.
"""

from __future__ import annotations

import base64
import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WRAPPER = (
    _REPO_ROOT
    / "ansible"
    / "roles"
    / "authorized_keys_managed"
    / "files"
    / "authorized-keys-bd-exec.sh"
)
_DENIED = 126


def _encode(*, argv: list[str]) -> str:
    return base64.b64encode(b"\0".join(arg.encode() for arg in argv)).decode()


def _install(*, tmp_path: Path) -> Path:
    projects = tmp_path / "projects"
    (projects / "okrepo" / ".beads").mkdir(parents=True)
    (projects / "notenant").mkdir(parents=True)
    allow = tmp_path / "repos"
    _ = allow.write_text("okrepo\nnotenant\n", encoding="utf-8")
    text = _WRAPPER.read_text(encoding="utf-8")
    text = re.sub(r"^ALLOWLIST=.*$", f"ALLOWLIST={allow}", text, flags=re.MULTILINE)
    text = re.sub(r"^PROJECTS=.*$", f"PROJECTS={projects}", text, flags=re.MULTILINE)
    text = re.sub(r"^RUN_PREFIX=.*$", 'RUN_PREFIX="printf [%s]"', text, flags=re.MULTILINE)
    copy = tmp_path / "wrapper.sh"
    _ = copy.write_text(text, encoding="utf-8")
    return copy


def _run(*, copy: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(copy)],
        env={"SSH_ORIGINAL_COMMAND": command, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_shipped_wrapper_has_no_environment_overridable_paths() -> None:
    text = _WRAPPER.read_text(encoding="utf-8")

    assert "AUTHORIZED_KEYS_BD_EXEC" not in text
    assert re.search(r"^ALLOWLIST=/etc/authorized-keys-bd-exec/repos$", text, re.MULTILINE)
    assert re.search(r"^PROJECTS=/data/projects$", text, re.MULTILINE)


@pytest.mark.parametrize(
    "argv",
    [
        ["show", "some-id", "--json"],
        ["comment", "x", 'text with spaces; $(id) and "quotes"'],
        ["update", "x", "--status", "closed"],
        ["config", "get", "issue-prefix"],
        ["list", "--status", "open", "--json", "-n", "5"],
    ],
)
def test_allowed_calls_reach_the_command_with_exact_arguments(
    *, tmp_path: Path, argv: list[str]
) -> None:
    copy = _install(tmp_path=tmp_path)

    done = _run(copy=copy, command=f"in okrepo bd {_encode(argv=argv)}")

    assert done.returncode == 0
    assert done.stdout == "".join(f"[{arg}]" for arg in argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["init"],
        ["sql", "select 1"],
        ["SQL", "select 1"],
        ["edit", "x"],
        ["config", "set", "k", "v"],
        ["config"],
        ["config", "list"],
        ["config", "get", "dolt.password"],
        ["config", "get", "jira.api_token"],
        ["config", "get", "a", "b"],
        ["repo", "add", "/x"],
        ["doctor", "--fix"],
        ["admin"],
        ["upgrade"],
        ["export"],
        ["show", "x", "--db", "/etc/x"],
        ["show", "x", "--DB=/etc/x"],
        ["show", "x", "-C", "/etc"],
        ["show", "x", "--directory", "/etc"],
        ["show", "x", "--global"],
        ["show", "x", "--profile"],
        ["show", "x", "--credentials-file=/x"],
        ["create", "--file", "/etc/passwd"],
        ["create", "--description-file", "/etc/passwd"],
        ["show", "x", "-f/etc/passwd"],
        ["show", "x", "-o/tmp/x"],
        ["show", "x", "-vf", "/x"],
        ["show", "x", "-f"],
        ["delete", "--from-file", "/etc/passwd"],
        ["create", "--graph", "/x"],
        ["create", "x", "--description=@/etc/passwd"],
        ["create", "x", "@/etc/passwd"],
        ["create", "--output-dir", "/x"],
        ["-x", "show"],
        ["", "show"],
    ],
)
def test_host_touching_or_unlisted_calls_are_denied(*, tmp_path: Path, argv: list[str]) -> None:
    copy = _install(tmp_path=tmp_path)

    done = _run(copy=copy, command=f"in okrepo bd {_encode(argv=argv)}")

    assert done.returncode == _DENIED
    assert done.stdout == ""


@pytest.mark.parametrize(
    "command",
    [
        "ls",
        "in okrepo bd",
        "in .. bd c2hvdw==",
        "in other bd c2hvdw==",
        "in notenant bd c2hvdw==",
        "in okrepo sh c2hvdw==",
        "in okrepo bd !!notb64",
        "in okrepo bd ====",
        "in okrepo bd c2hvdw==; id",
        "in okrepo bd c2hvdw== extra",
    ],
)
def test_malformed_repo_encoding_or_shape_is_denied(*, tmp_path: Path, command: str) -> None:
    copy = _install(tmp_path=tmp_path)

    done = _run(copy=copy, command=command)

    assert done.returncode == _DENIED
    assert done.stdout == ""
