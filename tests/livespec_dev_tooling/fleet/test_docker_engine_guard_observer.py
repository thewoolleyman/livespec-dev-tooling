"""Tests for the Docker engine install guard's observer and commit half (child 1b).

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- "Observe and the challenge",
"Commit" and "After the commit". Governing design:
`docs/docker-engine-guard-design.md`: F4, G2's `confirm`, G4, H2's
observer rules, H3, H5, I2's `confirm`, `verify` and `reconfigure` rows,
and rider points 5 and 9.

The guard is six factory-safe children sharing one module set; this file
covers 1b -- `observe`, `confirm`, `verify` and `reconfigure`, plus the
records they hand each other (the evidence record, the challenge, the
spent nonces and the owned-keys digest). The host is reached only
through the `HostOps` protocol, so everything here runs against
`FakeHost` with an injected clock, boot id and state roots, and no real
host action ever fires.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

__all__: list[str] = []

_OBSERVER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_observer"
_OBSERVER_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_observer.py")
_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"

# The observation window every test here drives, and the interval the
# observer samples at. Short on purpose: each assertion is about the
# ORDER of what the observer does, and the real 420-second window would
# say the same thing twenty-eight times over.
_WINDOW_SECONDS = 30


def _fake(*, root: Path) -> Any:
    """A `FakeHost` rooted at `root`, with the two guard state roots under it."""
    fake_module = importlib.import_module(_FAKE_MODULE)
    return fake_module.FakeHost(state_root=root / "var", runtime_root=root / "run")


def _paths(*, root: Path) -> Any:
    """`GuardPaths` for the two state roots `_fake` also uses."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def _env(*, root: Path, host: Any, window: int = _WINDOW_SECONDS) -> Any:
    """A `GuardEnv` over those two roots, with a short observation window."""
    state = importlib.import_module(_STATE_MODULE)
    return state.GuardEnv(paths=_paths(root=root), host=host, window_seconds=window)


def _decision(*, verdict: str = "proceed") -> Any:
    """The table's decision, as the handler is always reached with it.

    The handlers under test never re-decide admission: by the time one
    runs, the lock is held, the run is the current reservation and the
    dispatch table has already admitted the invocation.
    """
    model = importlib.import_module(_MODEL_MODULE)
    return model.Decision(verdict=verdict, reason="admitted by the dispatch table")


def _record_phase(*, root: Path, run: str, phase: str) -> None:
    """Put a reservation and a phase on disk the way the guard's records read."""
    state_root = root / "var"
    (state_root / "runs" / run).mkdir(parents=True, exist_ok=True)
    (state_root / "run").write_text(run, encoding="utf-8")
    (state_root / "runs" / run / "phase").write_text(phase, encoding="utf-8")


def test_observe_claims_the_run_before_it_takes_its_first_sample(tmp_path: Path) -> None:
    """Specification "Observe and the challenge": `started` -> `observing` first.

    The claim is what makes the observer a singleton in FACT rather than
    only by unit name. An `observe` that sampled first and claimed
    afterwards would leave a window in which the run still reads
    `started` -- the one phase a second `observe` is admitted from -- so
    the phase is read back from the stamp the fake puts on each `sample`
    call rather than merely at the end.
    """
    assert _OBSERVER_PATH.is_file()
    observer = importlib.import_module(_OBSERVER_MODULE)
    fake = _fake(root=tmp_path)
    fake.sample_result = {"passed": True}
    _record_phase(root=tmp_path, run="run-a", phase="started")

    outcome = observer.observe(
        run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision()
    )

    assert [call.phase for call in fake.calls_named(name="sample")] == ["observing", "observing"]
    assert outcome.operation == "observe"
