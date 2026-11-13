"""Consumer-tier render proof for the reconcile_runs role (livespec-dev-tooling-oxwre7).

The role renders livespec-orchestrator-beads-fabro's committed reconcile-runs unit
text once per tenant, orders the enabled tenants' passes into one serial sweep, and
holds every timer while ``reconcile_runs_enabled`` is false. These fixtures execute
the role with the same pinned ``ansible-core`` as ``just ansible-drift``, against the
orchestrator unit text copied under ``fixtures/reconcile_runs_render/input/``, with
``reconcile_runs_manage_systemd`` false so nothing reaches a systemd manager. Every
file the role writes is compared byte-for-byte with ``fixtures/reconcile_runs_render/
<scenario>/``, after the scratch root and the invoking account are replaced by
``@ROOT@`` and ``@USER@``.

A deliberate change to the role's output updates these fixtures in the same commit.
"""

from __future__ import annotations

import grp
import json
import os
import pwd
import re
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLES = _REPO_ROOT / "ansible" / "roles"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reconcile_runs_render"
_TIMEOUT_SECONDS = 600
_ALERT_UNIT = "fixture-alert@.service"
_MARKERS = "markers.txt"


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


def _executable(*, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    path.chmod(0o755)


def _tenant_repo(*, root: Path, name: str) -> Path:
    repo = root / "workspace" / name
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text("{}\n", encoding="utf-8")
    return repo


def _scenario_vars(*, root: Path, enabled: bool) -> dict[str, object]:
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    _executable(path=root / "plugin" / "scripts" / "bin" / "dispatcher.py")
    _executable(path=root / "bin" / "with-env.sh")
    alpha = _tenant_repo(root=root, name="alpha")
    beta = _tenant_repo(root=root, name="beta")
    gamma = _tenant_repo(root=root, name="gamma")
    _executable(path=beta / "with-beta-env.sh")
    units = root / "units"
    units.mkdir()
    _ = (units / _ALERT_UNIT).write_text("[Service]\nExecStart=/bin/true\n", encoding="utf-8")
    wrapper = [str(root / "bin" / "with-env.sh"), "--"]
    return {
        "reconcile_runs_enabled": enabled,
        "reconcile_runs_manage_systemd": False,
        "reconcile_runs_user": user,
        "reconcile_runs_group": group,
        "reconcile_runs_unit_owner": user,
        "reconcile_runs_unit_group": group,
        "reconcile_runs_unit_dir": str(units),
        "reconcile_runs_state_dir": str(root / "state"),
        "reconcile_runs_staleness_bin": str(root / "bin" / "staleness"),
        "reconcile_runs_template_dir": str(_FIXTURES / "input"),
        "reconcile_runs_plugin_root": str(root / "plugin"),
        "reconcile_runs_staleness_on_failure": "fixture-alert@%n.service",
        "reconcile_runs_tenants": [
            {
                "name": "alpha",
                "unit": "reconcile-runs",
                "repo": str(alpha),
                "credential_wrapper": wrapper,
            },
            {
                "name": "beta",
                "repo": str(beta),
                "enabled": False,
                "credential_wrapper": ["./with-beta-env.sh", "--"],
            },
            {"name": "gamma", "repo": str(gamma), "credential_wrapper": wrapper},
        ],
    }


def _converge(*, root: Path, enabled: bool) -> None:
    inventory = root / "inventory.yml"
    _ = inventory.write_text(
        "".join(
            [
                "---\nall:\n  hosts:\n    fixture-host:\n",
                "      ansible_connection: local\n      ansible_become: false\n",
            ]
        ),
        encoding="utf-8",
    )
    play = root / "play.yml"
    _ = play.write_text(
        "".join(
            [
                "---\n- name: reconcile-runs render fixture\n  hosts: all\n",
                "  gather_facts: false\n  roles:\n    - role: reconcile_runs\n",
            ]
        ),
        encoding="utf-8",
    )
    variables = _scenario_vars(root=root, enabled=enabled)
    result = subprocess.run(
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
        env=_fixture_environment(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _rendered(*, root: Path) -> dict[str, str]:
    user = re.escape(pwd.getpwuid(os.getuid()).pw_name)
    group = re.escape(grp.getgrgid(os.getgid()).gr_name)

    def normal(text: str) -> str:
        text = text.replace(str(_FIXTURES / "input"), "@INPUT@").replace(str(root), "@ROOT@")
        text = re.sub(rf"^User={user}$", "User=@USER@", text, flags=re.MULTILINE)
        text = re.sub(rf"^Group={group}$", "Group=@GROUP@", text, flags=re.MULTILINE)
        return re.sub(rf"and `{user}` are substituted", "and `@USER@` are substituted", text)

    units = root / "units"
    files = {
        str(path.relative_to(units)): normal(path.read_text(encoding="utf-8"))
        for path in sorted(units.rglob("*"))
        if path.is_file() and path.name != _ALERT_UNIT
    }
    state = root / "state"
    files[_MARKERS] = "".join(f"{path.name}\n" for path in sorted(state.glob("*.last-success")))
    return files


def _expected(*, scenario: str) -> dict[str, str]:
    base = _FIXTURES / scenario
    return {
        str(path.relative_to(base)): path.read_text(encoding="utf-8")
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def _directive(*, text: str, key: str) -> list[str]:
    return [line.split("=", 1)[1] for line in text.splitlines() if line.startswith(f"{key}=")]


def test_an_enabled_host_renders_every_tenant_and_sweeps_only_the_enabled_ones(
    tmp_path: Path,
) -> None:
    _converge(root=tmp_path, enabled=True)
    rendered = _rendered(root=tmp_path)

    assert rendered == _expected(scenario="enabled")
    sweep = rendered["reconcile-runs-sweep.service"]
    assert _directive(text=sweep, key="Wants") == [
        "reconcile-runs.service reconcile-runs-gamma.service"
    ]
    assert _directive(text=sweep, key="After") == [
        "reconcile-runs.service reconcile-runs-gamma.service"
    ]
    gamma_policy = rendered["reconcile-runs-gamma.service.d/10-reconcile-runs-role.conf"]
    assert _directive(text=gamma_policy, key="After") == ["reconcile-runs.service"]
    beta_policy = rendered["reconcile-runs-beta.service.d/10-reconcile-runs-role.conf"]
    assert _directive(text=beta_policy, key="After") == []
    assert _directive(text=rendered["reconcile-runs.timer"], key="Unit") == [
        "reconcile-runs-sweep.service"
    ]
    beta_exec = _directive(text=rendered["reconcile-runs-beta.service"], key="ExecStart")
    assert beta_exec[0].startswith("@ROOT@/workspace/beta/with-beta-env.sh -- ")
    assert "--dry-run --json" in rendered["reconcile-runs-gamma-dry-run.service"]
    assert rendered[_MARKERS] == "alpha.last-success\ngamma.last-success\n"


def test_a_held_host_installs_every_unit_but_sweeps_and_seeds_nothing(tmp_path: Path) -> None:
    _converge(root=tmp_path, enabled=False)
    rendered = _rendered(root=tmp_path)

    assert rendered == _expected(scenario="held")
    assert _directive(text=rendered["reconcile-runs-sweep.service"], key="Wants") == []
    assert rendered[_MARKERS] == ""
    staleness = _directive(text=rendered["reconcile-runs-staleness.service"], key="ExecStart")
    assert staleness[0].endswith(" 14400")
