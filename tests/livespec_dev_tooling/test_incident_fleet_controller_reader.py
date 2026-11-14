"""The controller's serving version is read from the RUNNING observer process, nothing else."""

from __future__ import annotations

import importlib.metadata
import json
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
import yaml
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling import incident_fleet_controller_reader as controller_reader
from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.incident_fleet_controller_reader import (
    OBSERVED_REPOSITORY,
    read_controller_serving,
)
from livespec_dev_tooling.incident_fleet_host import HostProbe
from livespec_dev_tooling.incident_fleet_serving import host_serving_reader

COMMIT = "c" * 40
BOOT = 1_000_000
PID = 4242
CONFIG = "/etc/livespec-incident/controller.json"
_UNIT_ARGV = ["-I", "-m", "livespec_dev_tooling.incident_observer_service", "--config", CONFIG]


def _stat_line(*, started_at: float) -> str:
    ticks = int((started_at - BOOT) * os.sysconf("SC_CLK_TCK"))
    after_comm = ["S", *["0"] * 18, str(ticks), "0"]
    return f"{PID} (python) " + " ".join(after_comm)


class _Host:
    """A fixture observer: a venv with its installed distribution, and a /proc entry."""

    def __init__(self, *, root: Path) -> None:
        self.root = root
        self.venv = root / "opt" / "venv"
        self.dist = (
            self.venv
            / "lib"
            / "python3.12"
            / "site-packages"
            / "livespec_dev_tooling-1.2.3.dist-info"
        )
        self.dist.mkdir(parents=True)
        _ = (self.dist / "METADATA").write_text("Metadata-Version: 2.1\nName: x\nVersion: 1.2.3\n")
        _ = (self.dist / "direct_url.json").write_text(
            json.dumps({"url": "https://example.test/r.git", "vcs_info": {"commit_id": COMMIT}})
        )
        self.proc = root / "proc"
        (self.proc / str(PID)).mkdir(parents=True)
        _ = (self.proc / "stat").write_text(f"cpu 1 2 3\nbtime {BOOT}\n")
        self.write_process(started_at=time.time() + 60)
        self.state = "ActiveState=active\nSubState=running\nMainPID=" + str(PID) + "\n"
        self.asked: list[list[str]] = []

    def argv(self) -> list[str]:
        return [
            str(self.venv / "bin" / "python"),
            "-I",
            "-m",
            "livespec_dev_tooling.incident_observer_service",
            "--config",
            CONFIG,
        ]

    def write_process(self, *, started_at: float, argv: list[str] | None = None) -> None:
        raw = "\0".join(self.argv() if argv is None else argv) + "\0"
        _ = (self.proc / str(PID) / "cmdline").write_bytes(raw.encode())
        _ = (self.proc / str(PID) / "stat").write_text(_stat_line(started_at=started_at))

    def probe(self, *, answer: CommandOutcome | None = None) -> HostProbe:
        def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
            _ = cwd
            self.asked.append(args)
            return answer or IOSuccess(CommandResult(returncode=0, stdout=self.state, stderr=""))

        return HostProbe(clones_root=None, proc_root=self.proc, home=self.root, run=run)

    def read(self, *, answer: CommandOutcome | None = None) -> str | None:
        return read_controller_serving(
            probe=self.probe(answer=answer), repository=OBSERVED_REPOSITORY
        )


@pytest.fixture
def host(tmp_path: Path) -> _Host:
    return _Host(root=tmp_path)


def test_the_running_observers_installed_release_and_revision_are_its_serving_version(
    host: _Host,
) -> None:
    assert host.read() == f"v1.2.3@{COMMIT}"
    assert host.asked[0][:2] == ["systemctl", "show"]
    assert "livespec-incident-observer.service" in host.asked[0]


def test_the_observed_repository_unit_and_command_are_the_deployed_ones() -> None:
    root = Path(__file__).resolve().parents[2]
    role = (root / "ansible/roles/incident_observer/defaults/main.yml").read_text(encoding="utf-8")
    assert f"incident_observer_repository: {OBSERVED_REPOSITORY}\n" in role
    assert "incident_observer_unit_name: livespec-incident-observer\n" in role
    assert f"incident_observer_config_path: {CONFIG}\n" in role
    unit = (root / "livespec_dev_tooling/data/incident-observer.service").read_text(
        encoding="utf-8"
    )
    assert " ".join(_UNIT_ARGV) in unit


def test_another_repository_has_no_independent_controller_and_nothing_is_asked(
    host: _Host,
) -> None:
    assert (
        read_controller_serving(probe=host.probe(), repository="thewoolleyman/livespec-runtime")
        is None
    )
    assert host.asked == []


@pytest.mark.parametrize(
    "state",
    [
        "ActiveState=inactive\nSubState=dead\nMainPID=0\n",
        "ActiveState=failed\nSubState=failed\nMainPID=0\n",
        "ActiveState=activating\nSubState=auto-restart\nMainPID=0\n",
        "ActiveState=active\nSubState=exited\nMainPID=4242\n",
        "ActiveState=active\nSubState=running\nMainPID=0\n",
        "ActiveState=active\nSubState=running\nMainPID=notanumber\n",
        "ActiveState=active\nSubState=running\n",
        "",
    ],
)
def test_a_stopped_or_unreachable_observer_is_unverified(host: _Host, state: str) -> None:
    host.state = state
    assert host.read() is None


def test_an_unanswered_or_failed_systemctl_is_unverified(host: _Host) -> None:
    refused = IOFailure(InvocationNotPerformed(argv=("systemctl",), kind=BINARY_ABSENT, detail="x"))
    assert host.read(answer=refused) is None
    assert (
        host.read(answer=IOSuccess(CommandResult(returncode=1, stdout=host.state, stderr="")))
        is None
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["{python}", "-I", "-m", "livespec_dev_tooling.incident_observer_service"],
        [
            "{python}",
            "-I",
            "-m",
            "livespec_dev_tooling.incident_observer_service",
            "--config",
            "/etc/o.json",
        ],
        ["{python}", "-I", "-m", "livespec_dev_tooling.other", "--config", CONFIG],
        ["{python}", *_UNIT_ARGV, "--extra"],
        ["python", *_UNIT_ARGV],
        ["{venv}/python", *_UNIT_ARGV],
        ["{python}", *_UNIT_ARGV[1:]],
    ],
)
def test_a_process_that_is_not_the_released_observer_unit_is_unverified(
    host: _Host, argv: list[str]
) -> None:
    resolved = [a.replace("{python}", str(host.venv / "bin" / "python")) for a in argv]
    resolved = [a.replace("{venv}", str(host.venv)) for a in resolved]
    host.write_process(started_at=time.time() + 60, argv=resolved)
    assert host.read() is None


def test_an_unreadable_process_entry_is_unverified(host: _Host) -> None:
    (host.proc / str(PID) / "cmdline").unlink()
    assert host.read() is None


def test_a_process_whose_start_time_cannot_be_read_is_unverified(host: _Host) -> None:
    _ = (host.proc / str(PID) / "stat").write_text("garbage")
    assert host.read() is None
    (host.proc / str(PID) / "stat").unlink()
    assert host.read() is None
    host.write_process(started_at=time.time() + 60)
    _ = (host.proc / "stat").write_text("cpu 1 2 3\n")
    assert host.read() is None


def test_an_observer_started_before_its_package_was_last_installed_is_unverified(
    host: _Host,
) -> None:
    host.write_process(started_at=time.time() - 3600)
    assert host.read() is None


def test_a_venv_without_exactly_one_installed_distribution_is_unverified(
    host: _Host, tmp_path: Path
) -> None:
    second = host.dist.parent / "livespec_dev_tooling-9.9.9.dist-info"
    second.mkdir()
    assert host.read() is None
    second.rmdir()
    for name in ("METADATA", "direct_url.json"):
        _ = (host.dist / name).rename(tmp_path / name)
        assert host.read() is None
        _ = (tmp_path / name).rename(host.dist / name)
    assert host.read() == f"v1.2.3@{COMMIT}"


@pytest.mark.parametrize(
    "metadata",
    ["Name: x\n", "Name: x\nVersion:\n", "Version: \n"],
)
def test_an_installed_distribution_that_names_no_version_is_unverified(
    host: _Host, metadata: str
) -> None:
    _ = (host.dist / "METADATA").write_text(metadata)
    host.write_process(started_at=time.time() + 60)
    assert host.read() is None


@pytest.mark.parametrize(
    "direct_url",
    [
        "not json",
        "[]",
        json.dumps({"url": "file:///x", "dir_info": {"editable": True}}),
        json.dumps({"vcs_info": {"commit_id": "tag-name"}}),
        json.dumps({"vcs_info": {"commit_id": 7}}),
        json.dumps({"vcs_info": []}),
    ],
)
def test_an_install_that_is_not_an_exact_vcs_revision_is_unverified(
    host: _Host, direct_url: str
) -> None:
    _ = (host.dist / "direct_url.json").write_text(direct_url)
    host.write_process(started_at=time.time() + 60)
    assert host.read() is None


def test_it_never_reads_the_auditors_own_package_or_a_release_name(
    host: _Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    own_version = Mock(side_effect=AssertionError("the auditor's own distribution was consulted"))
    monkeypatch.setattr(importlib.metadata, "version", own_version)
    assert host.read() == f"v1.2.3@{COMMIT}"
    assert own_version.call_count == 0


_SECOND = "thewoolleyman/livespec"
_SECOND_UNIT = "livespec-incident-observer-livespec.service"
_SECOND_CONFIG = "/etc/livespec-incident/controller-livespec.json"


def _serve_second(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        controller_reader, "SERVED_REPOSITORIES", (OBSERVED_REPOSITORY, _SECOND), raising=False
    )


def _second_argv(host: _Host, *, config: str) -> list[str]:
    return [*host.argv()[:-1], config]


def test_a_served_repository_is_read_from_its_own_installations_unit_and_configuration(
    host: _Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_second(monkeypatch)
    host.write_process(started_at=time.time() + 60, argv=_second_argv(host, config=_SECOND_CONFIG))
    assert read_controller_serving(probe=host.probe(), repository=_SECOND) == f"v1.2.3@{COMMIT}"
    assert host.asked
    assert all(_SECOND_UNIT in call for call in host.asked)


def test_a_served_repository_never_counts_another_installations_process(
    host: _Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_second(monkeypatch)
    assert read_controller_serving(probe=host.probe(), repository=_SECOND) is None


def test_this_librarys_reading_is_unchanged_when_other_repositories_are_served(
    host: _Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_second(monkeypatch)
    assert host.read() == f"v1.2.3@{COMMIT}"
    assert all("livespec-incident-observer.service" in call for call in host.asked)


def test_a_process_started_with_the_scratch_configuration_is_never_read(host: _Host) -> None:
    scratch = "/etc/livespec-incident/controller-scratch-thhgeg.json"
    host.write_process(started_at=time.time() + 60, argv=_second_argv(host, config=scratch))
    assert host.read() is None


@pytest.mark.parametrize(
    "served",
    [
        (OBSERVED_REPOSITORY, "thewoolleyman/Not_Safe"),
        (OBSERVED_REPOSITORY, "thewoolleyman/scratch"),
        (OBSERVED_REPOSITORY, "thewoolleyman/livespec", "someone-else/livespec"),
    ],
)
def test_a_served_name_that_is_unsafe_scratch_or_shared_is_unverified_with_nothing_asked(
    host: _Host, monkeypatch: pytest.MonkeyPatch, served: tuple[str, ...]
) -> None:
    monkeypatch.setattr(controller_reader, "SERVED_REPOSITORIES", served, raising=False)
    assert read_controller_serving(probe=host.probe(), repository=served[1]) is None
    assert host.asked == []


_ROLE_DEFAULTS = "ansible/roles/incident_observer/defaults/main.yml"
_INVENTORY_KEY = "incident_observer_installations"


def _yaml(*, path: Path) -> dict[str, object]:
    loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast("dict[str, object]", loaded) if isinstance(loaded, dict) else {}


def _inventory_like(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    entries = cast("list[object]", value)
    return all(
        isinstance(entry, dict) and "repository" in cast("dict[str, object]", entry)
        for entry in entries
    )


def test_the_served_repositories_are_the_observer_roles_committed_inventory() -> None:
    root = Path(__file__).resolve().parents[2]
    inventory = _yaml(path=root / _ROLE_DEFAULTS).get(_INVENTORY_KEY)
    assert _inventory_like(inventory), f"{_ROLE_DEFAULTS} declares no {_INVENTORY_KEY} list"
    entries = cast("list[dict[str, str]]", inventory)
    declared = tuple(entry["repository"] for entry in entries)
    assert getattr(controller_reader, "SERVED_REPOSITORIES", None) == declared


def test_no_other_role_or_inventory_key_declares_a_repository_inventory() -> None:
    root = Path(__file__).resolve().parents[2]
    sources = [
        root / _ROLE_DEFAULTS,
        *sorted((root / "ansible/roles/incident_observer/vars").glob("*.yml")),
        *sorted((root / "ansible/inventory/host_vars").glob("*.yml")),
        *sorted((root / "ansible/inventory/group_vars").glob("*.yml")),
    ]
    stray = [
        f"{path.relative_to(root)}: {key}"
        for path in sources
        for key, value in _yaml(path=path).items()
        if _inventory_like(value) and not (path == root / _ROLE_DEFAULTS and key == _INVENTORY_KEY)
    ]
    assert stray == []


def test_the_recovery_reading_for_a_served_repository_asks_that_repositorys_own_unit(
    host: _Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    second = "thewoolleyman/livespec"
    monkeypatch.setattr(
        controller_reader,
        "SERVED_REPOSITORIES",
        (OBSERVED_REPOSITORY, second),
        raising=False,
    )
    config = "/etc/livespec-incident/controller-livespec.json"
    host.write_process(started_at=time.time() + 60, argv=[*host.argv()[:-1], config])
    ruleset = {
        "id": 7,
        "enforcement": "active",
        "target": "branch",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [{"actor_id": 987, "actor_type": "Integration", "bypass_mode": "always"}],
    }
    base = host.probe()
    units: list[str] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        if args[0] == "systemctl":
            units.append(args[2])
            return base.run(args=args, cwd=cwd)
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
    served = read(repository=second, capability="recovery-authorization")
    assert served == f"v1.2.3@{COMMIT}+bypass-app-987"
    assert units == ["livespec-incident-observer-livespec.service"]
