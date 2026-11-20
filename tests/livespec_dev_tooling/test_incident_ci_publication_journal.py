"""A refused POST /ci/publish writes one journal line naming its reason, never a secret."""

from __future__ import annotations

import pytest

from tests.livespec_dev_tooling import test_incident_ci_identity as identity_tests
from tests.livespec_dev_tooling import test_incident_ci_publication as publication_tests

trusted = identity_tests.trusted
correlated = identity_tests.correlated
authenticated = identity_tests.authenticated
published = publication_tests.published

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-q6uucs


def test_an_unverifiable_token_is_journaled_by_reason_code_and_not_by_token(published, capsys):
    application, query, _ = published
    _status, reply = publication_tests.call(
        application, "not.a.token", publication_tests.publication(query)
    )
    journal = capsys.readouterr().err
    assert reply["reason"] == "identity-unverified"
    assert journal.splitlines() == ["ci-publish refused: identity-unverified"]
    assert "not.a.token" not in journal


def test_an_attachment_the_signature_passed_is_journaled_with_the_attachment_reason(
    published, capsys, monkeypatch
):
    application, query, token = published

    class Declined:
        def __init__(self, *, installation):
            self.installation = installation

        def execute(self, **_ignored):
            return {
                "schema": 1,
                "status": "refused",
                "reason": "CI identity observations changed or unavailable",
            }

    monkeypatch.setattr("livespec_dev_tooling.incident_ci_publication.CiJobAttachment", Declined)
    _status, reply = publication_tests.call(
        application, token, publication_tests.publication(query)
    )
    journal = capsys.readouterr().err
    assert reply["reason"] == "identity-unverified"
    assert journal.splitlines() == [
        "ci-publish refused: identity-unverified (attachment: "
        "CI identity observations changed or unavailable)"
    ]
    assert token not in journal


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            b'{"unreadable-body-value":"must-not-reach-the-journal"}',
            "ci-publish refused: publication-invalid "
            "(detail: request body is unreadable or invalid)",
        ),
        (
            lambda query: publication_tests.publication(query)
            | {"query": {"repository": "other/repo"}},
            "ci-publish refused: publication-invalid "
            "(detail: request has no valid query for this repository)",
        ),
    ],
)
def test_publication_invalid_refusals_name_their_site_without_request_values(
    published, capsys, body, expected
):
    application, query, token = published
    body = body(query) if callable(body) else body

    _status, reply = publication_tests.call(application, token, body)

    journal = capsys.readouterr().err
    assert reply["reason"] == "publication-invalid"
    assert journal.splitlines() == [expected]
    assert "must-not-reach-the-journal" not in journal
