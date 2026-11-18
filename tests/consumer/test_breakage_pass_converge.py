"""Consumer-tier converge proof for the breakage_pass role (bd-ib-voazyv, S3).

The role is executed with the same pinned ``ansible-core`` as ``just ansible-drift``,
with ``breakage_pass_manage_systemd`` false so nothing reaches a systemd manager.
These cases cover the two paths a unit-text check cannot: the revert, which must
remove every unit it installed (and the unit of a repository dropped from the list),
and the refusal of a repository whose inputs are missing.
"""

from __future__ import annotations

import grp
import json
import os
import pwd
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLES = _REPO_ROOT / "ansible" / "roles"
_TIMEOUT_SECONDS = 600
_PREFIX = "livespec-breakage-pass-"


@pytest.fixture
def scratch() -> Iterator[Path]:
    """A scratch root OUTSIDE /tmp: the role refuses a /tmp runner, state or plugin path."""
    base = _REPO_ROOT / "tmp" / "breakage-pass-converge"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _ansible_core_pin() -> str:
    recipe = _JUSTFILE.read_text(encoding="utf-8")
    match = re.search(r"^ansible-drift \*args:\n(?P<body>(?:    .*\n)+)", recipe, re.MULTILINE)
    assert match is not None, "justfile must define the ansible-drift recipe"
    pin = re.search(r"ansible-core==[0-9][0-9A-Za-z.]*", match["body"])
    assert pin is not None, "ansible-drift must pin ansible-core"
    return pin[0]


def _environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {
        "ANSIBLE_NOCOWS": "1",
        "ANSIBLE_RETRY_FILES_ENABLED": "False",
        "ANSIBLE_ROLES_PATH": str(_ROLES),
    }


def _executable(*, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    path.chmod(0o755)


def _repo(*, root: Path, name: str, config: bool = True) -> Path:
    repo = root / "workspace" / name
    repo.mkdir(parents=True, exist_ok=True)
    if config:
        _ = (repo / ".livespec.jsonc").write_text("{}\n", encoding="utf-8")
    return repo


def _variables(
    *,
    root: Path,
    enabled: bool,
    names: list[str],
    wrapper: bool,
    config: bool = True,
    overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    _executable(path=root / "plugin" / "scripts" / "bin" / "dispatcher.py")
    family = root / "bin" / "with-livespec-env.sh"
    _executable(path=family)
    _executable(path=root / "bin" / "staleness")
    if wrapper:
        _executable(path=root / "bin" / "livespec-tenant-wrap.sh")
    (root / "units").mkdir(exist_ok=True)
    return {
        "breakage_pass_enabled": enabled,
        "breakage_pass_manage_systemd": False,
        "breakage_pass_user": user,
        "breakage_pass_group": group,
        "breakage_pass_unit_owner": user,
        "breakage_pass_unit_group": group,
        "breakage_pass_unit_dir": str(root / "units"),
        "breakage_pass_state_dir": str(root / "state"),
        "breakage_pass_runner_bin": str(root / "bin" / "livespec-breakage-pass"),
        "breakage_pass_staleness_bin": str(root / "bin" / "staleness"),
        "breakage_pass_tenant_wrap_bin": str(root / "bin" / "livespec-tenant-wrap.sh"),
        "breakage_pass_family_wrapper": str(family),
        "breakage_pass_plugin_root": str(root / "plugin"),
        "breakage_pass_repos": [
            {"name": name, "repo": str(_repo(root=root, name=name, config=config))}
            for name in names
        ],
    } | (overrides or {})


def _converge(
    *,
    root: Path,
    enabled: bool,
    names: list[str],
    wrapper: bool = True,
    config: bool = True,
    overrides: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    inventory = root / "inventory.yml"
    _ = inventory.write_text(
        "---\nall:\n  hosts:\n    fixture-host:\n"
        "      ansible_connection: local\n      ansible_become: false\n",
        encoding="utf-8",
    )
    play = root / "play.yml"
    _ = play.write_text(
        "---\n- name: breakage pass fixture\n  hosts: all\n  gather_facts: false\n"
        "  roles:\n    - role: breakage_pass\n",
        encoding="utf-8",
    )
    variables = _variables(
        root=root,
        enabled=enabled,
        names=names,
        wrapper=wrapper,
        config=config,
        overrides=overrides,
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
            json.dumps(variables),
            str(play),
        ],
        cwd=root,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )


def _units(*, root: Path) -> list[str]:
    return sorted(path.name for path in (root / "units").glob(f"{_PREFIX}*"))


def test_an_enabled_converge_installs_a_service_and_timer_per_repository(scratch: Path) -> None:
    done = _converge(root=scratch, enabled=True, names=["alpha", "beta"])

    assert done.returncode == 0, done.stdout + done.stderr
    assert _units(root=scratch) == [
        f"{_PREFIX}alpha.service",
        f"{_PREFIX}alpha.timer",
        f"{_PREFIX}beta.service",
        f"{_PREFIX}beta.timer",
        f"{_PREFIX}staleness.service",
        f"{_PREFIX}staleness.timer",
    ]
    service = (scratch / "units" / f"{_PREFIX}alpha.service").read_text(encoding="utf-8")
    assert "Type=oneshot" in service
    assert "TimeoutStopSec=90" in service
    assert (scratch / "state" / "alpha.last-success").is_file()


def test_a_second_enabled_converge_changes_nothing(scratch: Path) -> None:
    _ = _converge(root=scratch, enabled=True, names=["alpha"])

    done = _converge(root=scratch, enabled=True, names=["alpha"])

    assert done.returncode == 0, done.stdout + done.stderr
    assert re.search(r"changed=0\b", done.stdout)


def test_the_revert_removes_every_installed_unit_and_a_second_run_changes_nothing(
    scratch: Path,
) -> None:
    _ = _converge(root=scratch, enabled=True, names=["alpha", "beta"])

    reverted = _converge(root=scratch, enabled=False, names=["alpha", "beta"])
    again = _converge(root=scratch, enabled=False, names=["alpha", "beta"])

    assert reverted.returncode == 0, reverted.stdout + reverted.stderr
    assert _units(root=scratch) == []
    assert (scratch / "bin" / "staleness").is_file()
    assert again.returncode == 0, again.stdout + again.stderr
    assert re.search(r"changed=0\b", again.stdout)


def test_a_repository_dropped_from_the_list_loses_its_units_and_the_rest_keep_theirs(
    scratch: Path,
) -> None:
    _ = _converge(root=scratch, enabled=True, names=["alpha", "beta"])

    done = _converge(root=scratch, enabled=True, names=["alpha"])

    assert done.returncode == 0, done.stdout + done.stderr
    assert _units(root=scratch) == [
        f"{_PREFIX}alpha.service",
        f"{_PREFIX}alpha.timer",
        f"{_PREFIX}staleness.service",
        f"{_PREFIX}staleness.timer",
    ]


def test_the_revert_needs_neither_the_tenant_wrapper_nor_a_usable_repository(
    scratch: Path,
) -> None:
    done = _converge(root=scratch, enabled=False, names=["alpha"], wrapper=False)

    assert done.returncode == 0, done.stdout + done.stderr


def test_an_enabled_converge_without_the_tenant_wrapper_is_refused_before_install(
    scratch: Path,
) -> None:
    done = _converge(root=scratch, enabled=True, names=["alpha"], wrapper=False)

    assert done.returncode != 0
    assert "Converge role reconcile_runs first" in done.stdout + done.stderr
    assert _units(root=scratch) == []


def test_a_repository_without_a_livespec_config_is_refused_before_install(scratch: Path) -> None:
    done = _converge(root=scratch, enabled=True, names=["alpha"], config=False)

    assert done.returncode != 0
    assert "missing or not usable" in done.stdout + done.stderr
    assert _units(root=scratch) == []


@pytest.mark.parametrize(
    "key",
    ["breakage_pass_state_dir", "breakage_pass_runner_bin", "breakage_pass_plugin_root"],
)
def test_a_path_under_tmp_is_refused_before_install(scratch: Path, key: str) -> None:
    done = _converge(
        root=scratch, enabled=True, names=["alpha"], overrides={key: "/tmp/breakage-pass-x"}
    )

    assert done.returncode != 0
    assert "must be stable paths" in done.stdout + done.stderr
    assert _units(root=scratch) == []


def test_a_plugin_path_under_a_versioned_plugin_cache_is_refused(scratch: Path) -> None:
    done = _converge(
        root=scratch,
        enabled=True,
        names=["alpha"],
        overrides={"breakage_pass_plugin_root": "/home/u/.claude/plugins/cache/x/y/abc123"},
    )

    assert done.returncode != 0
    assert "must be stable paths" in done.stdout + done.stderr
