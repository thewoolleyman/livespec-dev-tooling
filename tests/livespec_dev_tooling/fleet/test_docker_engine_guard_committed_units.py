"""Tests for WHERE the post-commit validation reads the guarded units' running state.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "After the commit" (this
repository). Governing design: `docs/docker-engine-guard-design.md` F4
and rider point 9 -- the validation needs BOTH enablement and running
state, and neither implies the other.

Why this file exists rather than another case beside the lifecycle
tests. H-01 of the `docker_engine` role's acceptance suite ran on
2026-10-17 on a disposable guest carrying a real single-node k3s,
passed its canary and its commit point, and then had `confirm` refuse
with "these guarded units are not both enabled and running:
containerd.service, docker.service, docker.socket" while the service
manager on that same guest reported all three `enabled` and `active`.
The validation read running state through `guard_unit_states`, which
enumerates the GUARD's own units by glob -- so the three GUARDED units
were never in that map and every real committed run read as adrift.
The `FakeHost` answered that seam from one map that also held the
guarded units, so no test in the suite could see the divergence.

The fix is therefore only provable against the REAL host: these cases
drive `build_real_host` over RECORDED `systemctl` output, so what the
check reads is what a service manager actually answered for each named
unit. The guard-unit glob is recorded too, answering EMPTY -- the
committed host H-01 found, where the dead-man has been stopped and no
guard unit is loaded at all.

The modules under test are reached through `importlib` inside each test
body, the pattern the sibling host and lifecycle tests already use: a
top-level import of a module a Red moment has not created yet makes
that Red a COLLECTION error instead of a genuine assertion failure.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

__all__: list[str] = []

_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_runner"
_RECORDS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_records"
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_HOST_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_host"
_COMMIT_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_commit"
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"

_RUN = "r202610170154022b87"

_GUARDED_UNITS = ("containerd.service", "docker.service", "docker.socket")

# The admission read's own argv, recorded so a check that reaches for it
# gets the answer a COMMITTED host gives: nothing. The dead-man is
# stopped at the commit point by design, so no guard unit is loaded.
_GUARD_SHOW_ARGV = (
    "systemctl",
    "show",
    "--property",
    "Id",
    "--property",
    "ActiveState",
    "docker-engine-guard-*.service",
    "docker-engine-deadman-*.service",
    "docker-engine-deadman-*.timer",
)

_ADRIFT = "these guarded units are not both enabled and running: "


def _active_state_argv(*, unit: str) -> tuple[str, ...]:
    """The service manager's own report of one unit's `ActiveState`."""
    return ("systemctl", "show", "--property", "ActiveState", "--value", unit)


def _enabled_state_argv(*, unit: str) -> tuple[str, ...]:
    """The service manager's own report of one unit's `UnitFileState`."""
    return ("systemctl", "show", "--property", "UnitFileState", "--value", unit)


@dataclass(kw_only=True)
class _Systemctl:
    """A recorded `systemctl` standing in for the guard's one timed runner.

    An argv with no recorded answer comes back EMPTY rather than
    raising, which is exactly how the real tool behaves for a unit the
    manager does not know -- and keeping that behaviour here is what
    makes a read of the wrong map fail on a genuine assertion about the
    verdict rather than on a lookup error in the harness.
    """

    answers: dict[tuple[str, ...], str] = field(default_factory=dict)
    argvs: list[tuple[str, ...]] = field(default_factory=list)

    timeouts: list[int] = field(default_factory=list)

    def __call__(self, *, argv: Sequence[str], timeout_seconds: int) -> Any:
        key = tuple(argv)
        self.argvs.append(key)
        self.timeouts.append(timeout_seconds)
        runner = importlib.import_module(_RUNNER_MODULE)
        return runner.GuardCommandResult(argv=key, returncode=0, stdout=self.answers.get(key, ""))


def _service_manager_reporting(*, active: dict[str, str], enabled: dict[str, str]) -> _Systemctl:
    """A `systemctl` that answers these states for the three guarded units."""
    return _Systemctl(
        answers={
            _GUARD_SHOW_ARGV: "",
            **{_active_state_argv(unit=unit): f"{state}\n" for unit, state in active.items()},
            **{_enabled_state_argv(unit=unit): f"{state}\n" for unit, state in enabled.items()},
        }
    )


def _committed_env(*, root: Path, commands: _Systemctl) -> Any:
    """A `GuardEnv` over the real host, on a host this run has committed.

    The marker is published carrying this run's own owned-keys digest,
    so the only fault the validation can report is the one about the
    units -- which is the whole subject here.
    """
    model = importlib.import_module(_MODEL_MODULE)
    records = importlib.import_module(_RECORDS_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    host_module = importlib.import_module(_HOST_MODULE)
    paths = model.GuardPaths(state_root=root / "var", runtime_root=root / "run")
    _ = records.publish_marker(
        paths=paths, run=_RUN, digest=records.owned_keys_digest(paths=paths, run=_RUN)
    )
    host = host_module.build_real_host(
        paths=paths, runner=commands, proc_root=root / "proc", restart_marker=root / "restart"
    )
    return state.GuardEnv(paths=paths, host=host)


def test_the_committed_validation_reads_each_guarded_units_state_from_the_service_manager(
    tmp_path: Path,
) -> None:
    """A committed host whose three guarded units are up reports no fault.

    This is the case H-01 failed on, and the one the guard-unit map can
    never answer: at the commit point the dead-man has been stopped and
    no guard unit is loaded, so a validation reading running state from
    the guard's OWN units reads an empty map and reports all three
    guarded units adrift on every real committed run.

    The argv assertions are the point of the case rather than
    decoration: they are what says the running state came from the
    service manager's report FOR THAT UNIT, one read per unit, the way
    enablement beside it is already read.
    """
    commit = importlib.import_module(_COMMIT_MODULE)
    commands = _service_manager_reporting(
        active=dict.fromkeys(_GUARDED_UNITS, "active"),
        enabled=dict.fromkeys(_GUARDED_UNITS, "enabled"),
    )
    env = _committed_env(root=tmp_path, commands=commands)

    assert commit.committed_installation_fault(run=_RUN, env=env) == ""
    for unit in _GUARDED_UNITS:
        assert _active_state_argv(unit=unit) in commands.argvs
        assert _enabled_state_argv(unit=unit) in commands.argvs


def test_the_committed_validation_names_only_the_guarded_unit_that_is_not_running(
    tmp_path: Path,
) -> None:
    """One stopped daemon is named, and the two that are up are not.

    A validation that named all three whenever any one of them was down
    would tell an operator on a Tailscale-only host to repair two units
    that are fine, which is the same unusable signal H-01 got.
    """
    commit = importlib.import_module(_COMMIT_MODULE)
    commands = _service_manager_reporting(
        active={**dict.fromkeys(_GUARDED_UNITS, "active"), "docker.service": "inactive"},
        enabled=dict.fromkeys(_GUARDED_UNITS, "enabled"),
    )
    env = _committed_env(root=tmp_path, commands=commands)

    assert commit.committed_installation_fault(run=_RUN, env=env) == f"{_ADRIFT}docker.service"


def test_the_committed_validation_names_only_the_guarded_unit_that_is_not_enabled(
    tmp_path: Path,
) -> None:
    """A running unit that will not come back at the next boot is still a fault.

    Enablement and running state are read SEPARATELY and are allowed to
    disagree: a `docker.socket` that is up now but disabled is an engine
    that does not return after a reboot, and the validation is the last
    thing watching a committed host.
    """
    commit = importlib.import_module(_COMMIT_MODULE)
    commands = _service_manager_reporting(
        active=dict.fromkeys(_GUARDED_UNITS, "active"),
        enabled={**dict.fromkeys(_GUARDED_UNITS, "enabled"), "docker.socket": "disabled"},
    )
    env = _committed_env(root=tmp_path, commands=commands)

    assert commit.committed_installation_fault(run=_RUN, env=env) == f"{_ADRIFT}docker.socket"


def test_the_fake_host_holds_the_guards_own_units_and_the_guarded_units_in_separate_maps(
    tmp_path: Path,
) -> None:
    """The harness is what let the real divergence through, so it is fixed too.

    `FakeHost` answered BOTH unit-state seams from one map, and that one
    map held the guarded units as well as the guard's own. So a check
    reading the wrong seam got the right answer anyway and the whole
    suite stayed green while every real committed run refused.

    Two maps make that impossible: whatever the guard's own units are
    doing, `guard_unit_states` carries no state for `containerd.service`,
    `docker.service` or `docker.socket` -- which is also what the REAL
    host answers, since those three match none of the globs the
    admission read enumerates its units from.
    """
    fake_module = importlib.import_module(_FAKE_MODULE)
    fake = fake_module.FakeHost(state_root=tmp_path / "var", runtime_root=tmp_path / "run")

    assert "guarded_unit_states" in {declared.name for declared in fields(fake)}

    fake.unit_states = {"docker-engine-guard-start.service": "failed"}
    fake.guarded_unit_states = dict.fromkeys(_GUARDED_UNITS, "active")

    assert dict(fake.guarded_unit_active_states()) == dict.fromkeys(_GUARDED_UNITS, "active")
    assert dict(fake.guard_unit_states()) == {"docker-engine-guard-start.service": "failed"}
