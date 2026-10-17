"""The Docker engine install guard's dead-man: what BOUNDS it, and what RETIRES it.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- "Arm and the dead-man",
"Rollback" and "After the commit" (this repository). Governing design:
`docs/docker-engine-guard-design.md`, G5, H2 and H6.

Two defects in one lifecycle share this file because they are the same
concern read from its two ends. A dead-man that is never bounded holds
the guard lock forever when its rollback hangs; a dead-man that is never
retired keeps a timer in the air over a run that is already terminal,
and the role's own classify counts any non-inactive
`docker-engine-deadman-*` unit as a busy host -- so the host is refused
forever. Neither failure raises anything: the first presents as a lock
nobody holds any more, the second as a host that is simply never free.

Everything here runs against `FakeHost`, so the assertions are on the
seams the guard actually reaches: the `systemd_run` argv that arms the
dead-man, and the `stop_unit` calls that retire it.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

__all__: list[str] = []

_GUARD_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard"
_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_MODEL_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_model.py")
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"

# The observation window the design derives at preflight from the host's
# effective k3s resync periods. Only `observe`'s budget reads it; the
# dead-man's service budget is the flat rollback budget.
_WINDOW_SECONDS = 420


def _fake(*, root: Path) -> Any:
    """A `FakeHost` rooted at `root`, with the two guard state roots under it."""
    fake_module = importlib.import_module(_FAKE_MODULE)
    return fake_module.FakeHost(state_root=root / "var", runtime_root=root / "run")


def _paths(*, root: Path) -> Any:
    """`GuardPaths` for the two state roots `_fake` also uses."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def _env(*, root: Path, host: Any) -> Any:
    """A `GuardEnv` over those two roots, at the derived observation window."""
    state = importlib.import_module(_STATE_MODULE)
    return state.GuardEnv(paths=_paths(root=root), host=host, window_seconds=_WINDOW_SECONDS)


def _record_phase(*, root: Path, run: str, phase: str) -> None:
    """Put a reservation and a phase on disk the way the guard's records read."""
    state_root = root / "var"
    (state_root / "runs" / run).mkdir(parents=True, exist_ok=True)
    _ = (state_root / "run").write_text(run, encoding="utf-8")
    _ = (state_root / "runs" / run / "phase").write_text(phase, encoding="utf-8")


def _service_properties(*, argv: tuple[str, ...]) -> tuple[str, ...]:
    """Every `--property=` a `systemd-run` recipe passes, in its own order.

    The SERVICE properties alone: `--timer-property=` entries govern the
    timer half, which this comparison deliberately leaves out because
    the rollback unit has no timer at all.
    """
    return tuple(word for word in argv if word.startswith("--property="))


def test_the_dead_man_is_a_bounded_oneshot_carrying_the_rollbacks_stop_properties(
    tmp_path: Path,
) -> None:
    """Design H6: the dead-man's budget has to BOUND the rollback it runs.

    `systemd-run`'s default service type is `simple`, and for a `simple`
    service `TimeoutStartSec` bounds nothing once the process has
    started -- systemd considers such a unit started the moment it has
    forked. So the dead-man carried a 900-second budget that could not
    expire, and a rollback that hung while holding the guard lock (under
    SIGSTOP, FAULTS case C-03) was never killed and held the lock
    forever. `Type=oneshot` is what makes the budget bind: a oneshot
    unit is "starting" until its command EXITS.

    The three stop properties are the other half, and they are what
    makes the expiry reach anything. `TimeoutStopSec=30` bounds the
    stop, `KillMode=control-group` sends the signal to the rollback's
    whole cgroup rather than to its main process alone -- the driver
    spawns a child per phase -- and `SendSIGKILL=yes` is what ends a
    process that is stopped or ignoring SIGTERM.

    They are asserted as the rollback unit's OWN property set rather
    than as five strings, because that is the actual rule: the recipe
    `rollback_argv` builds for a triggered rollback already runs under
    exactly these bounds, the dead-man runs the same `rollback <run>`
    command, and the two drifting apart is how this defect arose.

    The timer half is asserted unchanged in the same breath. With
    `Type=oneshot` the service goes inactive when the rollback exits, so
    `--on-unit-inactive` still re-fires it 60 seconds later -- the
    repeat is what lets a rollback killed half way simply be repeated,
    and a fix that bounded the service by retiring the repeat would
    trade one defect for another.
    """
    assert _MODEL_PATH.is_file()
    guard = importlib.import_module(_GUARD_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    fake = _fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="published")

    outcome = guard.run_operation(operation="arm", run="run-a", env=_env(root=tmp_path, host=fake))

    assert outcome.exit_code == 0
    armed = fake.calls_named(name="systemd_run")[0].detail
    budget = model.operation_budget_seconds(operation="rollback", window_seconds=0)
    assert f"--property=TimeoutStartSec={budget}" in armed
    assert "--property=Type=oneshot" in armed
    assert "--property=TimeoutStopSec=30" in armed
    assert "--property=KillMode=control-group" in armed
    assert "--property=SendSIGKILL=yes" in armed
    assert _service_properties(argv=armed) == _service_properties(
        argv=model.rollback_argv(run="run-a")
    )
    assert "--on-unit-inactive=60" in armed
    assert "--timer-property=AccuracySec=1s" in armed
    assert "--collect" in armed
    assert armed[-2:] == ("rollback", "run-a")
