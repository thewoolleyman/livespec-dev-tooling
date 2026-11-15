"""The fleet git credential helper shim routes org-App clones through their wrapper.

Each fleet clone on the dev host names
``!/home/ubuntu/.local/bin/livespec-agent-github-credential-helper`` as its
GitHub credential helper. The shim was installed by hand (livespec-orslcm), and
its single route ran the livespec-runtime helper under the bare family wrapper.
After the livespec-ai organization transfer, that route mints the personal App,
and livespec-ai repositories refuse the push with a 403 (overseer-iyfjbo).

This test applies the committed role to a temporary destination, then runs the
installed shim inside throwaway git clones. Stub wrappers and a stub helper
record which route each run took, and with what arguments.
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
_ROLE_NAME = "fleet_git_credential_helper"
_PLAY = _ANSIBLE / "dev-host.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_HOST = "synthetic-dev-host"
_TIMEOUT_SECONDS = 600
_ROUTE_C = json.dumps(
    {
        "credential_wrapper": [
            "/usr/local/bin/with-livespec-env.sh",
            "--",
            "/bin/sh",
            "-c",
            'GITHUB_APP_ID="$GITHUB_APP_ID_ORG" exec "$@"',
            "sh",
        ]
    }
)
_FAKE_WRAPPER = """#!/bin/sh
printf '%s TW_REPO=%s\\n' "$WRAPPER_NAME" "${TW_REPO:-unset}" >> "$SHIM_LOG"
[ "$1" = -- ] && shift
exec "$@"
"""
_FAKE_HELPER = """#!/bin/sh
printf 'helper %s\\n' "$*" >> "$SHIM_LOG"
"""


def _ansible_core_pin() -> str:
    recipe = _JUSTFILE.read_text(encoding="utf-8")
    match = re.search(r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)", recipe, re.MULTILINE)
    assert match is not None, "justfile must define the ansible-apply recipe"
    pin = _ANSIBLE_CORE_PIN.search(match["body"])
    assert pin is not None, "ansible-apply must pin ansible-core"
    return pin[0]


def _stub(*, path: Path, name: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _FAKE_HELPER if name == "helper" else _FAKE_WRAPPER.replace("$WRAPPER_NAME", name)
    _ = path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _converge(
    *, root: Path, tenant_wrap: Path, helper_mode: int = 0o755
) -> subprocess.CompletedProcess[str]:
    helper = _stub(path=root / "bin" / "helper", name="helper")
    helper.chmod(helper_mode)
    inventory = root / "hosts.yml"
    _ = inventory.write_text(
        f"---\nall:\n  hosts:\n    {_HOST}:\n      ansible_connection: local\n"
        "      ansible_become: false\n",
        encoding="utf-8",
    )
    play = root / "play.yml"
    _ = play.write_text(
        "---\n- name: Converge the fleet git credential helper shim\n  hosts: all\n"
        f"  gather_facts: false\n  roles:\n    - role: {_ROLE_NAME}\n",
        encoding="utf-8",
    )
    variables = {
        "fleet_git_credential_helper_dest": str(root / "home" / ".local" / "bin" / "shim"),
        "fleet_git_credential_helper_owner": pwd.getpwuid(os.getuid()).pw_name,
        "fleet_git_credential_helper_group": grp.getgrgid(os.getgid()).gr_name,
        "fleet_git_credential_helper_runtime_helper": str(helper),
        "fleet_git_credential_helper_family_wrapper": str(
            _stub(path=root / "bin" / "with-livespec-env.sh", name="family")
        ),
        "fleet_git_credential_helper_tenant_wrap": str(tenant_wrap),
    }
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {
        "ANSIBLE_NOCOWS": "1",
        "ANSIBLE_RETRY_FILES_ENABLED": "False",
        "ANSIBLE_ROLES_PATH": str(_ANSIBLE / "roles"),
    }
    return subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(inventory),
            "-e",
            json.dumps(variables),
            str(play),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )


def _installed(*, root: Path, tenant_wrap: Path) -> Path:
    result = _converge(root=root, tenant_wrap=tenant_wrap)
    assert result.returncode == 0, result.stdout + result.stderr
    return root / "home" / ".local" / "bin" / "shim"


def _clone(*, root: Path, name: str, config: str | None) -> Path:
    clone = root / "clones" / name
    clone.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "-q", str(clone)], check=True, timeout=60)
    if config is not None:
        _ = (clone / ".livespec.jsonc").write_text(config, encoding="utf-8")
    (clone / "sub").mkdir()
    return clone


def _ask(*, root: Path, shim: Path, cwd: Path) -> list[str]:
    log = root / "log"
    _ = log.write_text("", encoding="utf-8")
    env = {"PATH": os.environ["PATH"], "SHIM_LOG": str(log), "HOME": str(root / "home")}
    done = subprocess.run(
        [str(shim), "get"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return log.read_text(encoding="utf-8").splitlines()


def test_the_shim_is_installed_executable_and_names_its_three_paths(tmp_path: Path) -> None:
    tenant_wrap = _stub(path=tmp_path / "libexec" / "tenant-wrap.sh", name="tenant")
    shim = _installed(root=tmp_path, tenant_wrap=tenant_wrap)

    mode = stat.S_IMODE(shim.stat().st_mode)
    assert mode == 0o775
    text = shim.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n")
    assert f"helper={tmp_path}/bin/helper\n" in text
    assert f'TW_REPO="$top" exec {tenant_wrap} -- "$helper" "$@"\n' in text
    assert text.endswith(f'exec {tmp_path}/bin/with-livespec-env.sh -- "$helper" "$@"\n')
    assert "livespec-orslcm" in text
    assert "livespec-dev-tooling#4796" in text


def test_a_route_c_clone_mints_through_the_tenant_wrapper(tmp_path: Path) -> None:
    tenant_wrap = _stub(path=tmp_path / "libexec" / "tenant-wrap.sh", name="tenant")
    shim = _installed(root=tmp_path, tenant_wrap=tenant_wrap)
    clone = _clone(root=tmp_path, name="org", config=_ROUTE_C)

    # From a subdirectory: the clone is found by its top level, not the cwd.
    log = _ask(root=tmp_path, shim=shim, cwd=clone / "sub")

    assert log == [f"tenant TW_REPO={clone.resolve()}", "helper get"]


@pytest.mark.parametrize(
    "config",
    [None, '{"credential_wrapper": ["./with-hetzner-xubuntu-credentials.sh", "--"]}\n'],
    ids=["no-livespec-jsonc", "own-wrapper-without-org-app"],
)
def test_a_clone_that_does_not_remap_keeps_the_family_route(
    tmp_path: Path, config: str | None
) -> None:
    tenant_wrap = _stub(path=tmp_path / "libexec" / "tenant-wrap.sh", name="tenant")
    shim = _installed(root=tmp_path, tenant_wrap=tenant_wrap)
    clone = _clone(root=tmp_path, name="plain", config=config)

    log = _ask(root=tmp_path, shim=shim, cwd=clone)

    assert log == ["family TW_REPO=unset", "helper get"]


def test_outside_a_clone_the_shim_keeps_the_family_route(tmp_path: Path) -> None:
    tenant_wrap = _stub(path=tmp_path / "libexec" / "tenant-wrap.sh", name="tenant")
    shim = _installed(root=tmp_path, tenant_wrap=tenant_wrap)
    elsewhere = tmp_path / "not-a-clone"
    elsewhere.mkdir()

    log = _ask(root=tmp_path, shim=shim, cwd=elsewhere)

    assert log == ["family TW_REPO=unset", "helper get"]


def test_a_route_c_clone_keeps_the_family_route_until_the_tenant_wrapper_exists(
    tmp_path: Path,
) -> None:
    shim = _installed(root=tmp_path, tenant_wrap=tmp_path / "libexec" / "absent.sh")
    clone = _clone(root=tmp_path, name="org", config=_ROUTE_C)

    log = _ask(root=tmp_path, shim=shim, cwd=clone)

    assert log == ["family TW_REPO=unset", "helper get"]


def test_a_runtime_helper_that_is_not_executable_refuses_before_the_shim_is_written(
    tmp_path: Path,
) -> None:
    tenant_wrap = _stub(path=tmp_path / "libexec" / "tenant-wrap.sh", name="tenant")
    result = _converge(root=tmp_path, tenant_wrap=tenant_wrap, helper_mode=0o644)

    assert result.returncode != 0
    assert f"{tmp_path}/bin/helper is missing or not executable" in result.stdout
    assert not (tmp_path / "home" / ".local" / "bin" / "shim").exists()


def test_the_dev_host_play_applies_the_role_under_its_own_tag() -> None:
    play = _PLAY.read_text(encoding="utf-8")

    assert f"    - role: {_ROLE_NAME}\n      tags: [{_ROLE_NAME}]\n" in play
