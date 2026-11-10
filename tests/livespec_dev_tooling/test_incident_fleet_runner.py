"""The audit's subprocesses ignore the caller's environment: real processes, not fake runners.

Each steering probe from the independent review of livespec-dev-tooling#4016 runs here
against the real runner: a fake `systemctl` earlier on `PATH`, a `GIT_DIR` pointing at a
tree the caller wrote, and `GIT_CONFIG_*` / `GIT_CONFIG_GLOBAL` redirecting core's
manifest read. Each must leave the audit's answer unchanged.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.fleet._manifest_git import git_file_text
from livespec_dev_tooling.incident_fleet_cli import production_environment
from livespec_dev_tooling.incident_fleet_controller_reader import (
    OBSERVED_REPOSITORY,
    read_controller_serving,
)
from livespec_dev_tooling.incident_fleet_host import production_probe
from livespec_dev_tooling.incident_fleet_runner import (
    BINARY_DIRECTORIES,
    make_scrubbed_runner,
    resolve_binary,
    scrubbed_runner,
)
from livespec_dev_tooling.incident_fleet_serving import host_serving_reader
from tests.livespec_dev_tooling import test_incident_fleet_controller_reader as controller_tests

host = controller_tests.host
_FORGED = "v9.9.9@" + "f" * 40
_CALLER_VARIABLES = ("GIT_DIR", "GIT_CONFIG_COUNT", "GH_HOST", "SYSTEMD_PAGER", "XDG_CONFIG_HOME")


def _git(*args: str, cwd: Path) -> None:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    _ = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=clean)


def _child_environment(*, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for name in _CALLER_VARIABLES:
        monkeypatch.setenv(name, "caller-chosen")
    answer = unsafe_perform_io(scrubbed_runner(args=["env"]).unwrap())
    return dict(line.split("=", 1) for line in answer.stdout.splitlines() if "=" in line)


def test_the_child_gets_only_the_fixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    child = _child_environment(monkeypatch=monkeypatch)
    assert set(child) == {
        "PATH",
        "HOME",
        "LANG",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_TERMINAL_PROMPT",
    }
    assert child["PATH"] == os.pathsep.join(str(d) for d in BINARY_DIRECTORIES)
    assert child["GIT_CONFIG_NOSYSTEM"] == "1"
    assert child["GIT_CONFIG_GLOBAL"] == os.devnull


def test_a_call_with_no_working_directory_runs_from_the_filesystem_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    answer = unsafe_perform_io(scrubbed_runner(args=["pwd"]).unwrap())
    assert answer.stdout.strip() == "/"
    named = unsafe_perform_io(scrubbed_runner(args=["pwd"], cwd=tmp_path).unwrap())
    assert Path(named.stdout.strip()).resolve() == tmp_path.resolve()


def test_binaries_resolve_only_from_the_fixed_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    planted = tmp_path / "git"
    _ = planted.write_text("#!/bin/sh\nexit 0\n")
    planted.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    resolved = resolve_binary(name="git", directories=BINARY_DIRECTORIES)
    assert resolved is not None
    assert resolved.parent in BINARY_DIRECTORIES
    assert resolve_binary(name=str(planted), directories=BINARY_DIRECTORIES) is None
    assert resolve_binary(name="", directories=BINARY_DIRECTORIES) is None
    assert resolve_binary(name="git", directories=(tmp_path / "absent",)) is None


def test_a_binary_outside_the_fixed_directories_is_never_run() -> None:
    refused = scrubbed_runner(args=["3wcldx-no-such-binary"])
    assert isinstance(refused, IOFailure)
    assert unsafe_perform_io(refused.failure()).kind == BINARY_ABSENT
    assert isinstance(scrubbed_runner(args=[]), IOFailure)


def test_a_binary_that_cannot_be_started_is_a_failure_value(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    _ = broken.write_bytes(b"\x00\x01not an executable format")
    broken.chmod(0o755)
    refused = make_scrubbed_runner(directories=(tmp_path,))(args=["broken"])
    assert isinstance(refused, IOFailure)
    assert unsafe_perform_io(refused.failure()).kind == SPAWN_FAILED


def test_a_fake_systemctl_earlier_on_path_cannot_forge_the_controller_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def controller() -> str | None:
        probe = production_probe(run=scrubbed_runner)
        return read_controller_serving(probe=probe, repository=OBSERVED_REPOSITORY)

    honest = controller()
    marker = tmp_path / "fake-systemctl-ran"
    fake = tmp_path / "bin" / "systemctl"
    fake.parent.mkdir()
    _ = fake.write_text(
        f"#!/bin/sh\ntouch {marker}\n"
        f"printf 'ActiveState=active\\nSubState=running\\nMainPID={os.getpid()}\\n'\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ['PATH']}")
    steered = controller()
    assert steered == honest
    assert steered != _FORGED
    assert not marker.exists()


def test_git_dir_cannot_move_the_clones_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    honest = production_probe(run=scrubbed_runner).clones_root
    forged = tmp_path / "fake-projects" / "livespec-dev-tooling"
    forged.mkdir(parents=True)
    _git("init", "-q", cwd=forged)
    monkeypatch.setenv("GIT_DIR", str(forged / ".git"))
    steered = production_probe(run=scrubbed_runner).clones_root
    assert steered == honest
    assert steered != forged.parent


def _forged_core(*, root: Path) -> tuple[str, Path]:
    """A local `livespec` repository holding a caller-authored manifest."""
    text = '{"owner": "attacker"}\n'
    source = root / "work"
    source.mkdir()
    _git("init", "-q", "-b", "master", cwd=source)
    _ = (source / ".livespec-fleet-manifest.jsonc").write_text(text)
    _git("add", ".", cwd=source)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x", cwd=source)
    _git("clone", "-q", "--bare", str(source), str(root / "owner" / "livespec.git"), cwd=root)
    return text, root / "owner"


@pytest.mark.parametrize("route", ["count", "global"])
def test_caller_git_configuration_cannot_redirect_the_manifest_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    forged_text, forged_owner = _forged_core(root=tmp_path)
    key = f"url.file://{forged_owner}/.insteadOf"
    value = "https://github.com/3wcldx-steering-probe/"
    if route == "count":
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", key)
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", value)
    else:
        config = tmp_path / "caller.gitconfig"
        _ = config.write_text(f'[url "file://{forged_owner}/"]\n\tinsteadOf = {value}\n')
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    seen = unsafe_perform_io(
        scrubbed_runner(args=["git", "config", "--get-regexp", r"^url\."]).unwrap()
    )
    assert seen.stdout == ""
    read = git_file_text(
        run=scrubbed_runner,
        owner="3wcldx-steering-probe",
        repo="livespec",
        path=".livespec-fleet-manifest.jsonc",
    )
    assert isinstance(read, IOFailure) or unsafe_perform_io(read.unwrap()) != forged_text


def test_the_production_command_runs_through_the_scrubbed_runner() -> None:
    default = inspect.signature(production_environment).parameters["run"].default
    assert default is scrubbed_runner


def test_the_recovery_read_asks_the_forge_through_the_audits_own_runner(
    host: Any,
) -> None:
    ruleset = {
        "id": 7,
        "enforcement": "active",
        "target": "branch",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [{"actor_id": 987, "actor_type": "Integration", "bypass_mode": "always"}],
    }
    base = host.probe()
    forge: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        if args[0] != "gh":
            return base.run(args=args, cwd=cwd)
        forge.append(args)
        path = args[-1]
        body: object = (
            [ruleset]
            if path.endswith("/rulesets")
            else ruleset
            if "/rulesets/" in path
            else {"default_branch": "master"}
        )
        return IOSuccess(CommandResult(returncode=0, stdout=json.dumps(body), stderr=""))

    read = host_serving_reader(probe=replace(base, run=run))
    served = read(repository=OBSERVED_REPOSITORY, capability="recovery-authorization")
    assert served == f"v1.2.3@{controller_tests.COMMIT}+bypass-app-987"
    assert forge
    assert all(call[:2] == ["gh", "api"] for call in forge)


def test_a_forge_that_cannot_be_started_leaves_recovery_unverified(host: Any) -> None:
    base = host.probe()

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        if args[0] != "gh":
            return base.run(args=args, cwd=cwd)
        return IOFailure(InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="x"))

    read = host_serving_reader(probe=replace(base, run=run))
    assert read(repository=OBSERVED_REPOSITORY, capability="recovery-authorization") is None
