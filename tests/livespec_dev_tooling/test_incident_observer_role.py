"""The incident_observer role renders the manifest the way the service verifies it.

livespec-dev-tooling-w7n3ad. The role's `render_released_installation.py` runs on
the host with the installation's own interpreter; these tests hold its digest
and argv rendering together with `incident_controller_installation.py`, the
loader that refuses the service's start when either drifts.
"""

from __future__ import annotations

# ruff: noqa: SLF001 -- White-box: the loader's digest is the contract under test.
import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from livespec_dev_tooling import incident_controller_installation as installation

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-w7n3ad
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "incident_observer"
_SCRIPT = _ROLE / "files" / "render_released_installation.py"
_PLAYBOOK = _REPO_ROOT / "ansible" / "dev-host.yml"
_VPS_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars" / "vps.yml"
_PACKAGE_ROOT = Path(installation.__file__).resolve().parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_released_installation", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: a dataclass under `from __future__ import
    # annotations` resolves its field types through sys.modules.
    sys.modules[spec.name] = module
    # No bytecode beside the script: a `.pyc` inside the role tree is a binary
    # file `check-ansible-hostname-free` cannot decode as UTF-8.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_package_digest_is_the_loaders_algorithm(tmp_path, monkeypatch) -> None:
    # Names chosen so Path ordering and plain string ordering disagree:
    # `a/b.py` sorts before `a-b/c.py` as parts, after it as a string.
    for relative, body in (
        ("a/b.py", b"one"),
        ("a-b/c.py", b"two"),
        ("_vendor/z.py", b"three"),
        ("top.py", b"four"),
        ("top.txt", b"not hashed"),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    monkeypatch.setattr(installation, "protected_path", lambda *, path: path is not None)
    assert _load().package_digest(root=tmp_path) == installation._package_digest(root=tmp_path)


@pytest.fixture
def host(tmp_path, monkeypatch):
    for name in ("state", "repo"):
        (tmp_path / name).mkdir(mode=0o700)
    for name, body in (("webhook", b"a" * 32), ("control", b"b" * 32), ("query", b"c" * 32)):
        (tmp_path / name).write_bytes(body)
        (tmp_path / name).chmod(0o600)
    reader_script = tmp_path / "incident_authority.py"
    reader_script.write_text("raise SystemExit(1)\n")
    reader_script.chmod(0o755)
    config_path = tmp_path / "controller.json"
    config_path.write_text(
        json.dumps(
            {
                "manifest": str(tmp_path / "released-installation.json"),
                "candidate_uid": os.geteuid() + 1,
                "repository": "owner/repo",
                "repo": str(tmp_path / "repo"),
                "state": str(tmp_path / "state"),
                "webhook_secret": str(tmp_path / "webhook"),
                "control_secret": str(tmp_path / "control"),
                "query_secret": str(tmp_path / "query"),
                "port": 8765,
            }
        )
    )
    config_path.chmod(0o600)
    # The developer tree is not a protected installation (group-writable
    # ancestors); the digest and argv rendering are what is under test here.
    monkeypatch.setattr(installation, "protected_path", lambda *, path: path is not None)
    monkeypatch.setattr(installation.importlib.metadata, "version", lambda _: "1.2.3")
    return tmp_path, reader_script, config_path


def test_rendered_manifest_loads_as_the_protected_installation(host) -> None:
    tmp_path, reader_script, config_path = host
    module = _load()
    manifest = module.render_manifest(
        inputs=module.ManifestInputs(
            release="v1.2.3",
            revision="a" * 40,
            reader_release="v0.290.0",
            reader_script=reader_script,
            config=config_path,
            required_jobs=("ci-green",),
            interpreter=Path(sys.executable),
        ),
        package_root=_PACKAGE_ROOT,
    )
    manifest_path = tmp_path / "released-installation.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_path.chmod(0o600)
    loaded = installation.ControllerInstallation.load(config=config_path)
    assert loaded is not None, "the service refuses the rendered manifest"
    assert loaded.reader == (sys.executable, str(reader_script))
    assert loaded.principal == (
        sys.executable,
        "-I",
        str(_PACKAGE_ROOT / "incident_recovery_principal_service.py"),
        str(config_path),
    )
    assert loaded.release == "v1.2.3"
    assert loaded.jobs == ("ci-green",)
    assert str(Path(sys.executable).resolve()) in manifest["files"]


def test_main_prints_the_manifest_only_for_the_installed_release(host, capsys) -> None:
    _, reader_script, config_path = host
    module = _load()
    installed = "v" + importlib.metadata.version("livespec-dev-tooling")
    argv = [
        "--revision",
        "b" * 40,
        "--reader-release",
        "v0.290.0",
        "--reader-script",
        str(reader_script),
        "--config",
        str(config_path),
        "--required-job",
        "ci-green",
    ]
    assert module.main(["--release", "v0.0.0-not-installed", *argv]) == 2
    assert "refused" in capsys.readouterr().err
    assert module.main(["--release", installed, *argv]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert set(rendered) == {
        "release",
        "revision",
        "package_sha256",
        "reader",
        "reader_release",
        "principal",
        "files",
        "required_jobs",
    }
    assert rendered["package_sha256"] == module.package_digest(root=_PACKAGE_ROOT)


def test_the_dev_host_play_runs_the_role_behind_the_tailnet_front() -> None:
    playbook = _PLAYBOOK.read_text(encoding="utf-8")
    assert "- role: incident_observer" in playbook
    assert playbook.index("- role: incident_observer") < playbook.index(
        "- role: tailscale_serve"
    ), "the loopback listener is converged before the tailnet front that fronts it"
    vps = _VPS_VARS.read_text(encoding="utf-8")
    assert "tailscale_serve_mappings:" in vps
    assert "backend: http://127.0.0.1:8765" in vps


def test_a_crash_loop_ends_in_failed_rather_than_restarting_forever() -> None:
    """Restart=on-failure with RestartSec=2 never trips systemd's default 5-in-10s limit.

    The service exits 1 whenever its conflict sweep or original-run watcher dies, so a
    crash on every start would take the webhook listener down every few seconds forever.
    Both the role's unit and the packaged provisioning unit bound it in `[Unit]`, and the
    bound must be reachable: StartLimitBurst starts spaced RestartSec apart fit inside
    StartLimitIntervalSec.
    """
    packaged = _REPO_ROOT / "livespec_dev_tooling" / "data" / "incident-observer.service"
    for path in (_ROLE / "templates" / "livespec-incident-observer.service.j2", packaged):
        text = path.read_text(encoding="utf-8")
        unit_section = text.split("[Unit]", 1)[1].split("[Service]", 1)[0]
        settings = dict(
            line.split("=", 1)
            for line in text.splitlines()
            if "=" in line and not line.startswith("#")
        )
        burst, interval = int(settings["StartLimitBurst"]), int(settings["StartLimitIntervalSec"])
        assert "StartLimitIntervalSec=300" in unit_section, path
        assert "StartLimitBurst=5" in unit_section, path
        assert settings["Restart"] == "on-failure", path
        assert burst * int(settings["RestartSec"]) < interval, path
    readme = (_ROLE / "README.md").read_text(encoding="utf-8")
    assert "StartLimitIntervalSec=300" in readme and "StartLimitBurst=5" in readme


def test_the_restart_handler_clears_the_start_limit_first() -> None:
    """A tripped StartLimitBurst refuses a plain restart until the interval passes.

    Measured: after a crash loop lands in `failed`, `systemctl restart` answers "Start
    request repeated too quickly" for up to StartLimitIntervalSec, even with the cause
    fixed. So every restart the role notifies is preceded by `systemctl reset-failed` on
    the same unit: a handler listening on the restart's own name, defined before it
    (handlers run in definition order), accepting only a never-loaded unit's refusal.
    """
    handlers = yaml.safe_load((_ROLE / "handlers" / "main.yml").read_text(encoding="utf-8"))
    names = [handler["name"] for handler in handlers]
    restart_name = "Restart the incident observer onto its installation"
    restart = names.index(restart_name)
    (clear,) = [
        index
        for index, handler in enumerate(handlers)
        if handler.get("ansible.builtin.command", {}).get("argv", [])[:2]
        == ["systemctl", "reset-failed"]
    ]
    reset = handlers[clear]
    assert clear < restart
    assert reset["listen"] == restart_name
    assert (
        reset["ansible.builtin.command"]["argv"][2]
        == handlers[restart]["ansible.builtin.systemd_service"]["name"]
    )
    assert reset["become"] is True
    assert reset["when"] == handlers[restart]["when"]
    # failed_when reads this name, and an undefined one fails even an rc-0 reset; a
    # check_mode override would reset a real unit under --check.
    assert reset["register"] == "incident_observer_reset_failed"
    assert "check_mode" not in reset
    # Ansible ANDs the list: a dropped `rc` clause fails a healthy rc-0 reset, and
    # systemctl writes "not loaded" to stderr, not stdout.
    assert reset["failed_when"] == [
        "incident_observer_reset_failed.rc != 0",
        "'not loaded' not in incident_observer_reset_failed.stderr",
    ]
    assert handlers[restart]["ansible.builtin.systemd_service"]["state"] == "restarted"


def test_the_unit_keeps_the_packaged_confinement() -> None:
    unit = (_ROLE / "templates" / "livespec-incident-observer.service.j2").read_text(
        encoding="utf-8"
    )
    packaged = (
        _REPO_ROOT / "livespec_dev_tooling" / "data" / "incident-observer.service"
    ).read_text(encoding="utf-8")
    for line in packaged.splitlines():
        key, _, _ = line.partition("=")
        if key in {"NoNewPrivileges", "ProtectSystem", "ProtectHome", "PrivateTmp", "UMask"}:
            assert line in unit, f"the role's unit dropped the packaged `{line}`"
    assert "python -I -m livespec_dev_tooling.incident_observer_service --config" in unit
    tasks = (_ROLE / "tasks" / "converge.yml").read_text(encoding="utf-8")
    assert "no_log: true" in tasks, "secret projection must never reach the run output"
    readme = (_ROLE / "README.md").read_text(encoding="utf-8")
    for step in (
        "LIVESPEC_INCIDENT_OBSERVER_URL",
        "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN",
        "fufpvkvatwkmqjzvilvfnemsue",
        "/callback",
    ):
        assert step in readme, f"the README must name the maintainer-only step `{step}`"
