"""The manifest renderer binds an optional CI identity policy by its path and exact digest."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from livespec_dev_tooling import incident_controller_installation as installation
from tests.livespec_dev_tooling import test_incident_observer_role as role_tests

host = role_tests.host

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "ansible"
    / "roles"
    / "incident_observer"
    / "files"
    / "render_released_installation.py"
)
_PACKAGE_ROOT = Path(installation.__file__).resolve().parent


def renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_released_installation", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_a_rendered_policy_member_names_the_path_and_its_exact_digest(host) -> None:
    tmp_path, reader_script, config_path = host
    module = renderer()
    fields = {field.name for field in dataclasses.fields(module.ManifestInputs)}
    assert "ci_identity_policy" in fields
    policy = tmp_path / "ci-identity.json"
    policy.write_bytes(b'{"schema": 1}\n')
    rendered = {
        name: module.render_manifest(
            inputs=module.ManifestInputs(
                release="v1.2.3",
                revision="a" * 40,
                reader_release="v0.290.0",
                reader_script=reader_script,
                config=config_path,
                required_jobs=("ci-green",),
                interpreter=Path(sys.executable),
                ci_identity_policy=value,
            ),
            package_root=_PACKAGE_ROOT,
        )
        for name, value in (("with", policy), ("without", None))
    }
    assert rendered["with"]["ci_identity_policy"] == {
        "path": str(policy),
        "sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
    }
    assert "ci_identity_policy" not in rendered["without"]
    assert {k: v for k, v in rendered["with"].items() if k != "ci_identity_policy"} == rendered[
        "without"
    ]
    # An optional policy the loader cannot use never stops the installation loading.
    manifest_path = tmp_path / "released-installation.json"
    manifest_path.write_text(json.dumps(rendered["with"], indent=2, sort_keys=True) + "\n")
    manifest_path.chmod(0o600)
    loaded = installation.ControllerInstallation.load(config=config_path)
    assert loaded is not None
    assert loaded.ci_identity_policy is None


def test_the_command_line_renders_the_policy_member_only_when_asked(host, capsys) -> None:
    tmp_path, reader_script, config_path = host
    module = renderer()
    policy = tmp_path / "policy.json"
    policy.write_bytes(b"{}\n")
    argv = [
        "--release",
        "v" + importlib.metadata.version("livespec-dev-tooling"),
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
    assert module.main([*argv, "--ci-identity-policy", str(policy)]) == 0
    with_policy = json.loads(capsys.readouterr().out)
    assert module.main(argv) == 0
    without = json.loads(capsys.readouterr().out)
    assert with_policy["ci_identity_policy"]["path"] == str(policy)
    assert "ci_identity_policy" not in without
