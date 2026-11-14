"""An expedited pull-request CI run is recorded on its incident work item.

Spec: livespec-dev-tooling SPECIFICATION/contracts.md `## Expedited incident execution`,
the expedited pull-request run records (livespec-dev-tooling-bqnzcm.4). A run of the
incident CI job on a pull-request head the controller has armed gets an unpublished
record carrying its key, the job's conclusion and any refusal code, retained from the
signed job callback and written onto the incident item by the sweep, once. A run on a
head the controller has not armed gets no record, and neither does a run on a branch
ci.yml runs on `push` (`master`, `incident-scratch/**`). While the installation has no
CI identity policy the record carries the refusal `identity-not-provisioned`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_observer_service as service
from livespec_dev_tooling import incident_pr_run_records as runs
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import LeafCompletion
from livespec_dev_tooling._incident_pr_run_store import (
    add_record,
    mark_written,
    pending_records,
    record_digest,
    run_tree,
)
from livespec_dev_tooling.incident_observer_events import completion_run_attempt
from livespec_dev_tooling.incident_repository_fence import RepositoryFenceBusyError
from tests.livespec_dev_tooling.test_incident_observer_target_branch import _World

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4

_HEAD = "c" * 40


@pytest.fixture
def world(tmp_path, monkeypatch):
    armed = _World(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert armed.post(path="/arm", payload=armed.arm)[1]["status"] == "armed"
    return armed


_PR_BRANCH = "incident/incident-1-attempt-1"


def _pr_leaf(
    world, *, head=_HEAD, name="incident-ci", attempt=2, delivery="pr-1", branch=_PR_BRANCH
):
    job = {
        "id": 77,
        "run_id": 4001,
        "head_sha": head,
        "head_branch": branch,
        "name": name,
        "status": "completed",
        "conclusion": "success",
    }
    if attempt is not None:
        job["run_attempt"] = attempt
    event = {"action": "completed", "repository": {"full_name": "owner/repo"}, "workflow_job": job}
    body = json.dumps(event).encode()
    signature = hmac.new(world.installation.webhook_secret, body, hashlib.sha256).hexdigest()
    return world.post(
        path="/callback",
        payload=event,
        HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
        HTTP_X_GITHUB_EVENT="workflow_job",
        HTTP_X_GITHUB_DELIVERY=delivery,
    )


def _record(world):
    with repository_lock(
        directory=world.installation.state, repository=world.installation.repository
    ) as path:
        return load_record(path=path)


class _Ledger:
    """The incident item's comment stream, as `bd` answers it."""

    def __init__(self):
        self.calls, self.comments = [], []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[:2] == ["comments", "add"]:
            self.comments.append({"text": args[3]})
            return ""
        return json.dumps(self.comments)


def _sweep(world, ledger):
    return runs.write_pending(
        state=world.installation.state, repository=world.installation.repository, ledger=ledger
    )


def test_an_armed_heads_incident_ci_run_is_recorded_once_on_its_incident_item(world):
    status, result = _pr_leaf(world)
    assert (status, result["status"], result["pr_run"]) == ("202 Accepted", "ignored", "retained")
    ledger = _Ledger()
    written = _sweep(world, ledger)
    assert len(written) == 1 and len(ledger.comments) == 1
    text = ledger.comments[0]["text"]
    assert text.startswith(runs.PR_RUN_MARKER + "\n")
    body = json.loads(text.removeprefix(runs.PR_RUN_MARKER + "\n"))
    assert body == {
        "kind": "unpublished",
        "repository": "owner/repo",
        "incident_item_id": "incident-1",
        "attempt_id": "repair-1",
        "generation": 1,
        "arm_id": _record(world)["observer_arm_id"],
        "pr_number": 55,
        "base_sha": "e" * 40,
        "head_sha": _HEAD,
        "run_id": 4001,
        "run_attempt": 2,
        "conclusion": "success",
        "refusal": "identity-not-provisioned",
        "digest": written[0],
    }
    assert ledger.calls[-1][:3] == ["comments", "add", "incident-1"]
    assert _sweep(world, ledger) == () and len(ledger.comments) == 1
    assert _pr_leaf(world)[1]["pr_run"] == "already-retained"


def test_a_record_the_item_already_carries_is_marked_written_and_never_written_twice(world):
    _ = _pr_leaf(world)
    ledger = _Ledger()
    row = pending_records(record=_record(world))[0]
    ledger.comments.append({"text": runs.record_text(row=row)})
    assert _sweep(world, ledger) == (row["digest"],)
    assert len(ledger.comments) == 1 and pending_records(record=_record(world)) == ()


@pytest.mark.parametrize(
    ("leaf", "expected"),
    [
        ({"head": "f" * 40}, "not-armed"),
        ({"name": "coverage"}, "not-incident-ci"),
        ({"attempt": None}, "run-attempt-unreadable"),
        ({"attempt": 0}, "run-attempt-unreadable"),
        ({"branch": "incident-scratch/drill-proof"}, "not-pull-request"),
    ],
)
def test_a_run_outside_an_armed_heads_incident_ci_job_receives_no_record(world, leaf, expected):
    assert _pr_leaf(world, **leaf)[1]["pr_run"] == expected
    assert run_tree(record=_record(world))["runs"] == {}


def test_an_invalidated_arm_records_nothing(world):
    with repository_lock(
        directory=world.installation.state, repository=world.installation.repository
    ) as path:
        record = load_record(path=path)
        record["observer_arm_invalidated"] = "ci invalidated"
        save_record(path=path, record=record)
    assert _pr_leaf(world)[1]["pr_run"] == "not-armed"


def test_an_unreadable_controller_record_answers_state_unavailable(world):
    with repository_lock(
        directory=world.installation.state, repository=world.installation.repository
    ) as path:
        record = load_record(path=path)
        record["pr_run_records"] = "corrupt"
        save_record(path=path, record=record)
    assert _pr_leaf(world)[1]["pr_run"] == "state-unavailable"


def _completion(**changes):
    fields = {
        "repository": "owner/repo",
        "job_name": "incident-ci",
        "head_sha": _HEAD,
        "branch": _PR_BRANCH,
        "run_id": 1,
        "run_attempt": 1,
        "conclusion": "failure",
        "identity_provisioned": False,
    }
    return runs.PrRunCompletion(**{**fields, **changes})


def test_with_no_arm_retained_a_completion_is_not_armed(tmp_path):
    assert runs.retain_pr_run(state=tmp_path, completion=_completion()) == "not-armed"


@pytest.mark.parametrize("branch", ["master", "incident-scratch/drill-proof"])
def test_a_run_on_a_push_branch_is_not_a_pull_request_run_even_at_the_armed_head(world, branch):
    completion = _completion(branch=branch)
    assert runs.retain_pr_run(state=world.installation.state, completion=completion) == (
        "not-pull-request"
    )
    assert run_tree(record=_record(world))["runs"] == {}


def test_a_provisioned_installation_records_no_refusal_until_one_is_answered(world):
    completion = _completion(identity_provisioned=True)
    assert runs.retain_pr_run(state=world.installation.state, completion=completion) == ("retained")
    (row,) = pending_records(record=_record(world))
    assert row["content"] == {"conclusion": "failure", "refusal": None}


def _leaf(*, head=_HEAD):
    return LeafCompletion(
        delivery_id="d",
        repository="owner/repo",
        head_sha=head,
        branch=_PR_BRANCH,
        run_id=5,
        job_id=6,
        job_name="incident-ci",
        conclusion="success",
    )


def _retain(world, *, leaf, wake):
    return runs.retain_callback_run(
        state=world.installation.state,
        completion=leaf,
        body=b'{"workflow_job": {"run_attempt": 1}}',
        wake=wake,
        identity_provisioned=False,
    )


def test_the_sweep_is_woken_only_when_a_record_is_retained(world):
    wake = threading.Event()
    assert _retain(world, leaf=_leaf(head="f" * 40), wake=wake) == "not-armed"
    assert not wake.is_set()
    assert _retain(world, leaf=_leaf(), wake=wake) == "retained"
    assert wake.is_set()
    wake.clear()
    assert _retain(world, leaf=_leaf(), wake=wake) == "already-retained"
    assert not wake.is_set()


def test_a_held_fence_answers_state_unavailable_within_its_bound(world, monkeypatch):
    waits = []

    def busy(**kwargs):
        waits.append(kwargs.get("wait_seconds"))
        raise RepositoryFenceBusyError("held")

    monkeypatch.setattr(runs, "repository_lock", busy)
    wake = threading.Event()
    assert _retain(world, leaf=_leaf(), wake=wake) == "state-unavailable"
    assert waits == [5.0] and not wake.is_set()


_KEY = {
    "repository": "owner/repo",
    "incident_item_id": "incident-1",
    "attempt_id": "repair-1",
    "generation": 1,
    "arm_id": "a" * 64,
    "pr_number": 55,
    "base_sha": "e" * 40,
    "head_sha": _HEAD,
    "run_id": 9,
    "run_attempt": 1,
}
_CONTENT = {"conclusion": "success", "refusal": "identity-not-provisioned"}


def _held():
    record: dict[str, object] = {}
    assert add_record(record=record, kind="unpublished", key=dict(_KEY), content=dict(_CONTENT))
    return record


def test_the_store_holds_one_copy_of_each_record_and_marks_it_written():
    record = _held()
    assert not add_record(record=record, kind="unpublished", key=dict(_KEY), content=_CONTENT)
    digest = record_digest(kind="unpublished", key=_KEY, content=_CONTENT)
    assert [row["digest"] for row in pending_records(record=record)] == [digest]
    assert not mark_written(record=record, digest="0" * 64)
    assert mark_written(record=record, digest=digest)
    assert pending_records(record=record) == ()


def _corrupt(path, value):
    record = _held()
    tree = record["pr_run_records"]
    if path == "tree":
        return {"pr_run_records": value}
    entry = tree["runs"]["9:1"][0]
    if path == "runs":
        tree["runs"] = value
    elif path == "rows":
        tree["runs"]["9:1"] = value
    elif path == "entry":
        tree["runs"]["9:1"] = [value]
    else:
        entry[path] = value
    return record


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        ("tree", "not-an-object", TypeError),
        ("tree", {"schema": 2, "runs": {}}, ValueError),
        ("tree", {"schema": True, "runs": {}}, ValueError),
        ("tree", {"schema": 1}, ValueError),
        ("runs", [], TypeError),
        ("rows", {}, TypeError),
        ("entry", "not-an-object", TypeError),
        ("kind", "published", ValueError),
        ("written", 1, ValueError),
        ("digest", "0" * 64, ValueError),
        ("key", {**_KEY, "run_id": -1}, ValueError),
        ("key", {**_KEY, "run_id": True}, ValueError),
        ("key", {**_KEY, "head_sha": 7}, ValueError),
        ("key", {**_KEY, "arm_id": "not-hex"}, ValueError),
        ("key", {k: v for k, v in _KEY.items() if k != "pr_number"}, ValueError),
        ("content", {"conclusion": "success"}, ValueError),
        ("content", {"conclusion": 1, "refusal": None}, ValueError),
        ("content", {"conclusion": "success", "refusal": 1}, ValueError),
    ],
)
def test_malformed_run_state_refuses_rather_than_going_empty(path, value, error):
    with pytest.raises(error):
        run_tree(record=_corrupt(path, value))


def test_carried_digests_reads_only_marked_run_records():
    text = runs.PR_RUN_MARKER + "\n"
    comments = [
        "not-a-row",
        {"text": 7},
        {"text": "livespec-incident-original-run-evidence-v1\n{}"},
        {"text": text + "[]"},
        {"text": text + json.dumps({"digest": 3})},
        {"text": text + json.dumps({"digest": "d" * 64})},
    ]
    assert runs.carried_digests(ledger=lambda _: json.dumps(comments), item_id="i") == {"d" * 64}
    assert runs.carried_digests(ledger=lambda _: "{}", item_id="i") == frozenset()


def test_a_sweep_pass_writes_through_the_credentialed_ledger(world):
    _ = _pr_leaf(world)
    ledger = _Ledger()
    sweep = runs.PrRunSweep(
        state=world.installation.state,
        repository=world.installation.repository,
        ledger=lambda: ledger,
    )
    assert len(sweep.sweep()) == 1 and len(ledger.comments) == 1


def test_a_record_cleared_from_state_mid_write_is_not_resaved(world):
    _ = _pr_leaf(world)

    class Clearing(_Ledger):
        def __call__(self, args):
            if args[:2] == ["comments", "add"]:
                with repository_lock(
                    directory=world.installation.state,
                    repository=world.installation.repository,
                ) as path:
                    record = load_record(path=path)
                    del record["pr_run_records"]
                    save_record(path=path, record=record)
            return super().__call__(args)

    ledger = Clearing()
    assert len(_sweep(world, ledger)) == 1
    assert "pr_run_records" not in _record(world)


def test_the_sweep_writes_nothing_without_the_tenant_credential(tmp_path):
    sweep = runs.PrRunSweep(state=tmp_path, repository="owner/repo", ledger=lambda: None)
    assert sweep.sweep() == ()


def test_the_sweep_survives_an_expected_failure_and_names_it(tmp_path, capsys):
    stop = threading.Event()

    def failing():
        stop.set()
        raise OSError("tenant unreachable")

    sweep = runs.PrRunSweep(
        state=tmp_path, repository="owner/repo", ledger=failing, interval_seconds=0
    )
    sweep.run(stop=stop)
    assert "incident-pr-run-sweep: OSError: tenant unreachable" in capsys.readouterr().err


def test_a_crashed_sweep_brings_the_service_down(tmp_path, monkeypatch):
    """No broad catch in the loop: the thread dies with its traceback, the service exits."""
    seen = []
    monkeypatch.setattr(threading, "excepthook", lambda args: seen.append(args.exc_type))

    def broken():
        raise RuntimeError("a defect, not an expected failure")

    crashes = []
    sweep = runs.PrRunSweep(state=tmp_path, repository="owner/repo", ledger=broken)
    sweep.start(stop=threading.Event(), on_crash=lambda: crashes.append(1)).join(timeout=30)
    assert seen == [RuntimeError] and sweep.crashed.is_set() and crashes == [1]


def test_a_stopped_sweep_does_not_report_a_crash(tmp_path):
    stop = threading.Event()
    stop.set()
    sweep = runs.PrRunSweep(state=tmp_path, repository="owner/repo", ledger=lambda: None)
    sweep.start(stop=stop, on_crash=lambda: pytest.fail("no crash")).join(timeout=30)
    assert not sweep.crashed.is_set()


def test_the_run_attempt_is_read_only_from_a_job_body():
    assert completion_run_attempt(body=b"not json") is None
    assert completion_run_attempt(body=b"[]") is None
    assert completion_run_attempt(body=b'{"workflow_job": []}') is None
    assert completion_run_attempt(body=b'{"workflow_job": {"run_attempt": "2"}}') is None
    assert completion_run_attempt(body=b'{"workflow_job": {"run_attempt": 3}}') == 3


def test_the_installed_ledger_is_the_credentialed_port_or_absent(monkeypatch):
    ledger = Mock()
    ports = SimpleNamespace(canonical=SimpleNamespace(ledger=ledger))
    monkeypatch.setattr(service, "installed_ports", lambda **_: ports)
    assert service.installed_ledger(installation=Mock()) is ledger

    def missing(**_):
        raise FileNotFoundError("reader.env")

    monkeypatch.setattr(service, "installed_ports", missing)
    assert service.installed_ledger(installation=Mock()) is None


def test_the_service_starts_the_run_sweep_with_its_wake_and_its_credentialed_ledger(
    tmp_path, monkeypatch
):
    installation = SimpleNamespace(state=tmp_path, repository="owner/repo", port=8765)
    application = SimpleNamespace(
        installation=installation,
        conflict_journaled=threading.Event(),
        pr_run_retained=threading.Event(),
    )
    monkeypatch.setattr(service.sys, "argv", ["observer-service", "--config", str(tmp_path)])
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(service.ControllerService, "installed", lambda **_: application)
    monkeypatch.setattr(service, "installed_watcher", lambda **_: Mock(failed=threading.Event()))
    monkeypatch.setattr(service, "ConflictSweep", lambda **_: Mock(crashed=threading.Event()))
    monkeypatch.setattr(service, "installed_ledger", lambda **kwargs: kwargs["installation"])
    built = {}

    def sweep(**kwargs):
        built.update(kwargs)
        return Mock(crashed=crashed)

    server = Mock()
    server.__enter__ = Mock(return_value=server)
    server.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(service, "make_server", lambda *_a, **_k: server)
    monkeypatch.setattr(service, "PrRunSweep", sweep)
    crashed = threading.Event()
    assert service.main() == 0
    assert (built["state"], built["repository"]) == (tmp_path, "owner/repo")
    assert built["wake"] is application.pr_run_retained and application.pr_run_retained.is_set()
    assert built["ledger"]() is installation
    crashed.set()
    assert service.main() == 1
