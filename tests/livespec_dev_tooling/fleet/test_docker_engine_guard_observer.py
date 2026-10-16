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
_COMMIT_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_commit"
_COMMIT_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_commit.py")
_GUARD_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard"
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


def _ready_to_confirm(
    *,
    root: Path,
    nonce: str = "nonce-of-the-current-window",
    answer: str | None = None,
    boot: str = "boot-a",
    issued: float = 0.0,
    passed: bool = True,
    deadline: float = 10_000.0,
) -> None:
    """Put `run-a` at `observed` carrying everything a `confirm` reads.

    Written by hand rather than by running the observer, so each clause
    of the commit rule can be falsified one at a time: a window that
    failed, a challenge from another boot, an answer carrying the wrong
    nonce. Driving the observer would make every clause true at once,
    which is the one arrangement that proves nothing about any of them.
    """
    records = importlib.import_module(_RECORDS_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    paths = _paths(root=root)
    _record_phase(root=root, run="run-a", phase="observed")
    state.write_deadline(
        paths=paths,
        run="run-a",
        deadline=model.Deadline(boot_id="boot-a", monotonic=deadline),
    )
    paths.inputs_dir(run="run-a").mkdir(parents=True, exist_ok=True)
    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    (paths.inputs_dir(run="run-a") / "challenge-answer").write_text(
        nonce if answer is None else answer, encoding="utf-8"
    )
    records.write_challenge(
        paths=paths,
        challenge=records.Challenge(
            run="run-a", boot_id=boot, nonce=nonce, issued_monotonic=issued
        ),
    )
    records.write_evidence(
        paths=paths,
        run="run-a",
        evidence=records.Evidence(
            run="run-a",
            boot_id="boot-a",
            digest=records.owned_keys_digest(paths=paths, run="run-a"),
            window_start=0.0,
            window_end=1.0,
            samples=({"passed": True},),
            passed=passed,
            failure="" if passed else "sample 1 of the observation window failed",
        ),
    )


def _confirm_refuses(*, root: Path, clause: str) -> None:
    """Require a `confirm` on this host to refuse and to commit nothing.

    "Commit nothing" is the half worth asserting: a refusal that had
    already written the marker would have committed a host it then
    reported as refused, and the marker is the one fact every later
    dispatch reads.
    """
    commit = importlib.import_module(_COMMIT_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    fake = _fake(root=root)
    fake.clock = 1.0

    outcome = commit.confirm(run="run-a", env=_env(root=root, host=fake), decision=_decision())

    assert outcome.verdict == "refuse", clause
    assert state.read_marker(paths=_paths(root=root), run="run-a") == "absent", clause
    assert clause in outcome.reason, clause


def _confirm_through_the_guard(*, root: Path) -> Any:
    """Run a `confirm` through the lock and the dispatch table, as the role does.

    The deadline clause lives in the table rather than in the handler, so
    a case that exercises it has to come through the whole guard rather
    than straight to `confirm`.
    """
    guard = importlib.import_module(_GUARD_MODULE)
    fake = _fake(root=root)
    fake.clock = 1.0
    return guard.run_operation(operation="confirm", run="run-a", env=_env(root=root, host=fake))


def test_confirm_commits_only_with_passing_evidence_and_this_boots_matching_nonce(
    tmp_path: Path,
) -> None:
    """Specification "Commit", the first sentence, clause by clause.

    Each clause is falsified on its own, because each is a different way
    for a confirmation to be worthless. Evidence that does not record a
    pass means nobody watched the host. A challenge from another boot
    means the answer was prepared against a machine that has since
    rebooted. An answer carrying the wrong nonce means it was prepared
    before this window ran at all. And an expired deadline means the
    dead-man has already won the race -- `confirm` re-reads the deadline
    under the lock precisely so that it loses it.

    Every refusal is required to name its own clause: on a host reachable
    only over Tailscale, "refused" without the reason leaves an operator
    with no next step, and the right next step differs per clause (re-run
    the observer for a stale challenge; never re-run it for evidence that
    recorded a failure).
    """
    assert _COMMIT_PATH.is_file()
    state = importlib.import_module(_STATE_MODULE)

    failing_evidence = tmp_path / "failing-evidence"
    _ready_to_confirm(root=failing_evidence, passed=False)
    _confirm_refuses(root=failing_evidence, clause="evidence")

    no_challenge = tmp_path / "no-challenge"
    _ready_to_confirm(root=no_challenge)
    importlib.import_module(_RECORDS_MODULE).challenge_path(
        paths=_paths(root=no_challenge)
    ).unlink()
    _confirm_refuses(root=no_challenge, clause="challenge")

    another_boot = tmp_path / "another-boot"
    _ready_to_confirm(root=another_boot, boot="boot-b")
    _confirm_refuses(root=another_boot, clause="challenge")

    wrong_nonce = tmp_path / "wrong-nonce"
    _ready_to_confirm(root=wrong_nonce, answer="the-nonce-of-some-earlier-window")
    _confirm_refuses(root=wrong_nonce, clause="nonce")

    out_of_time = tmp_path / "out-of-time"
    _ready_to_confirm(root=out_of_time, deadline=-1.0)
    assert _confirm_through_the_guard(root=out_of_time).verdict == "refuse"
    assert state.read_marker(paths=_paths(root=out_of_time), run="run-a") == "absent"

    committed = tmp_path / "committed"
    _ready_to_confirm(root=committed)
    assert _confirm_through_the_guard(root=committed).verdict != "refuse"
    assert state.read_marker(paths=_paths(root=committed), run="run-a") == "self"


def test_a_confirm_carrying_an_expired_or_already_spent_challenge_refuses(
    tmp_path: Path,
) -> None:
    """Specification "Commit": an expired or already-used challenge refuses.

    The two are different replays and both have to be closed. An
    EXPIRED challenge means the controller's probes ran more than 120
    seconds ago, so its answer vouches for a host as it was, not as it
    is -- and the window it watched is long over. An ALREADY-SPENT one
    means this exact answer has been presented before, so re-presenting
    it proves nothing a second time.

    The nonce is spent BEFORE the commit point, not after, and that
    order is what closes the spent case at all: a `confirm` that died
    between the two would otherwise leave an answer that still worked,
    and rider point 5 requires the challenge to be re-issued rather than
    reused.
    """
    records = importlib.import_module(_RECORDS_MODULE)

    expired = tmp_path / "expired"
    _ready_to_confirm(root=expired, issued=-200.0)
    _confirm_refuses(root=expired, clause="120 seconds")

    spent = tmp_path / "already-spent"
    _ready_to_confirm(root=spent)
    records.record_consumed_nonce(
        paths=_paths(root=spent), run="run-a", nonce="nonce-of-the-current-window"
    )
    _confirm_refuses(root=spent, clause="spent")

    committed = tmp_path / "committed"
    _ready_to_confirm(root=committed)
    assert _confirm_through_the_guard(root=committed).verdict != "refuse"
    assert records.consumed_nonces(paths=_paths(root=committed), run="run-a") == (
        "nonce-of-the-current-window",
    )


_OWNED_DAEMON_CONFIGURATION: dict[str, Any] = {
    "bip": "172.17.0.1/16",
    "cgroup-parent": "fabro-sandbox.slice",
    "ip-forward": True,
    "ip-forward-no-drop": True,
    "ip6tables": True,
    "iptables": True,
    "ipv6": False,
    "live-restore": False,
}


def test_the_commit_marker_carries_the_run_and_the_canonical_owned_keys_digest(
    tmp_path: Path,
) -> None:
    """Specification "Commit", and design F4: the digest is over PARSED keys.

    The marker is the only durable statement of what was committed, and
    it says two things: WHICH run committed, so a later dispatch can
    tell this host's commitment from another run's, and WHAT
    configuration it committed, so a later converge can tell a
    reconfiguration from a no-op.

    The digest covers the owned keys parsed and re-serialized rather
    than the file's bytes, and that is the half a byte digest would get
    wrong in the damaging direction: the slice role re-serializes
    `daemon.json` without changing an owned key, so a byte digest would
    report an identical configuration as a changed one on every later
    converge. The second half of this test writes exactly that -- the
    same owned keys reordered and re-indented, beside a CHANGED foreign
    key -- and requires the digest not to move.
    """
    records = importlib.import_module(_RECORDS_MODULE)
    root = tmp_path / "commit"
    _ready_to_confirm(root=root)
    paths = _paths(root=root)
    daemon_json = paths.inputs_dir(run="run-a") / "daemon.json"
    daemon_json.write_text(
        json.dumps({**_OWNED_DAEMON_CONFIGURATION, "log-driver": "json-file"}), encoding="utf-8"
    )

    assert _confirm_through_the_guard(root=root).verdict != "refuse"

    marker = json.loads(paths.marker.read_text(encoding="utf-8"))
    assert marker["run"] == "run-a"
    assert "digest" in marker
    assert marker["digest"] == records.owned_keys_digest(paths=paths, run="run-a")
    assert records.owned_daemon_keys(paths=paths, run="run-a") == _OWNED_DAEMON_CONFIGURATION

    reordered = dict(reversed(list(_OWNED_DAEMON_CONFIGURATION.items())))
    daemon_json.write_text(
        json.dumps({"log-driver": "syslog", **reordered}, indent=4), encoding="utf-8"
    )
    assert records.owned_keys_digest(paths=paths, run="run-a") == marker["digest"]
