"""Protected installation policy refuses candidate-owned or mismatched runtime state."""

from __future__ import annotations

# ruff: noqa: SLF001 -- White-box tests exercise each protected filesystem boundary.
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_controller_installation as installation

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@pytest.fixture
def host(tmp_path, monkeypatch):
    for name in ("state", "repo"):
        (tmp_path / name).mkdir(mode=0o700)
    for name, body in (("webhook", b"a" * 32), ("control", b"b" * 32), ("query", b"c" * 32)):
        (tmp_path / name).write_bytes(body)
        (tmp_path / name).chmod(0o600)
    executable = str(Path(sys.executable).resolve())
    real_protected = installation.protected_path
    # Controlled deployment fixture: this developer venv is group-writable, so
    # emulate its separately provisioned executable only; real path tests below
    # still reject every unsafe ancestor rather than changing production policy.
    monkeypatch.setattr(
        installation,
        "protected_path",
        lambda *, path: path in {Path(executable), Path(sys.executable)}
        or real_protected(path=path),
    )
    manifest = {
        "release": "v1.0.0",
        "revision": "a" * 40,
        "package_sha256": "protected-build",
        "reader": [executable],
        "reader_release": "v0.282.0",
        "principal": [executable],
        "files": {executable: hashlib.sha256(Path(executable).read_bytes()).hexdigest()},
        "required_jobs": ["unit", "coverage"],
    }
    config = {
        "manifest": str(tmp_path / "manifest.json"),
        "candidate_uid": os.geteuid() + 1,
        "repository": "owner/repo",
        "repo": str(tmp_path / "repo"),
        "state": str(tmp_path / "state"),
        "webhook_secret": str(tmp_path / "webhook"),
        "control_secret": str(tmp_path / "control"),
        "query_secret": str(tmp_path / "query"),
        "port": 8765,
    }
    monkeypatch.setattr(installation.importlib.metadata, "version", lambda _: "1.0.0")
    monkeypatch.setattr(installation, "_package_digest", lambda **_: "protected-build")

    def write():
        for name, data in (("config.json", config), ("manifest.json", manifest)):
            path = tmp_path / name
            path.write_text(json.dumps(data))
            path.chmod(0o600)
        return tmp_path / "config.json"

    return tmp_path, config, manifest, write


def test_protected_manifest_selects_exact_installed_controller_and_commands(host):
    root, _, manifest, write = host
    result = installation.ControllerInstallation.load(config=write())
    assert result is not None
    assert result.state == root / "state"
    assert result.reader == tuple(manifest["reader"])
    assert result.principal == tuple(manifest["principal"])
    assert result.revision == "a" * 40
    assert result.jobs == ("unit", "coverage")


@pytest.mark.parametrize(
    "change",
    [
        "config-keys",
        "same-uid",
        "bad-uid",
        "missing-manifest",
        "manifest-keys",
        "release",
        "revision",
        "revision-hex",
        "package",
        "files-type",
        "digest",
        "relative-command",
        "unhashed-command",
        "empty-command",
        "command-type",
        "arg-type",
        "not-executable",
        "state-mode",
        "state-missing",
        "state-in-repo",
        "relative-repo",
        "jobs-empty",
        "jobs-type",
        "job-empty",
        "job-type",
        "job-duplicate",
        "secret-short",
        "secret-same",
        "query-short",
        "query-control",
        "query-webhook",
        "query-mode",
        "secret-mode",
        "bad-port",
        "bool-port",
        "malformed-json",
    ],
)
def test_invalid_installation_never_returns_serving_settings(host, change):
    root, config, manifest, write = host
    program = root / "program"
    program.write_text("readonly")
    program.chmod(0o600)
    actions = {
        "config-keys": lambda: config.update(request_command="candidate"),
        "same-uid": lambda: config.update(candidate_uid=os.geteuid()),
        "bad-uid": lambda: config.update(candidate_uid="1001"),
        "missing-manifest": lambda: config.update(manifest=str(root / "absent")),
        "manifest-keys": lambda: manifest.update(candidate=True),
        "release": lambda: manifest.update(release="v9"),
        "revision": lambda: manifest.update(revision=3),
        "revision-hex": lambda: manifest.update(revision="x" * 40),
        "package": lambda: manifest.update(package_sha256="foreign"),
        "files-type": lambda: manifest.update(files=[]),
        "digest": lambda: manifest["files"].update({manifest["reader"][0]: "foreign"}),
        "relative-command": lambda: manifest.update(reader=["python"]),
        "unhashed-command": lambda: manifest.update(reader=[str(root / "absent")]),
        "empty-command": lambda: manifest.update(reader=[]),
        "command-type": lambda: manifest.update(reader="python"),
        "arg-type": lambda: manifest.update(reader=[1]),
        "not-executable": lambda: manifest.update(reader=[str(program)]),
        "state-mode": lambda: (root / "state").chmod(0o755),
        "state-missing": lambda: config.update(state=str(root / "absent")),
        "state-in-repo": lambda: config.update(repo=str(root)),
        "relative-repo": lambda: config.update(repo="candidate"),
        "jobs-empty": lambda: manifest.update(required_jobs=[]),
        "jobs-type": lambda: manifest.update(required_jobs="unit"),
        "job-empty": lambda: manifest.update(required_jobs=[""]),
        "job-type": lambda: manifest.update(required_jobs=[3]),
        "job-duplicate": lambda: manifest.update(required_jobs=["unit", "unit"]),
        "secret-short": lambda: (root / "webhook").write_bytes(b"short"),
        "secret-same": lambda: config.update(control_secret=config["webhook_secret"]),
        "query-short": lambda: (root / "query").write_bytes(b"short"),
        "query-control": lambda: config.update(query_secret=config["control_secret"]),
        "query-webhook": lambda: config.update(query_secret=config["webhook_secret"]),
        "query-mode": lambda: (root / "query").chmod(0o644),
        "secret-mode": lambda: (root / "control").chmod(0o644),
        "bad-port": lambda: config.update(port=65536),
        "bool-port": lambda: config.update(port=True),
        "malformed-json": lambda: config.update(port=None),
    }
    actions[change]()
    assert installation.ControllerInstallation.load(config=write()) is None


def test_protected_path_checks_link_target_and_every_ancestor(tmp_path, monkeypatch):
    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    program = safe / "reader"
    program.write_text("protected")
    program.chmod(0o500)
    link = tmp_path / "link"
    link.symlink_to(program)
    assert installation.protected_path(path=link)
    assert not installation.protected_path(path=Path("relative"))
    assert not installation.protected_path(path=tmp_path / "missing")
    safe.chmod(0o777)
    assert not installation.protected_path(path=link)
    safe.chmod(0o700)
    original = Path.lstat

    def foreign_link(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        values = list(info)
        values[4] = {link: os.geteuid() + 100}.get(path, info.st_uid)
        return os.stat_result(values)

    monkeypatch.setattr(Path, "lstat", foreign_link)
    assert not installation.protected_path(path=link)


def test_record_secret_and_command_boundaries(host):
    root, _, manifest, write = host
    path = write()
    path.write_text("[]")
    assert installation._record(path=path) is None
    path.chmod(0o644)
    assert installation._record(path=path) is None
    assert installation._secret(path=root / "missing") is None
    manifest["reader"] = [*manifest["reader"], "-I"]
    assert installation._command_files(manifest=manifest, files=manifest["files"])


def test_package_digest_covers_source_and_loaded_dependency_paths(tmp_path, monkeypatch):
    source = tmp_path / "module.py"
    source.write_bytes(b"pass\n")
    source.chmod(0o600)
    monkeypatch.setattr(
        installation.sys,
        "modules",
        {"controlled": SimpleNamespace(__file__=str(source)), "builtin": SimpleNamespace()},
    )
    expected = hashlib.sha256(b"module.py\0pass\n").hexdigest()
    assert installation._package_digest(root=tmp_path) == expected
    source.chmod(0o666)
    assert installation._package_digest(root=tmp_path) is None
    source.chmod(0o600)
    dependency = tmp_path / "foreign.bin"
    dependency.write_bytes(b"external")
    dependency.chmod(0o666)
    monkeypatch.setattr(
        installation.sys, "modules", {"external": SimpleNamespace(__file__=str(dependency))}
    )
    assert installation._package_digest(root=tmp_path) is None


def test_malformed_host_record_is_named_refusal(host):
    _, _, _, write = host
    path = write()
    path.write_text("{")
    assert installation.ControllerInstallation.load(config=path) is None


def test_unhashed_script_and_foreign_target_are_refused(host, tmp_path, monkeypatch):
    _, _, manifest, _ = host
    manifest["reader"].append(str(tmp_path / "unlisted-script"))
    assert not installation._command_files(manifest=manifest, files=manifest["files"])
    target = tmp_path / "protected-target"
    target.write_text("protected")
    link = tmp_path / "service-owned-link"
    link.symlink_to(target)
    original = Path.stat

    def foreign_target(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        values = list(info)
        values[4] = {link: os.geteuid() + 100}.get(path, info.st_uid)
        return os.stat_result(values)

    monkeypatch.setattr(Path, "stat", foreign_target)
    assert not installation.protected_path(path=link)


def test_sudo_credential_wrapper_cannot_be_selected_by_confined_controller(host):
    _, _, manifest, _ = host
    manifest["reader"] = ["/usr/local/bin/with-livespec-env.sh", "--", *manifest["reader"]]
    assert not installation._command_files(manifest=manifest, files=manifest["files"])
