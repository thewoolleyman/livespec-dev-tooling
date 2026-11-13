"""A publication whose identity does not verify reads and writes no controller state."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_ci_attachment as attachment_module
from livespec_dev_tooling import incident_ci_publication as publication_module
from tests.livespec_dev_tooling import test_incident_ci_identity as identity_tests
from tests.livespec_dev_tooling import test_incident_ci_publication as publication_tests

trusted = identity_tests.trusted
correlated = identity_tests.correlated
authenticated = identity_tests.authenticated
published = publication_tests.published

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4


def snapshot(directory):
    return {
        str(path.relative_to(directory)): path.read_bytes() if path.is_file() else None
        for path in sorted(directory.rglob("*"))
    }


@pytest.mark.parametrize("token", ["not.a.token", "", "a.b.c"])
def test_an_unverified_identity_is_refused_before_any_state_is_touched(
    published, monkeypatch, token
):
    application, query, _ = published
    locks = Mock(wraps=publication_module.repository_lock)
    reads = Mock(wraps=publication_module.load_record)
    attaches = Mock(wraps=attachment_module.repository_lock)
    monkeypatch.setattr(publication_module, "repository_lock", locks)
    monkeypatch.setattr(publication_module, "load_record", reads)
    monkeypatch.setattr(attachment_module, "repository_lock", attaches)
    before = snapshot(application.installation.state)
    body = publication_tests.publication(query)
    status, reply = publication_tests.call(application, token, body)
    facts = [
        (status, reply["reason"]) == ("403 Forbidden", "identity-unverified"),
        locks.call_count == 0,
        reads.call_count == 0,
        attaches.call_count == 0,
        snapshot(application.installation.state) == before,
        not application.pr_run_retained.is_set(),
    ]
    assert all(facts), facts
