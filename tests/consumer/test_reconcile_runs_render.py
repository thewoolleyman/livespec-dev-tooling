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

Every tenant's pass runs through the role's ``livespec-tenant-wrap.sh``, which reads
the tenant's committed ``.livespec.jsonc`` ``credential_wrapper`` when the pass runs
(livespec-orchestrator-beads-fabro bd-ib-ft426g). The fixture tenants cover its three
routes, and the script itself runs here against fake wrappers that record what each
hop sees.

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
_TENANT_WRAP = _ROLES / "reconcile_runs" / "files" / "livespec-tenant-wrap.sh"
_REFUSED = 78


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


def _tenant_repo(*, root: Path, name: str, config: str = "{}\n") -> Path:
    repo = root / "workspace" / name
    repo.mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(config, encoding="utf-8")
    return repo


def _route_c(*, family: Path) -> str:
    """The shape of the orchestrator's route C wrapper (orchestrator PR 5361)."""
    hop = 'GITHUB_APP_ID="$GITHUB_APP_ID_ORG" exec "$@"'
    return json.dumps({"credential_wrapper": [str(family), "--", "/bin/sh", "-c", hop, "sh"]})


def _scenario_vars(*, root: Path, enabled: bool) -> dict[str, object]:
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    _executable(path=root / "plugin" / "scripts" / "bin" / "dispatcher.py")
    family = root / "bin" / "with-livespec-env.sh"
    _executable(path=family)
    alpha = _tenant_repo(root=root, name="alpha")
    beta = _tenant_repo(
        root=root, name="beta", config='{"credential_wrapper": ["./with-beta-env.sh", "--"]}\n'
    )
    gamma = _tenant_repo(root=root, name="gamma", config=_route_c(family=family))
    _executable(path=beta / "with-beta-env.sh")
    units = root / "units"
    units.mkdir(exist_ok=True)
    _ = (units / _ALERT_UNIT).write_text("[Service]\nExecStart=/bin/true\n", encoding="utf-8")
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
        "reconcile_runs_tenant_wrap_bin": str(root / "bin" / "livespec-tenant-wrap.sh"),
        "reconcile_runs_family_wrapper": str(family),
        "reconcile_runs_template_dir": str(_FIXTURES / "input"),
        "reconcile_runs_plugin_root": str(root / "plugin"),
        "reconcile_runs_staleness_on_failure": "fixture-alert@%n.service",
        "reconcile_runs_tenants": [
            {"name": "alpha", "unit": "reconcile-runs", "repo": str(alpha)},
            {"name": "beta", "repo": str(beta), "enabled": False},
            {"name": "gamma", "repo": str(gamma)},
        ],
    }


def _converge(
    *, root: Path, enabled: bool, overrides: dict[str, object] | None = None
) -> subprocess.CompletedProcess[str]:
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
    variables = _scenario_vars(root=root, enabled=enabled) | (overrides or {})
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
    return result


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


def _converged(*, root: Path, enabled: bool) -> None:
    result = _converge(root=root, enabled=enabled)
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_enabled_host_renders_every_tenant_and_sweeps_only_the_enabled_ones(
    tmp_path: Path,
) -> None:
    _converged(root=tmp_path, enabled=True)
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
    for unit in ("reconcile-runs", "reconcile-runs-beta", "reconcile-runs-gamma-dry-run"):
        text = rendered[f"{unit}.service"]
        assert _directive(text=text, key="ExecStart")[0].startswith(
            "@ROOT@/bin/livespec-tenant-wrap.sh -- /usr/bin/python3 "
        )
        assert _directive(text=text, key="Environment") == [
            "TW_FAMILY_WRAPPER=@ROOT@/bin/with-livespec-env.sh"
        ]
    installed = tmp_path / "bin" / "livespec-tenant-wrap.sh"
    assert installed.read_bytes() == _TENANT_WRAP.read_bytes()
    assert os.access(installed, os.X_OK)
    assert "--dry-run --json" in rendered["reconcile-runs-gamma-dry-run.service"]
    assert rendered[_MARKERS] == "alpha.last-success\ngamma.last-success\n"


def test_a_held_host_installs_every_unit_but_sweeps_and_seeds_nothing(tmp_path: Path) -> None:
    _converged(root=tmp_path, enabled=False)
    rendered = _rendered(root=tmp_path)

    assert rendered == _expected(scenario="held")
    assert _directive(text=rendered["reconcile-runs-sweep.service"], key="Wants") == []
    assert rendered[_MARKERS] == ""
    staleness = _directive(text=rendered["reconcile-runs-staleness.service"], key="ExecStart")
    assert staleness[0].endswith(" 14400")


def test_a_converge_retires_the_hand_installed_tenant_wrap_override(tmp_path: Path) -> None:
    override = tmp_path / "units" / "reconcile-runs.service.d" / "60-tenant-wrap.conf"
    override.parent.mkdir(parents=True)
    _ = override.write_text("[Service]\nExecStart=\nExecStart=/bin/true\n", encoding="utf-8")
    _converged(root=tmp_path, enabled=True)

    assert not override.exists()
    assert _rendered(root=tmp_path) == _expected(scenario="enabled")


def test_a_tenant_entry_that_still_copies_its_credential_wrapper_is_refused(
    tmp_path: Path,
) -> None:
    copied = {
        "name": "alpha",
        "repo": str(tmp_path / "workspace" / "alpha"),
        "credential_wrapper": ["/usr/local/bin/with-livespec-env.sh", "--"],
    }
    result = _converge(root=tmp_path, enabled=True, overrides={"reconcile_runs_tenants": [copied]})

    assert result.returncode != 0
    assert "must not carry a credential_wrapper" in result.stdout
    assert not (tmp_path / "units" / "reconcile-runs.service").exists()


def test_a_tenant_whose_committed_wrapper_a_pass_could_not_run_is_refused_before_install(
    tmp_path: Path,
) -> None:
    broken = _tenant_repo(
        root=tmp_path,
        name="broken",
        config='{"credential_wrapper": ["/nonexistent/with-broken-env.sh", "--"]}\n',
    )
    tenants = [
        {"name": "alpha", "unit": "reconcile-runs", "repo": str(tmp_path / "workspace" / "alpha")},
        {"name": "broken", "repo": str(broken), "enabled": False},
    ]
    result = _converge(root=tmp_path, enabled=True, overrides={"reconcile_runs_tenants": tenants})

    assert result.returncode != 0
    assert "/nonexistent/with-broken-env.sh" in result.stdout
    assert not (tmp_path / "units" / "reconcile-runs.service").exists()


# --- livespec-tenant-wrap.sh against fake wrappers ---

_FAKE_FAMILY = """#!/usr/bin/env bash
printf 'family %s\\n' "$*" >> "$TW_LOG"
export BEADS_DOLT_PASSWORD=family-password GITHUB_APP_ID=personal-app GITHUB_APP_ID_ORG=org-app
[ "$1" = -- ] && shift
exec "$@"
"""
_FAKE_TENANT = """#!/usr/bin/env bash
printf 'tenant password-before=%s\\n' "${BEADS_DOLT_PASSWORD:-unset}" >> "$TW_LOG"
export BEADS_DOLT_PASSWORD=tenant-password
[ "$1" = -- ] && shift
exec "$@"
"""
_FAKE_COMMAND = """#!/usr/bin/env bash
printf 'command app=%s password=%s argv=%s\\n' \\
  "${GITHUB_APP_ID:-unset}" "${BEADS_DOLT_PASSWORD:-unset}" "$*" >> "$TW_LOG"
"""


def _script(*, path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _wrap(
    *, root: Path, config: str | None, args: list[str], cwd: Path | None = None
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    family = _script(path=root / "bin" / "with-livespec-env.sh", text=_FAKE_FAMILY)
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _ = _script(path=repo / "with-tenant-env.sh", text=_FAKE_TENANT)
    _ = _script(path=root / "bin" / "command", text=_FAKE_COMMAND)
    if config is not None:
        _ = (repo / ".livespec.jsonc").write_text(config, encoding="utf-8")
    log = root / "log"
    log.touch()
    env = {"PATH": os.environ["PATH"], "TW_LOG": str(log), "TW_FAMILY_WRAPPER": str(family)}
    if cwd is not None:
        env["TW_REPO"] = str(repo)
    done = subprocess.run(
        [str(_TENANT_WRAP), *args],
        cwd=cwd or repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return done, log.read_text(encoding="utf-8").splitlines()


def _command(*, root: Path) -> list[str]:
    return ["--", str(root / "bin" / "command"), "reconcile-runs", "--json"]


def test_a_tenant_without_a_credential_wrapper_runs_under_the_family_wrapper(
    tmp_path: Path,
) -> None:
    done, log = _wrap(root=tmp_path, config="{}\n", args=_command(root=tmp_path))

    assert done.returncode == 0, done.stderr
    assert [line.split(" ", 1)[0] for line in log] == ["family", "command"]
    assert log[1] == "command app=personal-app password=family-password argv=reconcile-runs --json"


def test_a_family_wrapper_runs_as_committed_so_route_c_mints_the_org_app(
    tmp_path: Path,
) -> None:
    family = tmp_path / "bin" / "with-livespec-env.sh"
    done, log = _wrap(root=tmp_path, config=_route_c(family=family), args=_command(root=tmp_path))

    assert done.returncode == 0, done.stderr
    # The /bin/sh hop after the family wrapper's "--" ran: the pass sees the org App.
    assert log[-1] == "command app=org-app password=family-password argv=reconcile-runs --json"


def test_another_tenants_wrapper_runs_nested_without_the_family_password(
    tmp_path: Path,
) -> None:
    config = """{
  // A comment naming "credential_wrapper": ["/decoy"] is not the key.
  "docs": "https://example.invalid/a//b",
  /* a block comment */
  "credential_wrapper": ["./with-tenant-env.sh", "--",],
}
"""
    done, log = _wrap(root=tmp_path, config=config, args=_command(root=tmp_path))

    assert done.returncode == 0, done.stderr
    assert log[1] == "tenant password-before=unset"
    assert log[2] == "command app=personal-app password=tenant-password argv=reconcile-runs --json"


def test_the_tenant_is_tw_repo_when_it_is_set(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    config = '{"credential_wrapper": ["./with-tenant-env.sh", "--"]}\n'
    done, log = _wrap(root=tmp_path, config=config, args=["--resolve"], cwd=elsewhere)

    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[0] == "mode=tenant"
    assert f"{tmp_path}/repo/with-tenant-env.sh" in done.stdout
    assert log == []


@pytest.mark.parametrize(
    "config",
    [
        '{"credential_wrapper": "/usr/local/bin/with-livespec-env.sh --"}\n',
        '{"credential_wrapper": []}\n',
        '{"credential_wrapper": ["/usr/local/bin/with-livespec-env.sh", ""]}\n',
        '{"credential_wrapper": ["/nonexistent/with-livespec-env.sh", "--"]}\n',
        '{"credential_wrapper": [\n',
    ],
    ids=["not-a-list", "empty", "empty-argument", "not-executable", "unparsable"],
)
def test_a_wrapper_the_pass_cannot_use_runs_nothing_and_never_falls_back(
    tmp_path: Path, config: str
) -> None:
    done, log = _wrap(root=tmp_path, config=config, args=_command(root=tmp_path))
    resolved, _ = _wrap(root=tmp_path, config=config, args=["--resolve"])

    assert done.returncode == _REFUSED
    assert log == []
    assert resolved.returncode == _REFUSED
    assert "livespec-tenant-wrap:" in done.stderr


def test_a_malformed_credential_wrapper_is_reported_as_credential_wrapper_unreadable(
    tmp_path: Path,
) -> None:
    config = '{"credential_wrapper": "/usr/local/bin/with-livespec-env.sh --"}\n'
    done, log = _wrap(root=tmp_path, config=config, args=_command(root=tmp_path))

    assert done.returncode == _REFUSED
    assert log == []
    assert "credential-wrapper-unreadable: " in done.stderr
