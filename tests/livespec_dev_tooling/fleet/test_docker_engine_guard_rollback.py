"""Tests for the Docker engine install guard's rollback driver (child 2).

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback". Governing design:
`docs/docker-engine-guard-design.md` — F1's rollback, R4's ordering, G5,
H2's stop-first rule and H6's bounds.

The driver is reached only through 1a's dispatch table and touches the
host only through the `HostOps` protocol, so every assertion here runs
against 1a's `FakeHost` with an injected clock and state roots, and no
real host action ever fires. The fake stamps each seam call with the
phase recorded when it arrived, which is what lets an ORDERING between a
durable record and a host action be asserted at all.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

__all__: list[str] = []

_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"
_GUARD_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard"
_ROLLBACK_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_rollback"
_ROLLBACK_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_rollback.py")


def _fake(*, root: Path) -> Any:
    """A `FakeHost` rooted at `root`, with the two guard state roots under it."""
    fake_module = importlib.import_module(_FAKE_MODULE)
    return fake_module.FakeHost(state_root=root / "var", runtime_root=root / "run")


def _paths(*, root: Path) -> Any:
    """`GuardPaths` for the two state roots `_fake` also uses."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def _env(*, root: Path, host: Any) -> Any:
    """A `GuardEnv` over the same two state roots `_fake` and `_paths` use."""
    state = importlib.import_module(_STATE_MODULE)
    return state.GuardEnv(paths=_paths(root=root), host=host)


def _record_phase(*, root: Path, run: str, phase: str) -> None:
    """Put a reservation and a phase on disk the way the guard's records read."""
    state_root = root / "var"
    (state_root / "runs" / run).mkdir(parents=True, exist_ok=True)
    _ = (state_root / "run").write_text(run, encoding="utf-8")
    _ = (state_root / "runs" / run / "phase").write_text(phase, encoding="utf-8")


def _decision() -> Any:
    """The table's decision a rollback reaches the driver with."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.Decision(verdict="proceed", reason="rollback is allowed from started")


def _driver() -> Any:
    """The rollback driver, asserted to have replaced 1a's declared stub.

    1a shipped this module as a stub whose docstring says child 2
    replaces the file and whose entry raises, so the stub marker's
    absence is the first thing each assertion here can read: it fails on
    the stub and passes on the driver, which is a genuine assertion
    rather than an unimportable module.
    """
    assert _ROLLBACK_PATH.is_file()
    assert "CHILD 2 REPLACES THIS FILE" not in _ROLLBACK_PATH.read_text(encoding="utf-8")
    return importlib.import_module(_ROLLBACK_MODULE)


def _phase_of(*, root: Path, run: str) -> Any:
    """The run's recorded phase, read the way every guard operation reads it."""
    state = importlib.import_module(_STATE_MODULE)
    return state.read_phase(paths=_paths(root=root), run=run)


# The two phases a firing may REPLACE the recorded phase with. Anything
# else a firing leaves behind is a phase it overwrote without having
# reached an outcome, which is the one thing a later firing must not do.
_OUTCOME_PHASES = ("rolled-back", "rollback-partial")


def test_rollback_records_rolling_back_first_and_closes_start_and_confirm(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": `rolling-back` is recorded before any other step.

    The record is what closes the forward path: from the first
    `rolling-back` on, `start` and `confirm` are allowed from phases this
    run no longer has, so neither can act on it again. Recording it
    BEFORE anything else is what makes that true even of a driver killed
    immediately afterwards — the alternative is a run that was acted on
    and still looks startable.
    """
    rollback = _driver()
    guard = importlib.import_module(_GUARD_MODULE)
    fake = _fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")

    outcome = rollback.run_rollback(
        run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision()
    )

    assert outcome.operation == "rollback"
    assert outcome.exit_code == 0
    assert _phase_of(root=tmp_path, run="run-a") == "rolling-back"
    for closed in ("start", "confirm"):
        refused = guard.run_operation(
            operation=closed, run="run-a", env=_env(root=tmp_path, host=fake)
        )
        assert refused.verdict == "refuse", closed


def test_a_later_firing_keeps_the_recorded_phase_until_it_writes_an_outcome(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": a firing on the rollback path keeps the phase.

    The dead-man re-fires every 60 seconds after each rollback it runs,
    so most firings arrive on a run that is already `rolling-back` or
    already `rollback-partial`. A firing that re-recorded `rolling-back`
    over a `rollback-partial` would erase the one record an operator
    reads while deciding whether the host needs a repair, and would do
    it silently. The phase a firing leaves behind is therefore either the
    phase it came in with or the outcome it reached, never a third thing.
    """
    rollback = _driver()

    for incoming in ("rolling-back", "rollback-partial"):
        root = tmp_path / incoming
        fake = _fake(root=root)
        _record_phase(root=root, run="run-a", phase=incoming)

        _ = rollback.run_rollback(run="run-a", env=_env(root=root, host=fake), decision=_decision())

        kept = _phase_of(root=root, run="run-a")
        assert kept == incoming or kept in _OUTCOME_PHASES, incoming
