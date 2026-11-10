"""The reconciler's workflow-side ownership transport, end to end in process.

Each Definition of Done bullet of livespec-dev-tooling-ariayn is driven through
the real CLI, the real `CiAuthorityBoundary` client and the real observer
`ControllerService` with its protected state directory. Only the TLS socket is
replaced, by a connection that hands the request to the WSGI service.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_ci_authority, master_health_observer
from livespec_dev_tooling._incident_observer_store import (
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling.incident_observer_service import ControllerService

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
_UNOBSERVED = "thewoolleyman/livespec"
_TOKEN = "query-token-fixture"
_GREEN = "1" * 40
_INCIDENT = "a" * 40
_LATER = "d" * 40
_NO_ACTION = "; no rerun, classification or revert action is taken in this pass\n"
_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def observer(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        repository=_REPOSITORY,
        state=tmp_path / "protected",
        control_secret=b"control" * 8,
        query_secret=_TOKEN.encode(),
        webhook_secret=b"webhook" * 8,
    )
    service = ControllerService(installation=settings, recover=lambda _: None)

    class Connection:
        def __init__(self, host, *, port, timeout):
            self.target = (host, port, timeout)
            self.response = None

        def request(self, method, path, *, body, headers):
            environ = {
                "PATH_INFO": path,
                "REQUEST_METHOD": method,
                "CONTENT_LENGTH": str(len(body)),
                "wsgi.input": io.BytesIO(body),
                "HTTP_AUTHORIZATION": headers["Authorization"],
            }
            statuses = []
            reply = b"".join(service(environ, lambda status, _headers: statuses.append(status)))
            self.response = SimpleNamespace(
                status=int(statuses[0].split()[0]), read=lambda limit: reply[:limit]
            )

        def getresponse(self):
            return self.response

        def close(self):
            self.response = None

    monkeypatch.setattr(incident_ci_authority.http.client, "HTTPSConnection", Connection)
    monkeypatch.delenv("LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR", raising=False)
    return settings


def _register(*, settings, head_sha=_INCIDENT, run_id=4242):
    registration = ObserverRegistration(
        repository=_REPOSITORY,
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="recovery-controller",
        phase="repair",
        head_sha=head_sha,
        run_id=run_id,
        required_jobs=("coverage",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical-verified-receipt-1",
    )
    with repository_lock(directory=settings.state, repository=_REPOSITORY) as path:
        save_record(
            path=path, record={"registration": registration_record(registration=registration)}
        )


def _commit(*, sha, parent, conclusion):
    return {"sha": sha, "parent_sha": parent, "ci_conclusion": conclusion}


# The incident commit failed (run 4242) and an ordinary commit landed on top of it
# and failed too (run 5000), so the reconciler would rerun 5000 and revert the
# incident commit, the culprit at the bottom of the red episode.
_STATE = {
    "head_sha": _LATER,
    "commits": [
        _commit(sha=_LATER, parent=_INCIDENT, conclusion="failure"),
        _commit(sha=_INCIDENT, parent=_GREEN, conclusion="failure"),
        _commit(sha=_GREEN, parent="0" * 40, conclusion="success"),
    ],
}
_RUNS = [
    {"head_sha": _LATER, "conclusion": "failure", "id": 5000},
    {"head_sha": _INCIDENT, "conclusion": "failure", "id": 4242},
    {"head_sha": _GREEN, "conclusion": "success", "id": 4000},
]


def _run(tmp_path, *, step, state=_STATE, runs=_RUNS, repository=_REPOSITORY, env=None):
    paths = {}
    for name, value in (("state", state), ("runs", runs), ("step", step)):
        paths[name] = tmp_path / (name + ".json")
        _ = paths[name].write_text(
            value if isinstance(value, str) else json.dumps(value), encoding="utf-8"
        )
    environ = (
        {
            "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example",
            "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": _TOKEN,
        }
        if env is None
        else env
    )
    return master_health_observer.main(
        argv=[
            "--repository",
            repository,
            "--state",
            str(paths["state"]),
            "--runs",
            str(paths["runs"]),
            "--step",
            str(paths["step"]),
        ],
        environ=environ,
    )


_REVERT = {"kind": "open-revert", "culprit_sha": _INCIDENT}
_RERUN = {"kind": "rerun-failed-jobs", "culprit_sha": None}


def test_dod1_a_registered_incident_run_is_incident_owned(tmp_path, observer, capsys):
    """Head SHA and run id the observer registered: rerun and revert left to it."""
    _register(settings=observer)

    revert = _run(tmp_path, step=_REVERT)
    revert_out = capsys.readouterr()
    rerun = _run(tmp_path, step=_RERUN, runs=_RUNS[1:])
    rerun_out = capsys.readouterr()

    owned = {
        "receipt": None,
        "reason": "independent incident controller owns repository action",
        "status": "incident-owned",
    }
    assert (revert, json.loads(revert_out.out), revert_out.err) == (0, owned, "")
    assert (rerun, json.loads(rerun_out.out), rerun_out.err) == (0, owned, "")


def test_f2_an_incident_commit_inside_the_window_owns_a_later_runs_rerun(
    tmp_path, observer, capsys
):
    """Neither the newest nor the oldest commit of the window: still incident-owned."""
    _register(settings=observer)
    pending = "0" * 40
    state = {
        "head_sha": pending,
        "commits": [_commit(sha=pending, parent=_LATER, conclusion="pending"), *_STATE["commits"]],
    }

    status = _run(tmp_path, step=_RERUN, state=state)

    assert (status, json.loads(capsys.readouterr().out)["status"]) == (0, "incident-owned")


def test_dod2_an_unbound_pre_merge_arm_is_incident_owned(tmp_path, observer, capsys):
    with repository_lock(directory=observer.state, repository=_REPOSITORY) as path:
        save_record(path=path, record={"observer_arm_id": "f" * 64})

    status = _run(tmp_path, step={"kind": "close-revert"})

    assert status == 0
    assert json.loads(capsys.readouterr().out) == {
        "receipt": None,
        "reason": "pre-merge observer owns repository action",
        "status": "incident-owned",
    }


def test_dod3_an_unregistered_run_keeps_its_policy_under_shared_ownership(
    tmp_path, observer, capsys
):
    """The observer's receipt names the one ordinary step it lets run."""
    _register(settings=observer, head_sha="e" * 40, run_id=9999)

    status = _run(tmp_path, step=_RERUN)

    assert status == 0
    assert json.loads(capsys.readouterr().out) == {
        "receipt": "ordinary rerun-failed-jobs retained by the master-health reconciler",
        "reason": "ordinary reconciler policy retained",
        "status": "ordinary",
    }


def test_dod4_an_unreadable_answer_names_its_cause_and_stops_the_pass(tmp_path, observer, capsys):
    _register(settings=observer)

    status = _run(
        tmp_path,
        step=_REVERT,
        env={
            "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example",
            "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "wrong-token",
        },
    )
    out = capsys.readouterr()
    cause = "HTTP 403 while reading /ordinary-action from observer.example:443 as observer.example"

    assert (status, out.out) == (1, "")
    assert out.err == (
        "incident-ci: observer read refused: "
        + cause
        + "\nmaster-health: the incident observer gave no readable ownership answer: "
        + cause
        + _NO_ACTION
    )


@pytest.mark.usefixtures("observer")
def test_dod4_a_missing_token_is_named_rather_than_read_as_no_observer(tmp_path, capsys):
    status = _run(
        tmp_path, step=_REVERT, env={"LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example"}
    )

    assert status == 1
    assert capsys.readouterr().err.endswith(
        "no readable ownership answer: the observer query token is empty, oversize or not a"
        " valid header value; no connection was attempted" + _NO_ACTION
    )


def test_dod5_a_repository_with_no_observer_runs_its_policy_unasked(tmp_path, monkeypatch, capsys):
    client = Mock()
    monkeypatch.setattr(master_health_observer, "CiAuthorityBoundary", client)

    status = _run(tmp_path, step=_REVERT, repository=_UNOBSERVED, env={})

    assert status == 0
    assert json.loads(capsys.readouterr().out) == {
        "receipt": None,
        "reason": "no incident observer is configured for this repository",
        "status": "ordinary",
    }
    assert client.call_count == 0


def test_f4_an_observed_repository_with_an_empty_url_fails_closed(tmp_path, capsys):
    """A variable not mapped through workflow_call reads as empty; that is not 'no observer'."""
    status = _run(tmp_path, step=_REVERT, env={"LIVESPEC_INCIDENT_OBSERVER_URL": ""})
    out = capsys.readouterr()

    assert (status, out.out) == (1, "")
    assert out.err == (
        "master-health: committed configuration says "
        + _REPOSITORY
        + " has an incident observer, but LIVESPEC_INCIDENT_OBSERVER_URL is empty in this run"
        + _NO_ACTION
    )


def test_a_step_that_takes_no_action_is_not_asked_about(tmp_path, capsys):
    status = _run(tmp_path, step={"kind": "none"}, env={})

    assert status == 0
    assert json.loads(capsys.readouterr().out)["reason"] == (
        "the step takes no action; ownership not asked"
    )


@pytest.mark.parametrize("step", ["not json", [], {"kind": 7}])
def test_an_unreadable_step_fails_closed(tmp_path, capsys, step):
    status = _run(tmp_path, step=step)

    assert status == 1
    assert re.fullmatch(
        r"master-health: the decided step \S+step\.json is unreadable or malformed"
        + re.escape(_NO_ACTION),
        capsys.readouterr().err,
    )


@pytest.mark.parametrize(
    ("state", "runs"),
    [
        ("not json", _RUNS),
        (_STATE, {"runs": []}),
        ({"head_sha": 7, "commits": []}, _RUNS),
        ({"head_sha": _LATER, "commits": {}}, _RUNS),
    ],
)
@pytest.mark.usefixtures("observer")
def test_an_unreadable_recording_fails_closed(tmp_path, capsys, state, runs):
    status = _run(tmp_path, step=_REVERT, state=state, runs=runs)

    assert status == 1
    assert capsys.readouterr().err == (
        "master-health: the recorded state or gating runs are unreadable or malformed" + _NO_ACTION
    )


def _window(*, state=_STATE, runs=(), step=None):
    return master_health_observer.ownership_window(
        state=state, runs=list(runs), step={} if step is None else step
    )


def test_the_window_walks_from_the_head_to_the_newest_green_commit():
    pending = "2" * 40
    state = {
        "head_sha": pending,
        "commits": [_commit(sha=pending, parent=_LATER, conclusion="pending"), *_STATE["commits"]],
    }

    assert _window(state=state) == frozenset({pending, _LATER, _INCIDENT})


def test_the_window_adds_the_rerun_target_and_the_culprit_outside_the_walk():
    green_head = {"head_sha": _GREEN, "commits": [_STATE["commits"][2]]}
    old = "3" * 40

    assert _window(state=green_head) == frozenset()
    assert _window(
        state=green_head,
        runs=[
            {"conclusion": "success", "head_sha": _GREEN},
            "x",
            {"conclusion": "failure", "head_sha": old},
        ],
        step={"culprit_sha": _INCIDENT},
    ) == frozenset({old, _INCIDENT})


def test_the_window_keeps_an_unrecorded_head_and_survives_a_parent_cycle():
    looped = {
        "head_sha": _LATER,
        "commits": [
            _commit(sha=_LATER, parent=_INCIDENT, conclusion="failure"),
            _commit(sha=_INCIDENT, parent=_LATER, conclusion="failure"),
        ],
    }

    assert _window(state={"head_sha": _LATER, "commits": []}) == frozenset({_LATER})
    assert _window(state=looped) == frozenset({_LATER, _INCIDENT})


@pytest.mark.parametrize(
    "state",
    [
        {"head_sha": _LATER, "commits": ["not a commit"]},
        {"head_sha": "HEAD", "commits": []},
        {
            "head_sha": _LATER,
            "commits": [
                _commit(sha=_LATER, parent="NOT-A-SHA", conclusion="failure"),
                _commit(sha="NOT-A-SHA", parent="", conclusion="failure"),
            ],
        },
    ],
)
def test_a_malformed_recording_has_no_window(state):
    assert _window(state=state) is None


def test_the_committed_observed_repositories_match_the_observer_role():
    """Installing an observer and fencing that repository's reconciler are one change."""
    defaults = (_REPO_ROOT / "ansible/roles/incident_observer/defaults/main.yml").read_text(
        encoding="utf-8"
    )
    declared = re.findall(r"(?m)^incident_observer_repository:\s*(\S+)\s*$", defaults)

    assert frozenset(declared) == master_health_observer.OBSERVED_REPOSITORIES
