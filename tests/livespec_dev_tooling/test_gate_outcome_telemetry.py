"""One outcome event per delegated gate run — its vocabulary, identity and fail-soft delivery.

Nothing here reaches a cluster, a mirror, a host or a receiver. The gate client's
only door to the world is its `GateCommandRunner` seam, so a canned runner is the
whole cluster; the receiver is a recording stand-in for `urllib.request.urlopen`,
so no span leaves this process and no socket is opened.

THE TWO FAULTS THIS SUITE KEEPS APART are the ones a delegated gate exists to
distinguish: a RED TREE, which is the pushing repository's own problem, and a run
that reached NO VERDICT, which is the delegation's. They want opposite responses,
and until this event existed the difference lived only in one push's own log —
so a broken delegation read, to anyone not reading that log, as a failing
repository.

WHY THE MODULE UNDER TEST IS IMPORTED FROM INSIDE EACH TEST BODY rather than at
the top: the Red leg of this change has the test and no module at all, and a
top-level import would make that Red a COLLECTION error, which proves only
unimportability. `_telemetry` asserts the module's file exists first, so the Red
fails on a genuine assertion about the behaviour being absent.
"""

from __future__ import annotations

import importlib
import json
import urllib.error
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from returns.result import Success

from livespec_dev_tooling.gate_remote_delegate import run_delegated_gate
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_verdict import (
    GATE_FAILED,
    GATE_NO_VERDICT,
    GATE_PASSED,
    GateVerdict,
)

__all__: list[str] = []

# Every heading this file covers is a `scenarios.md` acceptance scenario, and
# `heading_coverage` resolves a mapped node id outside the `scenario_tiers`
# prefixes only when the test carries a static `integration` marker. The marker
# is a TIER LABEL, never a filter: no recipe passes `-m`.
pytestmark = pytest.mark.integration

_MODULE = "livespec_dev_tooling.gate_outcome_telemetry"
_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "gate_outcome_telemetry.py"
)


def _telemetry() -> ModuleType:
    """Import the emitter, having first asserted the file it lives in exists.

    The assertion is the point: it is reached from a test BODY, so a tree that
    does not carry the emitter yet fails on a genuine assertion rather than
    erroring during collection.
    """
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


# ---------------------------------------------------------------------------
# The canned cluster — one delegated run's every command, answered from script
# ---------------------------------------------------------------------------

_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RENDERER = Path("/opt/gates/render-gate-job.sh")
_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n"
# The name the API SERVER assigns. Neither this suite nor the client predicts it:
# the manifest asks for a `generateName`, which is what lets one tree be gated
# twice — and is why the name can only be carried OUT of an adjudicated run.
_JOB = "gate-widget-7f2qd"
_CREATED = json.dumps({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB}})
_ORIGIN_URL = "git@github.com:acme/widget.git"
_REPOSITORY = "widget"
_JOB_ADMITTING = json.dumps({"status": {}})
_JOB_COMPLETE = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})
_JOB_FAILED = json.dumps({"status": {"conditions": [{"type": "Failed", "status": "True"}]}})

# `--git-common-dir` is matched BEFORE `rev-parse`, because the clone-identity
# read is itself a `rev-parse` and the tree read must not answer for it.
_STEP_MARKERS: tuple[tuple[str, str], ...] = (
    ("--git-common-dir", "read-common-dir"),
    ("rev-parse", "read-tree"),
    ("get-url", "read-origin"),
    ("create", "submit-job"),
    ("get", "get-job"),
)


def _kind_of(*, argv: list[str]) -> str:
    """Name the step one argv belongs to, for the canned answers below."""
    if argv[0] == str(_RENDERER):
        return "render"
    for marker, kind in _STEP_MARKERS:
        if marker in argv:
            return kind
    return "other"


class _CannedCluster:
    """Every command one delegated run issues, answered without a cluster.

    `terminal` is the Job condition the poll reports, so one gate is green and
    another red without either reaching an API server. `refuse` names the steps
    that answer non-zero, which is how a run is driven to no verdict at all —
    and WHICH step is refused decides what the run ever determined: a refused
    `submit-job` means no Job was created, so no Job name exists to report.

    The polls are answered in SEQUENCE — not admitted yet, then terminal —
    rather than from one canned payload, so a run has to WAIT at least once
    before it sees a verdict. That is the realistic shape, since no gate is
    terminal on its first poll, and it is the only way the sleeper seam is
    reached at all.
    """

    def __init__(self, *, terminal: str = _JOB_COMPLETE, refuse: tuple[str, ...] = ()) -> None:
        self._refuse = refuse
        self._terminal = terminal
        self._polls = 0
        self._answers = {
            "read-tree": f"{_TREE}\n",
            "read-origin": f"{_ORIGIN_URL}\n",
            "read-common-dir": ".git\n",
            "render": _MANIFEST,
            "submit-job": _CREATED,
            "other": "",
        }

    def _poll(self) -> str:
        """Not admitted yet, then whichever terminal condition this gate reaches."""
        self._polls += 1
        return _JOB_ADMITTING if self._polls == 1 else self._terminal

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (cwd, stdin, stream)
        kind = _kind_of(argv=argv)
        if kind in self._refuse:
            return Success(GateCommandResult(returncode=1, stdout="", stderr=f"{kind} refused"))
        stdout = self._poll() if kind == "get-job" else self._answers[kind]
        return Success(GateCommandResult(returncode=0, stdout=stdout, stderr=""))


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned — the run's only source of time."""
    _ = seconds


def _recorded_events() -> tuple[list[dict[str, Any]], Callable[..., None]]:
    """An emitter that records what it was asked to send, and sends nothing."""
    events: list[dict[str, Any]] = []

    def _emit(
        *, outcome: str, repository: str | None, tree_hash: str | None, job_name: str | None
    ) -> None:
        events.append(
            {
                "outcome": outcome,
                "repository": repository,
                "tree_hash": tree_hash,
                "job_name": job_name,
            }
        )

    return events, _emit


def _attributes_of(*, payload: dict[str, Any]) -> dict[str, str]:
    """Flatten one span's OTLP attribute list into the mapping a reader sees."""
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 1
    return {
        attribute["key"]: next(iter(attribute["value"].values()))
        for attribute in spans[0]["attributes"]
    }


def _recording_receiver(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Accept every span into a list, so delivery succeeds and nothing is sent."""
    accepted: list[dict[str, Any]] = []

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            _ = args

        def read(self) -> bytes:
            return b""

    def _urlopen(request: Any, timeout: float) -> _Response:
        _ = timeout
        accepted.append(
            {
                "url": request.full_url,
                "method": request.method,
                "headers": dict(request.headers),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    return accepted


def _refusing_receiver(monkeypatch: pytest.MonkeyPatch) -> None:
    """A receiver that refuses the connection, the way an absent one does."""

    def _urlopen(request: Any, timeout: float) -> object:
        _ = (request, timeout)
        raise urllib.error.URLError("receiver refused the connection")

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)


# ---------------------------------------------------------------------------
# The event itself — one span, the outcome vocabulary, and the run's identity
# ---------------------------------------------------------------------------


def test_each_gate_outcome_is_one_span_carrying_the_runs_gate_identity() -> None:
    """The three outcomes a delegated gate can have, each as exactly one span.

    The vocabulary is the whole point of the event: `failed-tree` and
    `no-verdict` are the two faults a reader could not tell apart before, and
    they are DIFFERENT WORDS here rather than one `failed` with a detail string,
    because an alert can filter on an attribute and cannot read prose.
    """
    telemetry = _telemetry()

    for outcome in (
        telemetry.GATE_OUTCOME_PASSED,
        telemetry.GATE_OUTCOME_FAILED_TREE,
        telemetry.GATE_OUTCOME_NO_VERDICT,
    ):
        payload = telemetry.build_span_payload(
            outcome=outcome, repository=_REPOSITORY, tree_hash=_TREE, job_name=_JOB
        )

        assert _attributes_of(payload=payload) == {
            "livespec.gate.outcome": outcome,
            "livespec.gate.repository": _REPOSITORY,
            "livespec.gate.tree_hash": _TREE,
            "livespec.gate.job_name": _JOB,
        }


def test_each_gate_outcome_vocabulary_word_is_the_one_the_contract_names() -> None:
    """`passed`, `failed-tree`, `no-verdict` — spelled, not merely distinct."""
    telemetry = _telemetry()

    assert (
        telemetry.GATE_OUTCOME_PASSED,
        telemetry.GATE_OUTCOME_FAILED_TREE,
        telemetry.GATE_OUTCOME_NO_VERDICT,
    ) == ("passed", "failed-tree", "no-verdict")


def test_a_value_the_run_never_determined_is_absent_rather_than_guessed() -> None:
    """An attribute it could invent is one an alert would read as fact.

    A run that stopped before the API server assigned a Job name HAS no Job
    name, and an empty string or a placeholder would be indistinguishable, to
    the reader of a trigger, from a real one.
    """
    telemetry = _telemetry()

    payload = telemetry.build_span_payload(
        outcome=telemetry.GATE_OUTCOME_NO_VERDICT,
        repository=None,
        tree_hash=None,
        job_name=None,
    )

    assert _attributes_of(payload=payload) == {
        "livespec.gate.outcome": telemetry.GATE_OUTCOME_NO_VERDICT
    }


def test_a_delivered_event_is_one_otlp_trace_request_to_the_receiver(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wire shape, asserted where a receiver would see it."""
    telemetry = _telemetry()
    accepted = _recording_receiver(monkeypatch)

    telemetry.post_span(endpoint="http://recv:4319", payload={"resourceSpans": []})

    assert len(accepted) == 1
    assert accepted[0]["url"] == "http://recv:4319/v1/traces"
    assert accepted[0]["method"] == "POST"
    assert accepted[0]["headers"]["Content-type"] == "application/json"
    assert accepted[0]["payload"] == {"resourceSpans": []}


def test_a_trailing_slash_on_the_endpoint_does_not_double_the_traces_path(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured endpoint is operator input, so its spelling is tolerated."""
    telemetry = _telemetry()
    accepted = _recording_receiver(monkeypatch)

    telemetry.post_span(endpoint="http://recv:4319/", payload={"resourceSpans": []})

    assert accepted[0]["url"] == "http://recv:4319/v1/traces"


def test_a_receiver_that_refuses_the_event_is_not_an_error(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The emitter is an observer of a decided gate; it raises nothing, ever."""
    telemetry = _telemetry()
    _refusing_receiver(monkeypatch)

    assert telemetry.post_span(endpoint="http://recv:4319", payload={"resourceSpans": []}) is None


def test_the_receiver_is_the_configured_endpoint_or_the_hosts_loopback_collector(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One knob, and a default that is the fleet's host-side convention.

    `127.0.0.1:4319` is the loopback OTLP receiver the host otel-collector
    serves — the same one `ci-runner-heartbeat.sh` and `ci-cache-gauges.sh`
    default to — so a delegating host needs no configuration to be observed.
    """
    telemetry = _telemetry()
    accepted = _recording_receiver(monkeypatch)

    monkeypatch.delenv(telemetry.ENDPOINT_ENV, raising=False)
    telemetry.emit_gate_outcome(
        outcome=telemetry.GATE_OUTCOME_PASSED,
        repository=_REPOSITORY,
        tree_hash=_TREE,
        job_name=_JOB,
    )
    monkeypatch.setenv(telemetry.ENDPOINT_ENV, "http://configured:4319")
    telemetry.emit_gate_outcome(
        outcome=telemetry.GATE_OUTCOME_PASSED,
        repository=_REPOSITORY,
        tree_hash=_TREE,
        job_name=_JOB,
    )

    assert telemetry.DEFAULT_ENDPOINT == "http://127.0.0.1:4319"
    assert [event["url"] for event in accepted] == [
        f"{telemetry.DEFAULT_ENDPOINT}/v1/traces",
        "http://configured:4319/v1/traces",
    ]


# ---------------------------------------------------------------------------
# The run — every delegated gate run emits exactly one event, whatever it decided
# ---------------------------------------------------------------------------


def test_a_delegated_gate_run_that_reaches_no_verdict_emits_a_no_verdict_event(
    *, tmp_path: Path
) -> None:
    """Scenario: a delegated gate run that reaches no verdict emits its outcome.

    The API server that cannot be reached is expressed as a refused submit, so
    the run is refused having created NOTHING on the cluster. It still emits:
    one event, the word `no-verdict`, and the identity it DID determine — the
    repository it was gating and the tree it was gating. The Job's name is
    absent because the run never obtained one, which is the contract's
    never-guessed rule rather than a gap in the event.
    """
    telemetry = _telemetry()
    events, emit = _recorded_events()
    repo_root = tmp_path / _REPOSITORY
    repo_root.mkdir()

    verdict = run_delegated_gate(
        repo_root=repo_root,
        renderer=_RENDERER,
        runner=_CannedCluster(refuse=("submit-job",)),
        sleeper=_no_sleep,
        emit=emit,
    )

    assert verdict.state == GATE_NO_VERDICT
    assert verdict.refuses_push is True
    assert events == [
        {
            "outcome": telemetry.GATE_OUTCOME_NO_VERDICT,
            "repository": _REPOSITORY,
            "tree_hash": _TREE,
            "job_name": None,
        }
    ]


def test_a_run_that_submitted_no_gate_at_all_still_emits_exactly_one_event(
    *, tmp_path: Path
) -> None:
    """A run that stopped before assembly is still a run, so it still reports.

    This is the path that used to be silent: nothing was submitted, so nothing
    could be red, and the whole fault is invisible to anyone not reading the
    push's own log. The event carries only the outcome, because the assembly's
    failure track reports the step that could not be completed and not the
    identity it had read on the way there — and the contract requires a value
    the emitter was not given to be ABSENT rather than guessed.
    """
    telemetry = _telemetry()
    events, emit = _recorded_events()

    verdict = run_delegated_gate(
        repo_root=tmp_path,
        renderer=_RENDERER,
        runner=_CannedCluster(refuse=("render",)),
        sleeper=_no_sleep,
        emit=emit,
    )

    assert verdict.state == GATE_NO_VERDICT
    assert events == [
        {
            "outcome": telemetry.GATE_OUTCOME_NO_VERDICT,
            "repository": None,
            "tree_hash": None,
            "job_name": None,
        }
    ]


def test_a_green_gate_emits_passed_and_a_red_tree_emits_failed_tree(*, tmp_path: Path) -> None:
    """The two verdicts an adjudicated run can reach, as the two words.

    Both carry the Job's name, which only an adjudicated run has: it is the name
    the API server assigned, read back off the submit and carried out through
    the verdict. That is what makes the event actionable — a reader can go and
    look at the Job this outcome is about.
    """
    telemetry = _telemetry()
    repo_root = tmp_path / _REPOSITORY
    repo_root.mkdir()
    reached: list[tuple[str, dict[str, Any]]] = []

    for terminal, state in ((_JOB_COMPLETE, GATE_PASSED), (_JOB_FAILED, GATE_FAILED)):
        events, emit = _recorded_events()
        verdict = run_delegated_gate(
            repo_root=repo_root,
            renderer=_RENDERER,
            runner=_CannedCluster(terminal=terminal),
            sleeper=_no_sleep,
            emit=emit,
        )
        assert verdict.state == state
        assert len(events) == 1
        reached.append((verdict.state, events[0]))

    assert [event for _, event in reached] == [
        {
            "outcome": telemetry.GATE_OUTCOME_PASSED,
            "repository": _REPOSITORY,
            "tree_hash": _TREE,
            "job_name": _JOB,
        },
        {
            "outcome": telemetry.GATE_OUTCOME_FAILED_TREE,
            "repository": _REPOSITORY,
            "tree_hash": _TREE,
            "job_name": _JOB,
        },
    ]


def test_a_delegated_gate_verdict_is_unchanged_when_its_event_cannot_be_delivered(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: a delegated gate verdict is unchanged when its event cannot be delivered.

    The same green gate is run twice against the same canned cluster, through
    the REAL emitter both times — once with a receiver that accepts the span and
    once with one that refuses the connection. The verdict and the status it
    produces are compared to each other rather than to a constant, which is the
    claim the scenario makes: a telemetry outage moves neither.
    """
    repo_root = tmp_path / _REPOSITORY
    repo_root.mkdir()

    def _gated() -> GateVerdict:
        return run_delegated_gate(
            repo_root=repo_root,
            renderer=_RENDERER,
            runner=_CannedCluster(),
            sleeper=_no_sleep,
        )

    accepted = _recording_receiver(monkeypatch)
    delivered = _gated()
    assert len(accepted) == 1

    _refusing_receiver(monkeypatch)
    undelivered = _gated()

    assert delivered == undelivered
    assert undelivered.state == GATE_PASSED
    assert undelivered.refuses_push is False
