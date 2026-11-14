"""A PASSED incident CI aggregate published by its protected job is recorded once."""

from __future__ import annotations

import copy
import hashlib
import io
import json

import pytest

from livespec_dev_tooling.incident_pr_run_records import PR_RUN_MARKER, write_pending
from tests.livespec_dev_tooling import test_incident_ci_identity as identity_tests

trusted = identity_tests.trusted
correlated = identity_tests.correlated
authenticated = identity_tests.authenticated

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
_FALSE = ("authorizes_current_effects", "ci_admission", "authorizes_merge", "normal_factory_proof")


def aggregate_for(query, **changes):
    value = {
        "status": "passed",
        "head_sha": query.head_sha,
        "scope": "d" * 64,
        "passed": ["check-lint", "check-types"],
        "failed": [],
        "missing": [],
        "deferred": [
            {"name": "check-per-file-coverage", "reason": "incident-policy:coverage"},
            {"name": "check-heading-coverage", "reason": "incident-policy:spec"},
            {"name": "check-coverage", "reason": "incident-policy:deferred-dependency-or-artifact"},
        ],
        "context_name": "ci-green",
    }
    return value | changes


def publication(query, **changes):
    return {"query": vars(query), "aggregate": aggregate_for(query), "release": "v1.2.3"} | changes


def call(application, token, body, *, path="/ci/publish", method="POST"):
    raw_body = body if isinstance(body, bytes) else json.dumps(body).encode()
    response = []
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(raw_body)),
        "HTTP_AUTHORIZATION": "Bearer " + token,
        "wsgi.input": io.BytesIO(raw_body),
    }
    raw = b"".join(
        application(environ, lambda status, headers: response.append((status, dict(headers))))
    )
    return response[0][0], json.loads(raw)


def state_path(application):
    return application.installation.state / (hashlib.sha256(b"owner/repo").hexdigest() + ".json")


def runs(application):
    return json.loads(state_path(application).read_bytes())["pr_run_records"]["runs"]


@pytest.fixture
def published(authenticated):
    application, query, token, *_ = authenticated
    application.installation.release = "v1.0.0"
    application.installation.revision = "b" * 40
    return application, query, token


def edit_record(application, change):
    path = state_path(application)
    record = json.loads(path.read_bytes())
    change(record)
    path.write_text(json.dumps(record, sort_keys=True))


def test_passed_aggregate_is_retained_once_and_written_onto_the_item(published):
    application, query, token = published
    status, reply = call(application, token, publication(query))
    assert status == "202 Accepted" and reply["status"] == "published"
    assert all(reply[key] is False for key in _FALSE)
    assert application.pr_run_retained.is_set()
    attached = call(application, token, vars(query), path="/ci/attach")[1]
    [rows] = runs(application).values()
    [row] = rows
    assert row["kind"] == "published" and row["written"] is False
    assert row["content"] == {
        "controller_build": "v1.2.3",
        "attachment_id": attached["attachment_id"],
        "aggregate_digest": reply["aggregate_digest"],
        "passed": ["check-lint", "check-types"],
        "deferred": aggregate_for(query)["deferred"],
        "omitted": ["check-heading-coverage", "check-per-file-coverage"],
    }
    binding = attached["binding"]
    assert row["key"] == {
        "repository": "owner/repo",
        "incident_item_id": "fixture",
        "attempt_id": "repair",
        "generation": 1,
        "arm_id": query.arm_id,
        "pr_number": 55,
        "base_sha": query.base_sha,
        "head_sha": query.head_sha,
        "run_id": binding["run_id"],
        "run_attempt": binding["run_attempt"],
    }
    assert "failed" not in row["content"] and "missing" not in row["content"]

    before = state_path(application).read_bytes()
    application.pr_run_retained.clear()
    status, again = call(application, token, publication(query))
    assert (status, again["status"]) == ("202 Accepted", "retained")
    assert again["aggregate_digest"] == reply["aggregate_digest"]
    assert state_path(application).read_bytes() == before
    assert not application.pr_run_retained.is_set()


def test_the_published_record_is_written_onto_the_incident_item(published):
    application, query, token = published
    assert call(application, token, publication(query))[1]["status"] == "published"
    [[row]] = runs(application).values()
    writes = []

    def ledger(argv):
        writes.append(argv)
        return "[]"

    carried = write_pending(
        state=application.installation.state, repository="owner/repo", ledger=ledger
    )
    assert carried == (row["digest"],)
    [add] = [argv for argv in writes if argv[:2] == ["comments", "add"]]
    assert add[2] == "fixture"
    marker, body = add[3].split("\n", 1)
    assert marker == PR_RUN_MARKER
    assert json.loads(body)["omitted"] == ["check-heading-coverage", "check-per-file-coverage"]
    assert json.loads(body)["kind"] == "published"


def test_a_different_aggregate_for_the_same_run_attempt_is_a_conflict_record(published):
    application, query, token = published
    first = call(application, token, publication(query))[1]
    other = publication(query, aggregate=aggregate_for(query, passed=["check-lint"]))
    status, reply = call(application, token, other)
    assert (status, reply["status"]) == ("409 Conflict", "conflict")
    assert all(reply[key] is False for key in _FALSE)
    [rows] = runs(application).values()
    assert [row["kind"] for row in rows] == ["published", "conflict"]
    assert rows[1]["content"]["retained_digest"] == first["aggregate_digest"]
    assert rows[1]["content"]["offered_digest"] == reply["aggregate_digest"]
    before = state_path(application).read_bytes()
    assert call(application, token, other)[1]["status"] == "conflict"
    assert state_path(application).read_bytes() == before
    # The original aggregate is still answered from its retained record.
    assert call(application, token, publication(query))[1]["status"] == "retained"


def test_stale_after_attachment_retains_the_refusal_and_no_published_record(published):
    application, query, token = published
    assert call(application, token, vars(query), path="/ci/attach")[1]["status"] == "attached"
    edit_record(application, lambda record: record.update(observer_arm_bound=True))
    status, reply = call(application, token, publication(query))
    assert (status, reply["status"], reply["reason"]) == (
        "403 Forbidden",
        "refused",
        "publication-stale",
    )
    assert all(reply[key] is False for key in _FALSE)
    [rows] = runs(application).values()
    assert [(row["kind"], row["content"]) for row in rows] == [
        ("unpublished", {"conclusion": "unknown", "refusal": "publication-stale"})
    ]


def test_stale_before_attachment_records_nothing(published):
    application, query, token = published
    edit_record(application, lambda record: record.update(observer_arm_bound=True))
    status, reply = call(application, token, publication(query))
    assert (status, reply["reason"]) == ("403 Forbidden", "publication-stale")
    assert "pr_run_records" not in json.loads(state_path(application).read_bytes())


def test_an_unverifiable_identity_on_a_current_arm_is_named(published):
    application, query, _ = published
    status, reply = call(application, "not.a.token", publication(query))
    assert (status, reply["reason"]) == ("403 Forbidden", "identity-unverified")
    assert "pr_run_records" not in json.loads(state_path(application).read_bytes())


def test_an_unprovisioned_installation_answers_identity_not_provisioned(published):
    application, query, token = published
    application.installation.ci_identity_policy = None
    status, reply = call(application, token, publication(query))
    assert (status, reply["status"], reply["reason"]) == (
        "403 Forbidden",
        "refused",
        "identity-not-provisioned",
    )
    assert all(reply[key] is False for key in _FALSE)


@pytest.mark.parametrize(
    "change",
    [
        lambda _q: {"extra": 1},
        lambda _q: {"release": "latest"},
        lambda _q: {"release": 7},
        lambda _q: {"query": "not-a-query"},
        lambda q: {"query": vars(q) | {"repository": "other/repo"}},
        lambda q: {"query": vars(q) | {"pr_number": 0}},
        lambda _q: {"aggregate": "passed"},
        lambda q: {"aggregate": aggregate_for(q, status="failed")},
        lambda q: {"aggregate": aggregate_for(q, head_sha="e" * 40)},
        lambda q: {"aggregate": aggregate_for(q, scope="short")},
        lambda q: {"aggregate": aggregate_for(q, scope=5)},
        lambda q: {"aggregate": aggregate_for(q, failed=["check-lint"])},
        lambda q: {"aggregate": aggregate_for(q, missing=["check-lint"])},
        lambda q: {"aggregate": aggregate_for(q, context_name="other")},
        lambda q: {"aggregate": aggregate_for(q, passed=[])},
        lambda q: {"aggregate": aggregate_for(q, passed="check-lint")},
        lambda q: {"aggregate": aggregate_for(q, passed=["lint"])},
        lambda q: {"aggregate": aggregate_for(q, deferred="none")},
        lambda q: {"aggregate": aggregate_for(q, deferred=["check-lint"])},
        lambda q: {"aggregate": aggregate_for(q, deferred=[{"name": "check-lint"}])},
        lambda q: {"aggregate": aggregate_for(q, deferred=[{"name": 1, "reason": "x"}])},
        lambda q: {"aggregate": aggregate_for(q, deferred=[{"name": "check-a", "reason": "a b"}])},
        lambda q: {"aggregate": aggregate_for(q, deferred=[{"name": "check-a", "reason": 1}])},
        lambda _q: {"aggregate": {"status": "passed"}},
    ],
)
def test_a_malformed_publication_is_invalid_before_any_verification(published, change):
    application, query, token = published
    body = publication(query) | change(query)
    status, reply = call(application, token, body)
    assert (status, reply["reason"]) == ("403 Forbidden", "publication-invalid")
    assert all(reply[key] is False for key in _FALSE)
    assert "ci_job_attachments" not in json.loads(state_path(application).read_bytes())


@pytest.mark.parametrize(("body", "method"), [(b"[]", "POST"), (b"{", "POST"), (b"", "GET")])
def test_an_unreadable_request_is_invalid(published, body, method):
    application, _, token = published
    status, reply = call(application, token, body, method=method)
    assert (status, reply["reason"]) == ("403 Forbidden", "publication-invalid")


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda row: row["content"].update(passed="check-lint"),
        lambda row: row["content"].update(attachment_id="short"),
        lambda row: row["content"].update(deferred=[{"name": "check-lint"}]),
        lambda row: row["content"].update(deferred="none"),
        lambda row: row["content"].update(extra=1),
        lambda row: row.update(kind="conflict"),
    ],
)
def test_malformed_retained_state_refuses_as_unavailable(published, corrupt):
    application, query, token = published
    assert call(application, token, publication(query))[1]["status"] == "published"

    def change(record):
        for rows in record["pr_run_records"]["runs"].values():
            corrupt(rows[0])

    edit_record(application, change)
    before = state_path(application).read_bytes()
    status, reply = call(application, token, publication(query))
    assert (status, reply["reason"]) == ("403 Forbidden", "state-unavailable")
    assert state_path(application).read_bytes() == before


def test_a_malformed_conflict_record_refuses_as_unavailable(published):
    application, query, token = published
    _ = call(application, token, publication(query))
    other = publication(query, aggregate=aggregate_for(query, passed=["check-lint"]))
    assert call(application, token, other)[1]["status"] == "conflict"

    def change(record):
        for rows in record["pr_run_records"]["runs"].values():
            rows[1]["content"] = copy.deepcopy(rows[1]["content"]) | {"offered_digest": "x"}

    edit_record(application, change)
    assert call(application, token, other)[1]["reason"] == "state-unavailable"
