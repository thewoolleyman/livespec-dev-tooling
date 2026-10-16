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
import os
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


_GUARDED_UNITS_RUNNING = {
    "containerd.service": "active",
    "docker.service": "active",
    "docker.socket": "active",
}
_GUARDED_UNITS_ENABLED = {
    "containerd.service": "enabled",
    "docker.service": "enabled",
    "docker.socket": "enabled",
}


def _host_after_the_commit(*, root: Path) -> Any:
    """A `FakeHost` whose three guarded units are enabled and running.

    `confirm` validates exactly that once its post-commit steps are
    done, so every case that gets past the commit point needs it. A
    committed host whose units are NOT up is the state that validation
    exists to catch, and it is driven on its own below rather than
    arrived at by accident here.
    """
    fake = _fake(root=root)
    fake.clock = 1.0
    fake.unit_states = dict(_GUARDED_UNITS_RUNNING)
    fake.unit_file_states = dict(_GUARDED_UNITS_ENABLED)
    return fake


def _confirm_through_the_guard(*, root: Path) -> Any:
    """Run a `confirm` through the lock and the dispatch table, as the role does.

    The deadline clause lives in the table rather than in the handler, so
    a case that exercises it has to come through the whole guard rather
    than straight to `confirm`.
    """
    guard = importlib.import_module(_GUARD_MODULE)
    return guard.run_operation(
        operation="confirm",
        run="run-a",
        env=_env(root=root, host=_host_after_the_commit(root=root)),
    )


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


def _fsync_failing_for(*, target: Path) -> Any:
    """An `os.fsync` that fails for exactly `target`, resolved through /proc/self/fd.

    Scoped to ONE path rather than to a file type, because a single
    `confirm` fsyncs several files and more than one directory, and a
    blanket failure would stop the first of them rather than the one
    under test.
    """
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        """Fail for the one path under test; pass every other fsync through."""
        if Path(f"/proc/self/fd/{fd}").readlink() == target:
            raise OSError(5, "simulated fsync failure")
        real_fsync(fd)

    return fsync


def test_a_failed_directory_fsync_after_the_rename_leaves_the_run_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Specification "Commit", and design F4: a visible marker is never rolled back.

    The run is committed the moment the rename returns, so a directory
    fsync that fails AFTER it has not failed to commit -- it has failed
    to make the commitment survive a power loss. Treating it as a failed
    commit would roll back a host whose marker is already visible, and
    the guarded units' start condition already reads that marker. So the
    failure is recorded as a durability warning, where an operator can
    find it, and the run stands.

    The complement is the half that keeps the rule from becoming a
    blanket "any fsync failure is fine": a failure BEFORE the rename
    leaves no marker, and that run is NOT committed. `confirm` tells the
    two apart by reading the marker back rather than by trusting what
    the write reported.
    """
    records = importlib.import_module(_RECORDS_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    ordinary = tmp_path / "ordinary"
    _ready_to_confirm(root=ordinary)

    assert records.publish_marker(paths=_paths(root=ordinary), run="run-a", digest="a-digest") == ""

    after = tmp_path / "after-the-rename"
    _ready_to_confirm(root=after)
    paths = _paths(root=after)
    monkeypatch.setattr(os, "fsync", _fsync_failing_for(target=paths.state_root))
    outcome = _confirm_through_the_guard(root=after)
    monkeypatch.undo()

    assert outcome.verdict != "refuse"
    assert state.read_marker(paths=paths, run="run-a") == "self"
    warning = records.durability_warning_path(paths=paths, run="run-a")
    assert "durability" in warning.read_text(encoding="utf-8")
    assert warning.read_text(encoding="utf-8") in outcome.reason

    before = tmp_path / "before-the-rename"
    _ready_to_confirm(root=before)
    uncommitted = _paths(root=before)
    monkeypatch.setattr(
        os, "fsync", _fsync_failing_for(target=uncommitted.marker.with_suffix(".tmp"))
    )
    refused = _confirm_through_the_guard(root=before)
    monkeypatch.undo()

    assert refused.verdict == "refuse"
    assert state.read_marker(paths=uncommitted, run="run-a") == "absent"
    assert state.read_phase(paths=uncommitted, run="run-a") == "observed"


def test_a_confirm_on_a_run_the_marker_names_repeats_the_post_commit_steps(
    tmp_path: Path,
) -> None:
    """Specification "Commit": the post-commit steps repeat, with no challenge.

    This is the state a crash between the commit rename and the phase
    update leaves, and the state a reboot after a failed directory
    fsync leaves. The marker names the run, so the run IS committed
    whatever its phase reads, and every step after the commit point is
    idempotent -- which is what lets the repeat be a plain re-run rather
    than a recovery protocol of its own.

    The challenge is deliberately removed first. A committed run has
    nothing left to prove, and /run is tmpfs, so after the reboot this
    case models there IS no challenge to answer: a repeat that still
    demanded one could never finish a committed host.

    Rider point 9: the repeat STARTS the units, not merely enables
    them. An enabled-but-stopped Docker on a committed host is a host
    whose engine comes back only at the next boot.
    """
    records = importlib.import_module(_RECORDS_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    root = tmp_path / "finish"
    _ready_to_confirm(root=root)
    paths = _paths(root=root)
    records.publish_marker(
        paths=paths, run="run-a", digest=records.owned_keys_digest(paths=paths, run="run-a")
    )
    records.challenge_path(paths=paths).unlink()
    _record_phase(root=root, run="run-a", phase="committed")
    fake = _host_after_the_commit(root=root)

    outcome = importlib.import_module(_GUARD_MODULE).run_operation(
        operation="confirm", run="run-a", env=_env(root=root, host=fake)
    )

    assert outcome.verdict != "refuse"
    assert state.read_phase(paths=paths, run="run-a") == "confirmed"
    assert fake.calls_named(name="revoke_start_permission") != ()
    assert fake.calls_named(name="enable_units")[0].detail == model.GUARDED_UNITS
    started = [call.detail[0] for call in fake.calls_named(name="start_unit")]
    assert started == list(model.GUARDED_UNITS)
    stopped = [call.detail[0] for call in fake.calls_named(name="stop_unit")]
    assert stopped == ["docker-engine-deadman-run-a.timer"]


def _confirm_on_a_committed_host(*, root: Path, host: Any) -> Any:
    """Run a `confirm` whose run the marker already names, against `host`."""
    guard = importlib.import_module(_GUARD_MODULE)
    return guard.run_operation(operation="confirm", run="run-a", env=_env(root=root, host=host))


def test_after_the_post_commit_steps_confirm_validates_the_committed_installation(
    tmp_path: Path,
) -> None:
    """Specification "Commit", the validation sentence.

    The post-commit steps are issued, not observed. Enabling and
    starting a unit says what was asked for; it does not say the engine
    came up, and on a committed host nothing is watching any more -- the
    dead-man has been stopped, by design, because a committed run must
    never be rolled back. So the validation is the only thing left that
    can notice a committed host whose engine is not actually running.

    It REPORTS rather than acts, and that is the point worth asserting:
    a validation that rolled back what it found would undo a commitment
    the guarded units' start condition already honours. The run stays
    committed and stays `confirmed`; only the exit code and the reason
    tell the operator what to repair.
    """
    records = importlib.import_module(_RECORDS_MODULE)
    state = importlib.import_module(_STATE_MODULE)

    down = tmp_path / "engine-not-running"
    _ready_to_confirm(root=down)
    host = _host_after_the_commit(root=down)
    host.unit_states = {**_GUARDED_UNITS_RUNNING, "docker.service": "failed"}
    outcome = _confirm_on_a_committed_host(root=down, host=host)

    assert outcome.verdict == "refuse"
    assert "docker.service" in outcome.reason
    assert state.read_marker(paths=_paths(root=down), run="run-a") == "self"
    assert state.read_phase(paths=_paths(root=down), run="run-a") == "confirmed"

    not_enabled = tmp_path / "engine-not-enabled"
    _ready_to_confirm(root=not_enabled)
    host = _host_after_the_commit(root=not_enabled)
    host.unit_file_states = {**_GUARDED_UNITS_ENABLED, "docker.socket": "disabled"}
    assert "docker.socket" in _confirm_on_a_committed_host(root=not_enabled, host=host).reason

    drifted = tmp_path / "keys-drifted"
    _ready_to_confirm(root=drifted)
    records.publish_marker(
        paths=_paths(root=drifted), run="run-a", digest="the-digest-of-another-configuration"
    )
    _record_phase(root=drifted, run="run-a", phase="committed")
    outcome = _confirm_on_a_committed_host(root=drifted, host=_host_after_the_commit(root=drifted))

    assert outcome.verdict == "refuse"
    assert "digest" in outcome.reason
    assert state.read_phase(paths=_paths(root=drifted), run="run-a") == "confirmed"


_POSTCONDITIONS_HOLDING = {
    "each FORWARD policy as snapshotted": True,
    "each watched sysctl as snapshotted": True,
    "no Docker rule": True,
    "no docker0": True,
    "no socket, process, queued job or pending start": True,
    "no start permission": True,
}


def _commit_entry(*, name: str) -> Any:
    """The commit module, asserted to carry the entry `name`.

    Asserted at the top of each test rather than once, so a Red fails on
    the entry it is driving instead of on whichever test happened to run
    first.
    """
    commit = importlib.import_module(_COMMIT_MODULE)
    assert name in commit.__all__
    return commit


def _verify_run(*, root: Path, postconditions: dict[str, bool]) -> Any:
    """Run `verify` through the whole guard with `postconditions` injected."""
    guard = importlib.import_module(_GUARD_MODULE)
    fake = _fake(root=root)
    fake.postconditions = postconditions
    return guard.run_operation(operation="verify", run="run-a", env=_env(root=root, host=fake))


def test_verify_rereads_the_postconditions_and_promotes_only_a_wholly_clean_host(
    tmp_path: Path,
) -> None:
    """Specification "After the commit", the `verify` sentence.

    `verify` is how a `rollback-partial` run ever ends. The reservation
    stays with that run until it does, so nothing else can reserve the
    host -- which is the correct state while Docker's footprint may
    still be on it, and the reason the promotion is the single most
    consequential write in this file: it is what lets a LATER run start.

    So it is made only when EVERY postcondition holds, re-read now
    rather than taken from what the rollback recorded. A partial
    recovery that read as complete would admit a fresh install onto a
    host still carrying a `docker0`, a Docker rule, or a daemon.

    An empty set refuses rather than promoting. A read that came back
    with nothing is not evidence that every postcondition holds; it is
    evidence that the read did not happen.
    """
    state = importlib.import_module(_STATE_MODULE)
    _commit_entry(name="verify")

    failing = tmp_path / "still-failing"
    _record_phase(root=failing, run="run-a", phase="rollback-partial")
    outcome = _verify_run(
        root=failing, postconditions={**_POSTCONDITIONS_HOLDING, "no docker0": False}
    )
    assert outcome.verdict == "refuse"
    assert "no docker0" in outcome.reason
    assert state.read_phase(paths=_paths(root=failing), run="run-a") == "rollback-partial"

    unread = tmp_path / "read-back-empty"
    _record_phase(root=unread, run="run-a", phase="rollback-partial")
    assert _verify_run(root=unread, postconditions={}).verdict == "refuse"
    assert state.read_phase(paths=_paths(root=unread), run="run-a") == "rollback-partial"

    repaired = tmp_path / "repaired"
    _record_phase(root=repaired, run="run-a", phase="rollback-partial")
    outcome = _verify_run(root=repaired, postconditions=dict(_POSTCONDITIONS_HOLDING))
    assert outcome.verdict == "proceed"
    assert state.read_phase(paths=_paths(root=repaired), run="run-a") == "rolled-back"

    finished = tmp_path / "already-rolled-back"
    _record_phase(root=finished, run="run-a", phase="rolled-back")
    assert _verify_run(root=finished, postconditions=dict(_POSTCONDITIONS_HOLDING)).verdict == (
        "proceed"
    )
    assert state.read_phase(paths=_paths(root=finished), run="run-a") == "rolled-back"


def test_verify_reads_the_postconditions_against_the_runs_own_snapshot(tmp_path: Path) -> None:
    """The comparison is against THIS run's snapshot, not the host's current state.

    The snapshot `publish` took before the first package step is what
    "as snapshotted" means for the FORWARD policies and the sysctls, so
    a `verify` reading any other baseline would compare Docker's own
    footprint against itself and find it clean.
    """
    guard = importlib.import_module(_GUARD_MODULE)
    _commit_entry(name="verify")
    _record_phase(root=tmp_path, run="run-a", phase="rolled-back")
    fake = _fake(root=tmp_path)
    fake.postconditions = dict(_POSTCONDITIONS_HOLDING)

    guard.run_operation(operation="verify", run="run-a", env=_env(root=tmp_path, host=fake))

    assert fake.calls_named(name="read_postconditions")[0].detail == (
        str(_paths(root=tmp_path).snapshot_dir(run="run-a")),
    )


def _reconfigure_run(*, root: Path, host: Any) -> Any:
    """Run `reconfigure` through the whole guard, as a post-commit converge does."""
    guard = importlib.import_module(_GUARD_MODULE)
    return guard.run_operation(operation="reconfigure", run="run-a", env=_env(root=root, host=host))


def test_reconfigure_writes_the_owned_keys_only_for_the_run_the_marker_names(
    tmp_path: Path,
) -> None:
    """Specification "After the commit", and design H3: the one post-commit change.

    After a confirmation the guarded transition is closed -- `reserve`
    refuses while the marker exists -- so `reconfigure` is the only way
    a later converge changes anything, and it is deliberately the
    smallest possible way: write the owned keys, record a pending
    DRAINED restart, and stop. It grants no permission, arms no
    dead-man, and does not rewrite the marker, which is why the marker's
    bytes are asserted unchanged: rewriting it would re-open the one
    question the marker exists to have already answered.

    The restart is DEFERRED rather than issued, exactly as the slice
    role defers one. Restarting Docker here would kill the sandbox
    containers running under it, on a host whose whole purpose is to run
    them.

    The two refusals are the table's, and both matter: a marker naming
    ANOTHER run means this host's commitment is not this run's, and no
    marker at all means the host never committed, so there is no
    post-commit path to take.
    """
    records = importlib.import_module(_RECORDS_MODULE)
    _commit_entry(name="reconfigure")
    confirmed = tmp_path / "confirmed"
    _record_phase(root=confirmed, run="run-a", phase="confirmed")
    paths = _paths(root=confirmed)
    paths.inputs_dir(run="run-a").mkdir(parents=True, exist_ok=True)
    (paths.inputs_dir(run="run-a") / "daemon.json").write_text(
        json.dumps({**_OWNED_DAEMON_CONFIGURATION, "log-driver": "json-file"}), encoding="utf-8"
    )
    records.publish_marker(paths=paths, run="run-a", digest="the-digest-committed-earlier")
    marker_before = paths.marker.read_text(encoding="utf-8")
    host = _fake(root=confirmed)

    outcome = _reconfigure_run(root=confirmed, host=host)

    assert outcome.verdict == "proceed"
    assert host.daemon_keys == _OWNED_DAEMON_CONFIGURATION
    assert host.calls_named(name="record_pending_drained_restart")[0].detail == ("docker.service",)
    assert paths.marker.read_text(encoding="utf-8") == marker_before
    assert host.calls_named(name="grant_start_permission") == ()

    foreign = tmp_path / "another-runs-marker"
    _record_phase(root=foreign, run="run-a", phase="confirmed")
    records.publish_marker(paths=_paths(root=foreign), run="run-other", digest="d")
    other_host = _fake(root=foreign)
    assert _reconfigure_run(root=foreign, host=other_host).verdict == "refuse"
    assert other_host.calls_named(name="write_daemon_keys") == ()

    uncommitted = tmp_path / "never-committed"
    _record_phase(root=uncommitted, run="run-a", phase="confirmed")
    bare_host = _fake(root=uncommitted)
    assert _reconfigure_run(root=uncommitted, host=bare_host).verdict == "refuse"
    assert bare_host.calls_named(name="write_daemon_keys") == ()
