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
import json
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_OBSERVER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_observer"
_OBSERVER_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_observer.py")
_RECORDS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_records"
_RECORDS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_records.py")
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


def test_observe_stops_sampling_once_the_run_has_left_observing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Specification "Observe and the challenge": a lock-held check ends the window.

    The observation window outlasts every other operation's whole
    budget, so the run genuinely can be taken away under it: a rollback
    records `rolling-back` before anything else, and from that moment
    nothing about this run may be carried forward. The observer
    therefore re-READS the phase record between samples rather than
    trusting the phase it claimed, and stops at the first reading that
    is no longer `observing`.
    """
    assert _OBSERVER_PATH.is_file()
    observer = importlib.import_module(_OBSERVER_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    fake = _fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")
    taken: list[str] = []

    def sample_then_take_the_run_away() -> dict[str, object]:
        """Answer one passing sample, and move the run out of `observing` with it."""
        taken.append("sample")
        _record_phase(root=tmp_path, run="run-a", phase="rolling-back")
        return {"passed": True}

    monkeypatch.setattr(fake, "sample", sample_then_take_the_run_away)

    outcome = observer.observe(
        run="run-a", env=_env(root=tmp_path, host=fake, window=300), decision=_decision()
    )

    assert taken == ["sample"]
    assert outcome.verdict == "refuse"
    assert outcome.exit_code == 1
    assert "observing" in outcome.reason
    # The observer records nothing over the run it no longer owns: the
    # phase it reads is the one the rollback wrote, untouched.
    assert state.read_phase(paths=_paths(root=tmp_path), run="run-a") == "rolling-back"


def _evidence(*, root: Path, run: str) -> dict[str, Any]:
    """The run's evidence record, read back the way an operator would read it."""
    records = importlib.import_module(_RECORDS_MODULE)
    path = records.evidence_path(paths=_paths(root=root), run=run)
    assert path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_failed_sample_records_it_and_triggers_a_rollback_it_never_waits_for(
    tmp_path: Path,
) -> None:
    """Specification "Observe and the challenge", the failed-sample sentence.

    Three things have to be true together, and each is a different kind
    of mistake to get wrong. The failure is RECORDED, so an operator can
    tell "Docker broke the pod network" from "CoreDNS restarted" after
    the host has already been put back. The rollback is started as its
    OWN transient unit, because this invocation holds the guard's one
    lock and the rollback entry takes that same lock -- calling it in
    process would deadlock. And the observer does not WAIT for it: it
    has nothing left to submit, so rollback's own stop of the observer
    unit is a no-op and neither waits on the other.
    """
    assert _RECORDS_PATH.is_file()
    observer = importlib.import_module(_OBSERVER_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    fake = _fake(root=tmp_path)
    fake.sample_result = {"passed": False, "probe": "dns", "error": "no answer from 10.43.0.10"}
    _record_phase(root=tmp_path, run="run-a", phase="started")

    outcome = observer.observe(
        run="run-a", env=_env(root=tmp_path, host=fake, window=300), decision=_decision()
    )

    evidence = _evidence(root=tmp_path, run="run-a")
    assert evidence["passed"] is False
    assert "dns" in evidence["failure"]
    assert evidence["samples"] == [dict(fake.sample_result)]
    assert evidence["run"] == "run-a"
    assert evidence["boot_id"] == "boot-a"
    # The window is 300 seconds at a 15-second interval, so a window that
    # ran on would have sampled twenty times: ONE sample is the proof that
    # the observer exited rather than carrying on over a doomed run.
    assert len(fake.calls_named(name="sample")) == 1
    assert fake.calls_named(name="systemd_run")[0].detail == model.rollback_argv(run="run-a")
    assert "--no-block" in model.rollback_argv(run="run-a")
    assert outcome.verdict == "refuse"
    assert "dns" in outcome.reason


def _challenge(*, root: Path) -> dict[str, Any]:
    """The challenge the observer issued, read from the runtime root."""
    records = importlib.import_module(_RECORDS_MODULE)
    path = records.challenge_path(paths=_paths(root=root))
    assert path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_passing_window_issues_a_challenge_under_the_runtime_root_then_observes(
    tmp_path: Path,
) -> None:
    """Specification "Observe and the challenge", the passing-window sentence.

    The challenge lives under the RUNTIME root rather than beside the
    durable records, and that placement is the mechanism rather than a
    filing convention: /run is tmpfs, so a reboot clears the challenge
    and an answer issued before that reboot can never be accepted after
    it. It carries the boot id for the same reason, so that a runtime
    root which somehow survived still cannot vouch for another boot.

    The run reaches `observed` only after the challenge is in place,
    which is the phase a `confirm` is admitted from: the other order
    would admit a `confirm` that had nothing to answer.
    """
    records = importlib.import_module(_RECORDS_MODULE)
    observer = importlib.import_module(_OBSERVER_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    paths = _paths(root=tmp_path)
    fake = _fake(root=tmp_path)
    fake.sample_result = {"passed": True}
    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    _record_phase(root=tmp_path, run="run-a", phase="started")

    outcome = observer.observe(
        run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision()
    )

    assert state.read_phase(paths=paths, run="run-a") == "observed"
    assert _evidence(root=tmp_path, run="run-a")["passed"] is True
    assert records.challenge_path(paths=paths) == paths.runtime_root / "challenge"
    challenge = _challenge(root=tmp_path)
    assert challenge["run"] == "run-a"
    assert challenge["boot_id"] == "boot-a"
    assert len(challenge["nonce"]) >= 32
    assert outcome.verdict == "proceed"
    assert outcome.exit_code == 0


def test_each_passing_window_issues_a_nonce_no_earlier_window_issued(tmp_path: Path) -> None:
    """Specification "Observe and the challenge": a fresh nonce every window.

    Freshness is what stops a replay. An answer carrying a nonce from an
    earlier window is an answer the controller could have prepared
    before this window ran -- so it would vouch for a host nobody
    observed, which is the one thing the challenge exists to prevent.
    Rider point 5 states the same rule from the other side: a challenge
    is RE-ISSUED rather than reused.

    Three windows rather than two, because a generator that alternated
    between two values would pass a two-window check.
    """
    observer = importlib.import_module(_OBSERVER_MODULE)
    records = importlib.import_module(_RECORDS_MODULE)
    paths = _paths(root=tmp_path)
    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    issued: list[str] = []

    for _window in range(3):
        fake = _fake(root=tmp_path)
        fake.sample_result = {"passed": True}
        _record_phase(root=tmp_path, run="run-a", phase="started")
        outcome = observer.observe(
            run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision()
        )
        assert outcome.verdict == "proceed"
        issued.append(_challenge(root=tmp_path)["nonce"])

    assert len(set(issued)) == 3
    assert [len(nonce) for nonce in issued] == [records.NONCE_BYTES * 2] * 3
