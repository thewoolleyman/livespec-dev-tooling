"""Invalid identity, retained history and private filesystem journal boundaries."""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import _incident_recovery_journal_io as journal_io
from livespec_dev_tooling import incident_recovery_journal_service as service
from livespec_dev_tooling._incident_observer_store import repository_lock, save_record
from livespec_dev_tooling._incident_recovery_journal_identity import JournalCodec
from livespec_dev_tooling.incident_observer import reconcile_action_receipt
from livespec_dev_tooling.incident_recovery_journal import RecoveryJournal
from tests.livespec_dev_tooling.test_incident_recovery_journal import (
    _conflict,
    _context,
    _publish,
    _wire,
)
from tests.livespec_dev_tooling.test_incident_recovery_journal import (
    protected as protected_fixture,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac


@pytest.fixture
def protected(tmp_path):
    return protected_fixture.__wrapped__(tmp_path)


def _packet(operation, payload):
    body = _wire(payload)
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {"schema": 1, "operation": operation, "binding": {"request_sha256": digest}, **body}


def _call(journal, operation, payload):
    raw = json.dumps(_packet(operation, payload)).encode()
    if operation == "conflict":
        with repository_lock(
            directory=journal.installation.state,
            repository=journal.installation.repository,
            existing_only=True,
        ):
            return service.JournalService(journal=journal).execute(raw=raw)
    return service.JournalService(journal=journal).execute(raw=raw)


def _entry(installation, intent):
    return installation.state / "recovery-journal" / (intent.action_id + ".json")


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        (None, "action_id", "not-a-digest"),
        (None, "extra", True),
        ("registration", "generation", True),
        ("registration", "generation", 0),
        ("registration", "run_id", 0),
        ("registration", "head_sha", "bad-sha"),
        ("registration", "authority_receipt", 42),
        ("registration", "authority_receipt", "!!"),
        ("registration", "authority_receipt", "Zg==\n"),
        ("registration", "authority_receipt", ""),
        ("registration", "required_jobs", []),
        ("registration", "required_jobs", ["tests", "tests"]),
        ("registration", "required_jobs", [0]),
        ("registration", "branch", "candidate-branch"),
        ("registration", "owner", ""),
        ("registration", "owner", "x" * 65537),
        ("registration", "extra", True),
        ("completion", "job_id", True),
        ("completion", "run_id", 999),
        ("completion", "head_sha", "0" * 40),
        ("completion", "job_name", "unregistered-job"),
        ("completion", "conclusion", "success"),
        ("completion", "delivery_id", ""),
        ("completion", "extra", True),
        ("observer_arm", "pr_number", 0),
        ("observer_arm", "base_sha", "invalid"),
        ("observer_arm", "head_sha", "0" * 40),
        ("observer_arm", "owner", "another-owner"),
        ("observer_arm", "generation", True),
        ("observer_arm", "extra", True),
    ],
)
def test_untrusted_intent_fields_refuse_before_creating_journal(protected, section, field, value):
    journal, installation, intent, _ = protected
    raw = _wire(asdict(intent))
    (raw if section is None else raw[section])[field] = value
    assert _call(journal, "lookup", {"intent": raw})["status"] == "refused"
    assert list((installation.state / "recovery-journal").iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        "actions",
        "missing",
        "registration",
        "arm",
        "arm-id",
        "completion",
        "status",
        "pending-receipt",
        "completed-receipt",
        "identity",
    ],
)
def test_unverifiable_retained_action_never_becomes_absence(protected, change):
    journal, installation, intent, path = protected
    data = json.loads(path.read_text())
    action = data["actions"][intent.action_id]
    if change == "actions":
        data["actions"] = []
    elif change == "missing":
        data["actions"] = {}
    elif change == "registration":
        action.pop("registration")
    elif change == "arm":
        action["observer_arm"] = []
    elif change == "arm-id":
        action["observer_arm_id"] = "0" * 64
    elif change == "completion":
        action["completion"] = []
    elif change == "status":
        action["status"] = "invented"
    elif change == "pending-receipt":
        action["receipt"] = "unexpected-effect"
    elif change == "completed-receipt":
        action.update(status="completed", receipt=3)
    else:
        action["completion"]["delivery_id"] = "another-authenticated-delivery"
    save_record(path=path, record=data)
    assert journal.lookup(intent=intent).status in {"refused", "unavailable"}
    assert not _entry(installation, intent).exists()


def test_legacy_retained_registration_without_arm_still_has_exact_journal_identity(protected):
    _, installation, intent, path = protected
    intent = replace(intent, observer_arm=None)
    data = json.loads(path.read_text())
    data["actions"][intent.action_id].update(observer_arm=None, observer_arm_id=None)
    save_record(path=path, record=data)
    journal = RecoveryJournal(installation=installation)
    assert journal.reserve(request=_publish_without_arm(intent)).status == "reserved"
    assert journal.lookup(intent=intent).status == "reserved"


def _publish_without_arm(intent):
    # Original PR facts remain independently supplied by a future publisher;
    # the journal reservation does not authorize them or a forge operation.
    from tests.livespec_dev_tooling.test_incident_recovery_journal import _intent

    request = _publish(_intent())
    return replace(request, intent=intent)


@pytest.mark.parametrize("operation", ["reserve", "publish", "authorize", "landed", "head"])
def test_unsupported_rpc_leaves_no_journal_context_or_history_files(protected, operation):
    journal, installation, intent, path = protected
    before = path.read_bytes()
    result = _call(journal, operation, {"request": _wire(asdict(_publish(intent)))})
    assert result["status"] == "refused" and result["authorizes_current_effects"] is False
    assert list((installation.state / "recovery-journal").iterdir()) == []
    assert list((installation.state / "recovery-journal-contexts").iterdir()) == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", ["scope", "head", "owner", "receipt", "reason", "extra"])
def test_conflict_caller_cannot_replace_independently_authenticated_context(protected, change):
    journal, installation, intent, _ = protected
    request = _conflict(intent)
    _context(installation, request)
    raw = _wire(asdict(request))
    if change == "scope":
        raw["scope"]["original_base_sha"] = "0" * 40
    elif change == "head":
        raw["expected_head"] = "0" * 40
    elif change == "owner":
        raw["intent"]["registration"]["owner"] = "attacker"
    elif change == "receipt":
        raw["receipt"] = "caller-invented-terminal-result"
    elif change == "reason":
        raw["reason"] = "unverified allegation"
    else:
        raw["extra"] = True
    assert _call(journal, "conflict", {"request": raw})["status"] == "refused"
    assert not _entry(installation, intent).exists()


@pytest.mark.parametrize("change", ["schema", "extra", "request", "scope", "different"])
def test_invalid_protected_scope_context_refuses_terminal_receipt(protected, change):
    journal, installation, intent, _ = protected
    request = _conflict(intent)
    path = _context(installation, request)
    data = json.loads(path.read_text())
    if change == "schema":
        data["schema"] = True
    elif change == "extra":
        data["extra"] = True
    elif change == "request":
        data["request"] = []
    elif change == "scope":
        data["request"]["scope"]["authority_sha256"] = "0" * 64
    else:
        data["request"]["reason"] = "another independently provisioned context"
    path.write_text(json.dumps(data))
    assert journal.record_conflict(request=request).status in {"refused", "unavailable"}
    assert not _entry(installation, intent).exists()


@pytest.mark.parametrize(
    "change",
    [
        "object",
        "schema",
        "extra",
        "operation",
        "request",
        "result",
        "history",
        "context",
        "intent-digest",
    ],
)
def test_corrupt_reservation_history_is_unavailable_and_never_rewritten(protected, change):
    journal, installation, intent, _ = protected
    assert journal.reserve(request=_publish(intent)).status == "reserved"
    path = _entry(installation, intent)
    data = json.loads(path.read_text())
    if change == "object":
        data = []
    elif change == "schema":
        data["schema"] = True
    elif change == "extra":
        data["extra"] = True
    elif change == "operation":
        data["operation"] = "published"
    elif change == "request":
        data["request"]["message"] = False
    elif change == "result":
        data["result"]["authorizes_current_effects"] = 0
    elif change == "history":
        data["history"].append(data["history"][0])
    elif change == "context":
        data["context_sha256"] = "0" * 64
    else:
        data["intent_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    assert journal.lookup(intent=intent).status == "unavailable"
    assert journal.reserve(request=_publish(intent)).status == "unavailable"
    assert path.read_bytes() == before


def test_completed_exact_conflict_recovers_history_without_context_or_current_arm(protected):
    journal, installation, intent, path = protected
    request = _conflict(intent)
    context = _context(installation, request)
    result = journal.record_conflict(request=request)
    context.unlink()
    data = json.loads(path.read_text())
    data["actions"][intent.action_id].update(status="completed", receipt=result.receipt)
    data["registration"]["generation"] = 900
    save_record(path=path, record=data)
    assert journal.record_conflict(request=request) == result
    assert journal.lookup(intent=intent) == result
    data["actions"][intent.action_id]["receipt"] = "another-terminal-receipt"
    save_record(path=path, record=data)
    assert journal.lookup(intent=intent).status == "unavailable"


def test_unknown_reserved_effect_cannot_be_replaced_with_a_conflict(protected):
    journal, installation, intent, _ = protected
    assert journal.reserve(request=_publish(intent)).status == "reserved"
    path = _entry(installation, intent)
    before = path.read_bytes()
    request = _conflict(intent)
    _context(installation, request)
    assert journal.record_conflict(request=request).status == "refused"
    assert path.read_bytes() == before


def test_semantically_identical_rpc_envelopes_recover_one_exact_history(protected):
    journal, installation, intent, _ = protected
    request = _conflict(intent)
    _context(installation, request)
    packet = _packet("conflict", {"request": _wire(asdict(request))})
    endpoint = service.JournalService(journal=journal)
    with repository_lock(
        directory=installation.state, repository=installation.repository, existing_only=True
    ):
        first = endpoint.execute(raw=json.dumps(packet, sort_keys=True).encode())
        path = _entry(installation, intent)
        before = path.read_bytes()
        second = endpoint.execute(
            raw=json.dumps(dict(reversed(list(packet.items()))), indent=2).encode()
        )
        assert first == second and first["status"] == "recorded"
        assert path.read_bytes() == before


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"[]",
        b"{",
        b'{"schema":1,"schema":2}',
        b'{"schema":NaN}',
        b'{"schema":Infinity}',
        b'{"schema":-Infinity}',
        b'{"schema":1e999}',
        b'{"intent":{"x":1,"x":2}}',
        b" " * (2 * 1024 * 1024 + 1),
    ],
)
def test_malformed_or_oversized_packets_never_touch_journal(protected, raw):
    journal, installation, _, _ = protected
    assert service.JournalService(journal=journal).execute(raw=raw)["status"] == "refused"
    assert list((installation.state / "recovery-journal").iterdir()) == []


def _uninstrumented_env():
    """Child env without coverage startup hooks (subprocess_spawn_allowlist contract)."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE_", "COV_CORE_"))
    }


def test_cli_imports_without_site_packages_or_undeclared_runtime_dependencies():
    source = Path(service.__file__).resolve().parent.parent
    script = (
        "import sys; sys.path.insert(0, " + repr(str(source)) + "); "
        "from livespec_dev_tooling.incident_recovery_journal_service import JournalService; "
        "print(JournalService.__name__)"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script],
        capture_output=True,
        check=False,
        timeout=10,
        env=_uninstrumented_env(),
    )
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b"JournalService\n"


@pytest.mark.parametrize(
    "change", ["schema-bool", "schema-wrong", "operation", "binding", "extra", "missing"]
)
def test_packet_type_and_binding_must_be_exact(protected, change):
    journal, installation, intent, _ = protected
    packet = _packet("lookup", {"intent": _wire(asdict(intent))})
    if change == "schema-bool":
        packet["schema"] = True
    elif change == "schema-wrong":
        packet["schema"] = 2
    elif change == "operation":
        packet["operation"] = 3
    elif change == "binding":
        packet["binding"] = {"request_sha256": "0" * 64}
    elif change == "extra":
        packet = _packet("lookup", {"intent": _wire(asdict(intent)), "state": "/candidate"})
    else:
        packet = _packet("lookup", {})
    assert (
        service.JournalService(journal=journal).execute(raw=json.dumps(packet).encode())["status"]
        == "refused"
    )
    assert list((installation.state / "recovery-journal").iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        "state-mode",
        "journal-mode",
        "journal-file",
        "journal-escape",
        "action-escape",
        "lock-symlink",
        "context-escape",
    ],
)
def test_unsafe_protected_filesystem_never_yields_absence_or_a_result(protected, tmp_path, change):
    journal, installation, intent, action_path = protected
    directory = installation.state / "recovery-journal"
    escaped = tmp_path / "outside"
    escaped.mkdir(mode=0o700)
    if change == "state-mode":
        installation.state.chmod(0o755)
    elif change == "journal-mode":
        directory.chmod(0o755)
    elif change == "journal-file":
        directory.rmdir()
        directory.write_text("not a private directory")
    elif change == "journal-escape":
        directory.rmdir()
        directory.symlink_to(escaped, target_is_directory=True)
    elif change == "action-escape":
        target = escaped / "action.json"
        target.write_bytes(action_path.read_bytes())
        target.chmod(0o600)
        action_path.unlink()
        action_path.symlink_to(target)
    elif change == "lock-symlink":
        (directory / (intent.action_id + ".lock")).symlink_to(escaped / "new-lock")
    else:
        context = installation.state / "recovery-journal-contexts"
        context.rmdir()
        context.symlink_to(escaped, target_is_directory=True)
        assert journal.record_conflict(request=_conflict(intent)).status == "unavailable"
        return
    assert journal.lookup(intent=intent).status == "unavailable"


def test_write_failure_preserves_absence_and_releases_only_its_own_lock(protected, monkeypatch):
    journal, installation, intent, _ = protected
    with monkeypatch.context() as patch:

        def fail(**_kwargs):
            raise OSError("controlled unavailable effect store")

        patch.setattr(journal_io, "save_record", fail)
        assert journal.reserve(request=_publish(intent)).status == "unavailable"
    assert not _entry(installation, intent).exists()
    assert journal.reserve(request=_publish(intent)).status == "reserved"


def _observer_lock_blocked(path):
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+b") as probe:
        try:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        return False


def test_observer_lock_probe_has_unlocked_and_locked_controls(protected):
    _, installation, _, _ = protected
    path = installation.state / (
        hashlib.sha256(installation.repository.encode()).hexdigest() + ".lock"
    )
    assert not _observer_lock_blocked(path)
    with repository_lock(
        directory=installation.state, repository=installation.repository, existing_only=True
    ):
        assert _observer_lock_blocked(path)


def _reconcile_receipt(order, intent, action_id):
    assert action_id == intent.action_id
    order.append("observer-reconciled")
    return "independent-prior-effect"


def test_journal_persistence_serializes_with_real_observer_reconciliation(protected, monkeypatch):
    journal, installation, intent, _ = protected
    _context(installation, _conflict(intent))
    entered, release = Event(), Event()
    original = journal_io.save_record
    order, results = [], []

    def persist(*, path, record):
        entered.set()
        assert release.wait(3)
        original(path=path, record=record)
        order.append("journal-persisted")

    lock_path = installation.state / (
        hashlib.sha256(installation.repository.encode()).hexdigest() + ".lock"
    )
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(descriptor)
    monkeypatch.setattr(journal_io, "save_record", persist)
    writer = Thread(
        target=lambda: results.append(journal.record_conflict(request=_conflict(intent)))
    )
    reconciler = Thread(
        target=lambda: reconcile_action_receipt(
            directory=installation.state,
            repository=installation.repository,
            action_id=intent.action_id,
            read_exact_receipt=lambda action_id: _reconcile_receipt(order, intent, action_id),
            publish_receipt=lambda *_: False,
        )
    )
    writer.start()
    assert entered.wait(3)
    try:
        blocked = _observer_lock_blocked(lock_path)
        reconciler.start()
    finally:
        release.set()
        writer.join(3)
        reconciler.join(3)
    assert not writer.is_alive() and not reconciler.is_alive()
    assert blocked, "journal must retain the observer fence until its durable result exists"
    assert order == ["journal-persisted", "observer-reconciled"]
    assert results[0].status == "recorded"


def test_main_requires_isolated_protected_installation_before_packet_read(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(service.sys, "argv", ["journal", "--", "/fixed/controller.json"])
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=0))
    monkeypatch.setattr(service.sys, "stdout", output)
    assert service.main() == 2
    assert json.loads(output.getvalue())["status"] == "refused"


def test_main_uses_only_fixed_positional_config_and_existing_packet_protocol(
    protected, monkeypatch
):
    journal, installation, intent, _ = protected
    payload = _packet("lookup", {"intent": _wire(asdict(intent))})
    output = io.StringIO()

    def load(*, config):
        assert config == Path("/fixed/controller.json")
        return installation

    monkeypatch.setattr(service.ControllerInstallation, "load", load)
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(service.sys, "argv", ["journal", "--", "/fixed/controller.json"])
    monkeypatch.setattr(
        service.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))
    )
    monkeypatch.setattr(service.sys, "stdout", output)
    monkeypatch.setenv("GH_TOKEN", "candidate-token-is-never-read")
    monkeypatch.setenv("LIVESPEC_INCIDENT_STATE", "/candidate/chosen/state")
    assert service.main() == 0
    result = json.loads(output.getvalue())
    assert result["status"] == journal.lookup(intent=intent).status == "absent"
    assert result["binding"] == payload["binding"]
    assert result["authorizes_current_effects"] is False


@pytest.mark.parametrize("change", ["scope-shape", "head", "tree", "object", "plan-shape"])
def test_library_reservation_rejects_malformed_typed_inputs_without_storage(protected, change):
    journal, installation, intent, _ = protected
    request = _publish(intent)
    if change == "scope-shape":
        request = replace(
            request, plan=replace(request.plan, scope=replace(request.plan.scope, changed_paths=()))
        )
    elif change == "head":
        request = replace(request, plan=replace(request.plan, expected_head="invalid"))
    elif change == "tree":
        request = replace(request, plan=replace(request.plan, tree_sha="invalid"))
    elif change == "plan-shape":
        request = replace(request, plan=None)
    else:
        request = replace(request, message=object())
    assert journal.reserve(request=request).status == "refused"
    assert list((installation.state / "recovery-journal").iterdir()) == []


def test_noncanonical_base64_receipt_cannot_authenticate_an_action(protected):
    journal, installation, intent, _ = protected
    raw = _wire(asdict(intent))
    raw["registration"]["authority_receipt"] = "Zh=="
    assert _call(journal, "lookup", {"intent": raw})["status"] == "refused"
    assert list((installation.state / "recovery-journal").iterdir()) == []


def test_foreign_internally_consistent_repository_grant_is_refused(protected):
    journal, installation, intent, _ = protected
    registration = replace(intent.registration, repository="another/repo")
    identity = (
        f"{registration.repository}:{registration.operation_id}:{registration.generation}:recover"
    )
    foreign = replace(
        intent,
        registration=registration,
        completion=replace(intent.completion, repository=registration.repository),
        observer_arm=replace(intent.observer_arm, repository=registration.repository),
        action_id=hashlib.sha256(identity.encode()).hexdigest(),
    )
    assert journal.lookup(intent=foreign).status == "refused"
    assert list((installation.state / "recovery-journal").iterdir()) == []


def test_valid_but_different_retained_identity_in_history_is_unavailable(protected):
    journal, installation, intent, _ = protected
    assert journal.reserve(request=_publish(intent)).status == "reserved"
    path = _entry(installation, intent)
    data = json.loads(path.read_text())
    data["request"]["intent"]["completion"]["delivery_id"] = "other-delivery"
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    assert journal.lookup(intent=intent).status == "unavailable"
    assert path.read_bytes() == before


def test_invalid_conflict_context_digest_in_history_remains_unavailable(protected):
    journal, installation, intent, _ = protected
    request = _conflict(intent)
    _context(installation, request)
    assert journal.record_conflict(request=request).status == "recorded"
    path = _entry(installation, intent)
    data = json.loads(path.read_text())
    data["context_sha256"] = "not-a-digest"
    path.write_text(json.dumps(data))
    assert journal.lookup(intent=intent).status == "unavailable"


def test_foreign_owned_ancestor_is_unavailable_even_with_private_mode(protected, monkeypatch):
    journal, installation, intent, _ = protected
    original = Path.lstat

    def lstat(path):
        value = original(path)
        if path == installation.state:
            fields = list(value)
            fields[4] = max(os.geteuid() + 1, 1)
            return os.stat_result(fields)
        return value

    monkeypatch.setattr(Path, "lstat", lstat)
    assert installation.state.parent.lstat() == original(installation.state.parent)
    assert journal.lookup(intent=intent).status == "unavailable"


def test_symlink_cycle_in_protected_action_is_an_unavailable_observation(protected):
    journal, installation, intent, path = protected
    path.unlink()
    path.symlink_to(path.name)
    assert journal.lookup(intent=intent).status == "unavailable"
    assert list((installation.state / "recovery-journal").iterdir()) == []


def test_lost_atomic_action_snapshot_before_journal_access_refuses(protected, monkeypatch):
    journal, installation, intent, path = protected
    original = JournalCodec.retained
    observed = []

    def retained(*, record, intent):
        result = original(record=record, intent=intent)
        observed.append(result)
        if len(observed) == 1:
            # Controlled protected-store fault between atomic observations,
            # not a cooperative lifecycle writer bypassing its fence.
            save_record(path=path, record={"actions": {}})
        return result

    monkeypatch.setattr(JournalCodec, "retained", retained)
    assert journal.lookup(intent=intent).status == "refused"
    assert not _entry(installation, intent).exists()


@pytest.mark.parametrize(("operation", "effect_request"), [("publish", None), ("reserve", None)])
def test_internal_store_operation_boundary_has_zero_effects(protected, operation, effect_request):
    _, installation, intent, _ = protected
    result = journal_io.JournalStore(installation=installation).perform(
        operation=operation, intent=intent, request=effect_request
    )
    assert result.status == "refused"
    assert list((installation.state / "recovery-journal").iterdir()) == []


def _main_reply(monkeypatch, installation, packet):
    output = io.StringIO()

    def load(*, config):
        assert config == Path("/fixed/controller.json")
        return installation

    monkeypatch.setattr(service.ControllerInstallation, "load", load)
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(service.sys, "argv", ["journal", "--", "/fixed/controller.json"])
    monkeypatch.setattr(
        service.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(packet).encode()))
    )
    monkeypatch.setattr(service.sys, "stdout", output)
    assert service.main() == 0
    return json.loads(output.getvalue())


@pytest.mark.parametrize("marker", ["+3", "003", "2", "-1", "not-a-descriptor", "999999"])
def test_cli_rejects_noncanonical_or_invalid_inherited_fence(protected, monkeypatch, marker):
    _, installation, intent, _ = protected
    monkeypatch.setenv(service.REPOSITORY_FENCE_FD_ENV, marker)
    result = _main_reply(
        monkeypatch, installation, _packet("lookup", {"intent": _wire(asdict(intent))})
    )
    assert result["status"] == "refused"
    assert list((installation.state / "recovery-journal").iterdir()) == []


def test_cli_borrows_valid_existing_descriptor_without_unlocking_parent(protected, monkeypatch):
    _, installation, intent, _ = protected
    with repository_lock(
        directory=installation.state, repository=installation.repository, existing_only=True
    ) as observer_path:
        fence = service.current_repository_fence(
            repository=installation.repository, directory=installation.state
        )
        assert fence is not None
        monkeypatch.setenv(service.REPOSITORY_FENCE_FD_ENV, str(fence.descriptor))
        reply = _main_reply(
            monkeypatch, installation, _packet("lookup", {"intent": _wire(asdict(intent))})
        )
        assert reply["status"] == "absent"
        assert _observer_lock_blocked(observer_path.with_suffix(".lock"))


def test_inprocess_conflict_rpc_without_held_fence_refuses_before_storage(protected):
    journal, installation, intent, _ = protected
    request = _conflict(intent)
    _context(installation, request)
    packet = _packet("conflict", {"request": _wire(asdict(request))})
    result = service.JournalService(journal=journal).execute(raw=json.dumps(packet).encode())
    assert result["status"] == "refused"
    assert list((installation.state / "recovery-journal").iterdir()) == []
