"""The observer answers the master-health reconciler's ownership question.

The reconciler runs on a GitHub-hosted runner, so it cannot take the observer's
repository fence itself. It asks the authenticated `/ordinary-action` query
route, which answers under that fence over the reconciler's whole window
(livespec-dev-tooling-ariayn; review findings F2 and F7 on
livespec-dev-tooling#3915).
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from livespec_dev_tooling._incident_observer_store import (
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling.cross_repo import master_health_reconcile
from livespec_dev_tooling.incident_observer_query import (
    MAX_WINDOW_SHAS,
    ORDINARY_ACTION_PATH,
    RECONCILER_ACTIONS,
    ObserverQuery,
)
from livespec_dev_tooling.incident_observer_service import ControllerService

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
_REPOSITORY = "owner/repo"
_INCIDENT = "a" * 40
_LATER = "d" * 40


@pytest.fixture
def service(tmp_path):
    settings = SimpleNamespace(
        repository=_REPOSITORY,
        state=tmp_path / "protected",
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        webhook_secret=b"webhook" * 8,
    )
    return ControllerService(installation=settings, recover=lambda _: None)


def _register(*, service):
    registration = ObserverRegistration(
        repository=_REPOSITORY,
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="recovery-controller",
        phase="repair",
        head_sha=_INCIDENT,
        run_id=4242,
        required_jobs=("coverage",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical-verified-receipt-1",
    )
    with repository_lock(directory=service.installation.state, repository=_REPOSITORY) as path:
        save_record(
            path=path, record={"registration": registration_record(registration=registration)}
        )


def _ask(*, service, payload, secret=None):
    body = json.dumps(payload).encode()
    secret = service.installation.query_secret if secret is None else secret
    environ = {
        "PATH_INFO": ORDINARY_ACTION_PATH,
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_AUTHORIZATION": "Bearer " + secret.decode(),
    }
    statuses = []
    reply = b"".join(service(environ, lambda status, _headers: statuses.append(status)))
    return statuses[0], json.loads(reply)


def _query(**changes):
    query = {
        "repository": _REPOSITORY,
        "action": "open-revert",
        "window_shas": [_LATER, _INCIDENT],
    }
    query.update(changes)
    return query


def test_a_registered_incident_commit_in_the_window_is_answered_incident_owned(service):
    _register(service=service)
    query = _query()

    status, reply = _ask(service=service, payload=query)

    assert status == "202 Accepted"
    assert reply == {
        "schema": 1,
        "status": "incident-owned",
        "reason": "independent incident controller owns repository action",
        "receipt": None,
        "query": query,
    }


def test_an_unregistered_window_lets_exactly_the_named_step_run(service):
    _register(service=service)
    query = _query(action="rerun-failed-jobs", window_shas=[_LATER])

    status, reply = _ask(service=service, payload=query)

    assert status == "202 Accepted"
    assert reply == {
        "schema": 1,
        "status": "ordinary",
        "reason": "ordinary reconciler policy retained",
        "receipt": "ordinary rerun-failed-jobs retained by the master-health reconciler",
        "query": query,
    }


def test_an_unbound_pre_merge_arm_owns_every_ordinary_step(service):
    with repository_lock(directory=service.installation.state, repository=_REPOSITORY) as path:
        save_record(path=path, record={"observer_arm_id": "f" * 64})

    status, reply = _ask(service=service, payload=_query(window_shas=[]))

    assert (status, reply["status"], reply["reason"]) == (
        "202 Accepted",
        "incident-owned",
        "pre-merge observer owns repository action",
    )


def test_the_control_credential_is_not_the_query_credential(service):
    status, reply = _ask(
        service=service, payload=_query(), secret=service.installation.control_secret
    )

    assert (status, reply["status"]) == ("403 Forbidden", "refused")


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "none"},
        {"action": ["open-revert"]},
        {"action": 7},
        {"window_shas": _LATER},
        {"window_shas": [_LATER.upper()]},
        {"window_shas": [_LATER, _LATER]},
        {"window_shas": [7]},
        {"window_shas": [format(index, "040x") for index in range(MAX_WINDOW_SHAS + 1)]},
        {"head_sha": _LATER},
    ],
)
def test_a_malformed_ownership_query_is_refused_never_answered_ordinary(service, changes):
    status, reply = _ask(service=service, payload=_query(**changes))

    assert (status, reply) == (
        "403 Forbidden",
        {"schema": 1, "status": "refused", "reason": "invalid ordinary-action ownership query"},
    )


def test_a_query_missing_a_field_is_refused(service):
    query = _query()
    del query["window_shas"]

    status, reply = _ask(service=service, payload=query)

    assert (status, reply["status"]) == ("403 Forbidden", "refused")


def test_a_full_window_at_the_bound_is_answered(service):
    window = [format(index, "040x") for index in range(MAX_WINDOW_SHAS)]

    status, reply = _ask(service=service, payload=_query(window_shas=window))

    assert (status, reply["status"]) == ("202 Accepted", "ordinary")


def test_a_query_naming_another_repository_is_refused_by_the_route_itself(service):
    """F7: the route's own repository guard, behind the service's identical check."""
    route = ObserverQuery(installation=service.installation)

    reply = route.execute(path=ORDINARY_ACTION_PATH, payload=_query(repository="other/repo"))

    assert reply == {
        "schema": 1,
        "status": "refused",
        "reason": "invalid ordinary-action ownership query",
    }


def test_corrupt_protected_state_is_refused_rather_than_read_as_ordinary(service):
    with repository_lock(directory=service.installation.state, repository=_REPOSITORY) as path:
        _ = path.write_text("[]", encoding="utf-8")

    status, reply = _ask(service=service, payload=_query())

    assert (status, reply["status"]) == ("403 Forbidden", "refused")


def test_the_route_knows_every_reconciler_step_that_touches_the_repository():
    steps = {
        value
        for name, value in vars(master_health_reconcile).items()
        if name.startswith("STEP_") and isinstance(value, str)
    }

    assert steps - {master_health_reconcile.STEP_NONE} == RECONCILER_ACTIONS
