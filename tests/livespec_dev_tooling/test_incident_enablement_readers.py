"""The enablement readers at the hook, CI and controller vantages, and the armed fence.

Spec v205, `## Expedited incident execution`: every vantage reads the enablement record
once an incident flag selects a mode in an ordinary invocation; a trusted normal origin
and an invocation with both flags absent never read it. While disarmed a vantage records
its reading in the artefact it already produces and refuses nothing. While armed it
refuses expedited repair on every reading but `enabled`, and an emergency revert on every
such reading except `unavailable`, with a named refusal naming the repository, the
installation and the reading. A vantage that cannot reach its installation reads
`unavailable` with no arming state and refuses nothing.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from livespec_dev_tooling import (
    incident_ci_entry,
    incident_ci_process,
    incident_hook_entry,
    incident_observer_control,
    incident_observer_query,
)
from livespec_dev_tooling._incident_enablement_fence import controller_fence, installation_reader
from livespec_dev_tooling._incident_enablement_reading import (
    EnablementReading,
    answer_reading,
    fence_refusal,
)
from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_ci_authority import CiAuthorityBoundary
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiTarget
from livespec_dev_tooling.incident_enablement import IdentitySource, ObserverEnablement
from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    Invocation,
    OperationIdentity,
    resolve_execution_context,
)
from livespec_dev_tooling.incident_hook_process import canonical, resolve_current_reading
from livespec_dev_tooling.incident_observer_admission import arm_before_merge
from livespec_dev_tooling.incident_observer_control import ObserverControl
from livespec_dev_tooling.incident_observer_query import ObserverQuery

SERVED = "thewoolleyman/livespec-dev-tooling"
IDENTITY = "a" * 64
OTHER = "b" * 64
NOT_ENABLED = "incident mode is not enabled for owner/repo at installation"


def packet() -> dict[str, Any]:
    arm = {
        "repository": "owner/repo",
        "incident_item_id": "incident-1",
        "attempt_id": "attempt-1",
        "operation_id": "repair-1",
        "generation": 1,
        "owner": "operator:alice",
        "phase": "repair",
        "pr_number": 7,
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "required_jobs": ["check-lint"],
        "controller_release": "v1.0.0",
        "controller_revision": "c" * 40,
        "authority_receipt": b"actual-controlled-receipt".hex(),
    }
    arm_id = hashlib.sha256(json.dumps(arm, sort_keys=True).encode()).hexdigest()
    return {"schema": 1, "arm": arm, "observer_arm_id": arm_id}


def query() -> dict[str, Any]:
    return {
        "repository": "owner/repo",
        "item": "incident",
        "attempt": "attempt",
        "phase": "repair",
        "operation": "operation",
        "generation": 1,
        "owner": "operator",
    }


def reading() -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "repository": "owner/repo",
        "item_id": "incident",
        "attempt_id": "attempt",
        "phase": "repair",
        "operation_id": "operation",
        "generation": 1,
        "owner": "operator",
        "base": "a" * 40,
        "head": "b" * 40,
        "landed_commits": [],
    }
    return {
        "attempt": attempt,
        "is_current": True,
        "committed_token_id": "closed",
        "current_token_id": "open",
    }


def _true(*_args: object, **_kwargs: object) -> bool:
    return True


def _none(*_args: object, **_kwargs: object) -> None:
    return None


def _answer(*, status: str, armed: bool, repository: str = SERVED) -> dict[str, Any]:
    return {
        "schema": 1,
        "status": status,
        "query": {"repository": repository},
        "confirmed_manifest_sha256": IDENTITY,
        "armed": armed,
    }


def _reading(*, value: str, armed: bool | None) -> EnablementReading:
    return EnablementReading(reading=value, armed=armed, installation="127.0.0.1:8765")


# --- the fence decision -------------------------------------------------------------------


@pytest.mark.parametrize("value", ["enabled", "absent", "stale", "revoked", "unavailable"])
def test_a_disarmed_or_unknown_arming_state_refuses_nothing(value: str) -> None:
    for armed in (False, None):
        reading_ = _reading(value=value, armed=armed)
        assert fence_refusal(reading=reading_, repository=SERVED, revert=False) is None
        assert fence_refusal(reading=reading_, repository=SERVED, revert=True) is None


@pytest.mark.parametrize("value", ["absent", "stale", "revoked", "unavailable", "no-installation"])
def test_armed_repair_is_refused_on_every_reading_but_enabled_naming_all_three(
    value: str,
) -> None:
    refusal = fence_refusal(
        reading=_reading(value=value, armed=True), repository=SERVED, revert=False
    )
    assert refusal == (
        f"incident mode is not enabled for {SERVED} at installation 127.0.0.1:8765: {value}"
    )
    assert (
        fence_refusal(
            reading=_reading(value="enabled", armed=True), repository=SERVED, revert=False
        )
        is None
    )


def test_armed_revert_is_refused_on_every_not_enabled_reading_except_unavailable() -> None:
    refused = [
        value
        for value in ("enabled", "absent", "stale", "revoked", "unavailable")
        if fence_refusal(reading=_reading(value=value, armed=True), repository=SERVED, revert=True)
    ]
    assert refused == ["absent", "stale", "revoked"]


def test_an_answer_is_read_exactly_and_anything_else_is_unavailable_with_no_arming_state() -> None:
    enabled = answer_reading(
        answer=_answer(status="enabled", armed=True), installation="i", repository=SERVED
    )
    assert enabled == EnablementReading(
        reading="enabled", armed=True, installation="i", detail=f"confirmed {IDENTITY}"
    )
    for malformed in (
        None,
        {"status": "refused", "reason": "an enablement operation for another repository"},
        _answer(status="enabled", armed=True, repository="example/other"),
        _answer(status="no-installation", armed=True),
        {**_answer(status="enabled", armed=True), "armed": "yes"},
    ):
        parsed = answer_reading(answer=malformed, installation="i", repository=SERVED)
        assert (parsed.reading, parsed.armed) == ("unavailable", None)
    assert answer_reading(answer=None, installation="i", repository=SERVED).detail == (
        "the query answer is malformed"
    )


# --- the dev-host hook reader -------------------------------------------------------------


class Post:
    """A fake query route recording each request it answers."""

    def __init__(self, *, answer: dict[str, Any] | None = None, error: bool = False) -> None:
        self.answer = answer
        self.error = error
        self.requests: list[tuple[str, bytes, dict[str, Any]]] = []

    def __call__(self, *, url: str, secret: bytes, body: bytes) -> tuple[int, dict[str, Any]]:
        self.requests.append((url, secret, json.loads(body)))
        if self.error:
            raise OSError("connection refused")
        return 202, self.answer or {}


def test_the_hook_asks_the_serving_installation_with_the_query_credential_and_compares_core() -> (
    None
):
    post = Post(answer=_answer(status="enabled", armed=True))
    environ = {"LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "query-secret"}
    same = installation_reader(environ=environ, post=post, own_identity=lambda: IDENTITY)
    assert same(repository=SERVED).reading == "enabled"
    assert post.requests == [
        ("http://127.0.0.1:8765/enablement/read", b"query-secret", {"repository": SERVED})
    ]
    moved = installation_reader(environ=environ, post=post, own_identity=lambda: OTHER)
    stale = moved(repository=SERVED)
    assert (stale.reading, stale.armed) == ("stale", True)
    assert stale.detail == f"controller confirmed {IDENTITY}; own read of core: {OTHER}"
    failed = installation_reader(environ=environ, post=post, own_identity=lambda: None)
    assert failed(repository=SERVED).reading == "unavailable"
    absent = installation_reader(
        environ=environ,
        post=Post(answer=_answer(status="absent", armed=False)),
        own_identity=lambda: OTHER,
    )
    assert absent(repository=SERVED).reading == "absent"


def test_the_hook_reads_no_installation_and_unavailable_without_an_answer() -> None:
    post = Post(error=True)
    unserved = installation_reader(environ={}, post=post, own_identity=lambda: IDENTITY)
    assert unserved(repository="example/unserved") == EnablementReading(
        reading="no-installation",
        armed=None,
        installation="none",
        detail="no controller installation serves it",
    )
    unprojected = unserved(repository=SERVED)
    assert (unprojected.reading, unprojected.armed) == ("unavailable", None)
    assert "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN is not projected" in unprojected.detail
    unreachable = installation_reader(
        environ={"LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "q"},
        post=post,
        own_identity=lambda: IDENTITY,
    )(repository=SERVED)
    assert (unreachable.reading, unreachable.armed) == ("unavailable", None)
    assert unreachable.detail == "/enablement/read query failed: connection refused"
    assert post.requests == [
        ("http://127.0.0.1:8765/enablement/read", b"q", {"repository": SERVED})
    ]


# --- the execution resolver ---------------------------------------------------------------


def _identity(*, phase: str = "repair") -> OperationIdentity:
    return OperationIdentity(
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        phase=phase,
        repository=SERVED,
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="operation-1",
        recorded_incident_merge_sha="c" * 40 if phase == "reverting" else None,
    )


class Reader:
    """A fake vantage reader that answers one fixed reading and counts its reads."""

    def __init__(self, *, value: str, armed: bool | None) -> None:
        self.reading = _reading(value=value, armed=armed)
        self.reads: list[str] = []

    def __call__(self, *, repository: str) -> EnablementReading:
        self.reads.append(repository)
        return self.reading


def test_normal_origins_and_absent_flags_never_read_the_record() -> None:
    reader = Reader(value="absent", armed=True)
    for invocation in (Invocation.NORMAL_MASTER, Invocation.NORMAL_FACTORY_FOLLOW_UP):
        resolved = resolve_execution_context(
            environ={EXPEDITED_INCIDENT_RESPONSE: "1"},
            invocation=invocation,
            identity=None,
            read_enablement=reader,
        )
        assert resolved.is_successful and resolved.enablement is None
    absent = resolve_execution_context(
        environ={}, invocation=Invocation.ORDINARY, identity=_identity(), read_enablement=reader
    )
    assert absent.is_successful and absent.unwrap().mode == "normal"
    assert reader.reads == []


def test_a_disarmed_reading_is_recorded_and_refuses_nothing() -> None:
    reader = Reader(value="absent", armed=False)
    resolved = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE: "1"},
        invocation=Invocation.ORDINARY,
        identity=_identity(),
        read_enablement=reader,
    )
    assert resolved.is_successful and resolved.unwrap().mode == "expedited-repair"
    assert resolved.enablement == {
        "reading": "absent",
        "armed": False,
        "installation": "127.0.0.1:8765",
        "detail": "",
    }
    assert reader.reads == [SERVED]


def test_an_armed_not_enabled_reading_refuses_repair_and_lets_a_revert_through_unavailable() -> (
    None
):
    repair = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE: "1"},
        invocation=Invocation.ORDINARY,
        identity=_identity(),
        read_enablement=Reader(value="unavailable", armed=True),
    )
    assert not repair.is_successful
    assert repair.failure().code == "incident-not-enabled"
    assert repair.failure().detail == (
        f"incident mode is not enabled for {SERVED} at installation 127.0.0.1:8765: unavailable"
    )
    revert = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE_REVERT: "1"},
        invocation=Invocation.ORDINARY,
        identity=_identity(phase="reverting"),
        read_enablement=Reader(value="unavailable", armed=True),
    )
    assert revert.is_successful and revert.enablement is not None
    revoked = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE_REVERT: "1"},
        invocation=Invocation.ORDINARY,
        identity=_identity(phase="reverting"),
        read_enablement=Reader(value="revoked", armed=True),
    )
    assert not revoked.is_successful and revoked.failure().code == "incident-not-enabled"


def test_the_hook_resolves_its_current_context_with_its_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(EXPEDITED_INCIDENT_RESPONSE, "1")
    monkeypatch.delenv(EXPEDITED_INCIDENT_RESPONSE_REVERT, raising=False)
    monkeypatch.delenv("LIVESPEC_INCIDENT_CONTEXT", raising=False)
    reader = Reader(value="absent", armed=False)
    context, enablement = resolve_current_reading(
        reading=reading(), query=query(), read_enablement=reader
    )
    assert context.mode == "expedited-repair"
    assert enablement is not None and enablement["reading"] == "absent"
    assert reader.reads == ["owner/repo"]


# --- the incident CI entrance -------------------------------------------------------------


def _event() -> CiEvent:
    return CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=("expedited-incident-response",),
    )


def _ci(*, tmp_path: Path, reader: Reader) -> incident_ci_entry.CiEntry:
    return incident_ci_entry.CiEntry(
        repo=tmp_path,
        targets=(CiTarget(name="check-fast", classification="fast"),),
        current=_true,
        observer=_true,
        enablement=reader,
    )


def test_the_ci_plan_records_its_reading_outside_the_identity_it_rechecks(tmp_path: Path) -> None:
    reader = Reader(value="absent", armed=False)
    entry = _ci(tmp_path=tmp_path, reader=reader)
    plan = entry.plan(event=_event(), payload=json.dumps(packet()), environ=dict(os.environ))
    assert plan is not None and plan.enablement is not None
    assert plan.enablement["reading"] == "absent"
    assert replace(plan, enablement={"reading": "unavailable"}) == plan
    assert reader.reads == ["owner/repo"]


def test_an_armed_not_enabled_ci_reading_refuses_the_plan_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = _ci(tmp_path=tmp_path, reader=Reader(value="stale", armed=True))
    assert entry.plan(event=_event(), payload=json.dumps(packet()), environ={}) is None
    assert capsys.readouterr().err == (
        f"incident-ci-refused: incident-not-enabled: {NOT_ENABLED} 127.0.0.1:8765: stale\n"
    )


def test_a_normal_ci_event_never_reads_the_record(tmp_path: Path) -> None:
    reader = Reader(value="absent", armed=True)
    normal = replace(_event(), labels=())
    plan = _ci(tmp_path=tmp_path, reader=reader).plan(
        event=normal, payload="", environ=dict(os.environ)
    )
    assert plan is not None and plan.enablement is None
    assert reader.reads == []


def test_the_ci_reader_asks_the_query_route_and_an_unreachable_one_reads_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unconfigured = CiAuthorityBoundary(observer_url="", observer_token="").enablement(
        repository="owner/repo"
    )
    assert (unconfigured.reading, unconfigured.armed) == ("unavailable", None)
    assert unconfigured.installation == "unconfigured"
    asked: list[tuple[str, dict[str, Any]]] = []

    def exchange(
        _self: CiAuthorityBoundary, *, route: str, query: dict[str, Any], **_: Any
    ) -> tuple[int, bytes]:
        asked.append((route, query))
        if query["repository"] == "owner/unreachable":
            raise OSError("timed out")
        return 202, json.dumps(
            _answer(status="revoked", armed=True, repository="owner/repo")
        ).encode()

    monkeypatch.setattr(CiAuthorityBoundary, "_exchange", exchange)
    boundary = CiAuthorityBoundary(observer_url="https://observer.example/", observer_token="t")  # noqa: S106 - a test token
    revoked = boundary.enablement(repository="owner/repo")
    assert (revoked.reading, revoked.armed, revoked.installation) == (
        "revoked",
        True,
        "observer.example",
    )
    unreachable = boundary.enablement(repository="owner/unreachable")
    assert (unreachable.reading, unreachable.armed) == ("unavailable", None)
    assert unreachable.detail == "enablement/read failed: OSError"
    assert asked[0] == ("enablement/read", {"repository": "owner/repo"})


# --- the controller's own entrances -------------------------------------------------------


class Core:
    def __init__(self) -> None:
        self.reads = 0

    def source(self) -> IdentitySource:
        def read_identity() -> str | None:
            self.reads += 1
            return IDENTITY

        return IdentitySource(read_head=lambda: "1" * 40, read_identity=read_identity)


def _controller_settings(*, tmp_path: Path) -> tuple[Any, ObserverArm]:
    state = tmp_path / "protected"
    state.mkdir(mode=0o700)
    attempt = {"repository": "owner/repo", "phase": "repair"}
    arm = ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="operation-1",
        generation=1,
        owner="owner",
        phase="repair",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("coverage",),
        controller_release="v1.0.0",
        controller_revision="b" * 40,
        authority_receipt=json.dumps(attempt, sort_keys=True).encode(),
    )
    settings = SimpleNamespace(
        repository="owner/repo",
        repo=tmp_path,
        state=state,
        release="v1.0.0",
        revision="b" * 40,
        reader=("/installed/reader",),
        reader_release="v0.282.0",
        jobs=("coverage",),
    )
    return settings, arm


def _pre_armed(*, settings: Any, arm: ObserverArm) -> dict[str, Any]:
    receipt = arm_before_merge(
        directory=settings.state,
        arm=arm,
        expected_arm_id=None,
        authorize_current=_true,
        released_controller=_true,
    )
    exact = {
        "repository": arm.repository,
        "arm_id": receipt.receipt,
        "pr_number": arm.pr_number,
        "base_sha": arm.base_sha,
        "head_sha": arm.head_sha,
        "receipt_digest": hashlib.sha256(arm.authority_receipt).hexdigest(),
    }
    return exact


def _enabled_and_armed(*, settings: Any, core: Core, revoke: bool) -> None:
    enablement = ObserverEnablement(installation=settings, source=core.source())
    payload = {"repository": "owner/repo", "manifest_sha256": IDENTITY, "operation_id": "e"}
    assert enablement.execute(path="/enablement", payload=payload)["status"] == "enabled"
    arm = {"repository": "owner/repo", "operation_id": "arm"}
    assert enablement.execute(path="/fence/arm", payload=arm)["status"] == "armed"
    if revoke:
        revoked = {"repository": "owner/repo", "operation_id": "revoke"}
        assert enablement.execute(path="/enablement/revoke", payload=revoked)["status"] == "revoked"


def test_the_controller_reads_nothing_for_its_answers_while_disarmed_and_absent_for_its_arm(
    tmp_path: Path,
) -> None:
    settings, _ = _controller_settings(tmp_path=tmp_path)
    core = Core()
    assert controller_fence(
        installation=settings, source=core.source(), phase="repair", shadow=False
    ) == (None, None)
    reading_, refusal = controller_fence(
        installation=settings, source=core.source(), phase="repair", shadow=True
    )
    assert reading_ == EnablementReading(
        reading="absent",
        armed=False,
        installation="controller:owner/repo",
        detail="no record retained",
    )
    assert refusal is None and core.reads == 0


def test_an_armed_controller_refuses_its_admitted_answer_unless_the_record_is_enabled(
    tmp_path: Path,
) -> None:
    settings, arm = _controller_settings(tmp_path=tmp_path)
    exact = _pre_armed(settings=settings, arm=arm)
    core = Core()
    _enabled_and_armed(settings=settings, core=core, revoke=False)
    query_ = ObserverQuery(installation=settings, source=core.source())
    assert query_.execute(path="/admitted", payload=exact)["status"] == "admitted"
    revoked = {"repository": "owner/repo", "operation_id": "revoke"}
    enablement = ObserverEnablement(installation=settings, source=core.source())
    _ = enablement.execute(path="/enablement/revoke", payload=revoked)
    assert query_.execute(path="/admitted", payload=exact) == {
        "schema": 1,
        "status": "refused",
        "reason": f"{NOT_ENABLED} controller:owner/repo: revoked (confirmed {IDENTITY})",
    }


def test_the_arm_receipt_records_the_reading_and_an_armed_fence_refuses_a_revoked_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, arm = _controller_settings(tmp_path=tmp_path)
    core = Core()
    payload = _arm_payload(arm=arm)
    control = ObserverControl(installation=settings, source=core.source())
    _enabled_and_armed(settings=settings, core=core, revoke=True)
    refused = control.execute(path="/arm", payload=payload)
    assert refused["status"] == "refused"
    assert refused["enablement"]["reading"] == "revoked"
    assert refused["reason"].startswith("incident mode is not enabled for owner/repo")
    evidence_reads: list[object] = []
    monkeypatch.setattr(
        incident_observer_control.FocusedEvidenceGate, "__call__", evidence_reads.append
    )
    assert control.execute(path="/arm", payload=payload)["status"] == "refused"
    assert evidence_reads == [], "an armed fence refuses before any evidence is read"


def test_a_disarmed_arm_receipt_records_the_absent_reading_and_arms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, arm = _controller_settings(tmp_path=tmp_path)
    monkeypatch.setattr(incident_observer_control.FocusedEvidenceGate, "__call__", _none)
    monkeypatch.setattr(incident_observer_control.CurrentAuthorityReader, "__call__", _true)
    receipt = ObserverControl(installation=settings, source=Core().source()).execute(
        path="/arm", payload=_arm_payload(arm=arm)
    )
    assert receipt["status"] == "armed"
    assert receipt["enablement"] == {
        "reading": "absent",
        "armed": False,
        "installation": "controller:owner/repo",
        "detail": "no record retained",
    }


def _arm_payload(*, arm: ObserverArm) -> dict[str, Any]:
    return {
        "repository": arm.repository,
        "incident_item_id": arm.incident_item_id,
        "attempt_id": arm.attempt_id,
        "operation_id": arm.operation_id,
        "generation": arm.generation,
        "owner": arm.owner,
        "phase": arm.phase,
        "pr_number": arm.pr_number,
        "base_sha": arm.base_sha,
        "head_sha": arm.head_sha,
        "authority_receipt": arm.authority_receipt.hex(),
    }


# --- each vantage's artefact carries its reading ------------------------------------------


def _hook_wired(*, monkeypatch: pytest.MonkeyPatch, reader: Reader, revert: bool = False) -> None:
    current = reading()
    query_ = query()
    if revert:
        current["attempt"].update(phase="reverting", landed_commits=["c" * 40])
        query_["phase"] = "reverting"
    monkeypatch.delenv("LIVESPEC_INCIDENT_CONTEXT", raising=False)
    monkeypatch.setenv(
        EXPEDITED_INCIDENT_RESPONSE_REVERT if revert else EXPEDITED_INCIDENT_RESPONSE, "1"
    )
    monkeypatch.delenv(
        EXPEDITED_INCIDENT_RESPONSE if revert else EXPEDITED_INCIDENT_RESPONSE_REVERT,
        raising=False,
    )
    monkeypatch.setenv(incident_hook_entry.QUERY_ENV, canonical(value=query_))
    monkeypatch.setenv(incident_hook_entry.LOCAL_OPERATION_ENV, "local-operation-1")
    monkeypatch.setattr(incident_hook_entry, "trusted_invocation", _ordinary)
    monkeypatch.setattr(incident_hook_entry, "invoke_authority", _answering(value=current))
    monkeypatch.setattr(incident_hook_entry, "installation_reader", _returning(value=reader))


def _ordinary(*_args: object, **_kwargs: object) -> str:
    return Invocation.ORDINARY


def _answering(*, value: dict[str, Any]) -> Any:
    def invoke(**_kwargs: object) -> dict[str, Any]:
        return value

    return invoke


def _returning(*, value: object) -> Any:
    def produce(*_args: object, **_kwargs: object) -> object:
        return value

    return produce


def test_the_hooks_printed_receipt_records_its_enablement_reading(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reader = Reader(value="absent", armed=False)
    _hook_wired(monkeypatch=monkeypatch, reader=reader)
    tree = "f" * 40
    prior = {"receipt_id": "r", "hook": "pre-commit", "tree": tree, "exit_status": 0}
    monkeypatch.setattr(incident_hook_entry, "exact_tree", _returning(value=tree))
    monkeypatch.setattr(incident_hook_entry, "validate_scope", _returning(value={}))
    monkeypatch.setattr(incident_hook_entry, "recover_receipt", _returning(value=prior))
    assert incident_hook_entry.main(argv=["pre-commit"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["receipt"] == prior
    assert printed["enablement"] == reader.reading.record()
    assert reader.reads == ["owner/repo"]


def test_the_hooks_revert_hand_off_records_its_enablement_reading(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reader = Reader(value="unavailable", armed=True)
    _hook_wired(monkeypatch=monkeypatch, reader=reader, revert=True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert incident_hook_entry.main(argv=["pre-push"]) == 79
    handoff = json.loads(capsys.readouterr().out)
    assert handoff["handoff"] == "trusted-recovery-boundary"
    assert handoff["enablement"] == reader.reading.record()


def test_an_armed_hook_refuses_repair_by_name_before_any_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _hook_wired(monkeypatch=monkeypatch, reader=Reader(value="absent", armed=True))
    gate_reads: list[object] = []
    monkeypatch.setattr(incident_hook_entry, "exact_tree", gate_reads.append)
    assert incident_hook_entry.main(argv=["pre-commit"]) == 78
    assert "incident-not-enabled: " + NOT_ENABLED in capsys.readouterr().err
    assert gate_reads == [], "an armed refusal comes before any gate selection"


def test_the_ci_plan_output_carries_the_plan_time_reading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reader = Reader(value="absent", armed=False)

    def entry(**kwargs: Any) -> incident_ci_entry.CiEntry:
        return incident_ci_entry.CiEntry(**kwargs, current=_true, observer=_true, enablement=reader)

    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.chdir(tmp_path)
    targets = (CiTarget(name="check-fast", classification="fast"),)
    # EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3hilpy
    monkeypatch.setattr(incident_ci_process, "load_repository_inventory", _returning(value=targets))
    observed = (_event(), json.dumps(packet()))
    monkeypatch.setattr(incident_ci_process, "observe_event", _returning(value=observed))
    monkeypatch.setattr(incident_ci_process, "CiEntry", entry)
    assert incident_ci_process.main(argv=["plan"]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["status"] == "planned"
    assert planned["enablement"] == reader.reading.record()


def test_an_armed_controller_refuses_its_current_answer_unless_the_record_is_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, arm = _controller_settings(tmp_path=tmp_path)
    exact = _pre_armed(settings=settings, arm=arm)
    core = Core()
    _enabled_and_armed(settings=settings, core=core, revoke=False)
    monkeypatch.setattr(incident_observer_query.CurrentAuthorityReader, "__call__", _true)
    query_ = ObserverQuery(installation=settings, source=core.source())
    assert query_.execute(path="/current", payload=exact)["status"] == "current"
    revoked = {"repository": "owner/repo", "operation_id": "revoke"}
    enablement = ObserverEnablement(installation=settings, source=core.source())
    _ = enablement.execute(path="/enablement/revoke", payload=revoked)
    assert query_.execute(path="/current", payload=exact) == {
        "schema": 1,
        "status": "refused",
        "reason": f"{NOT_ENABLED} controller:owner/repo: revoked (confirmed {IDENTITY})",
    }
