"""The observer refuses malformed ordinary-action ownership requests."""

from __future__ import annotations

import pytest

from tests.livespec_dev_tooling.test_incident_observer_query import (
    _request,
)
from tests.livespec_dev_tooling.test_incident_observer_query import (
    provisioned as _provisioned,
)


@pytest.fixture
def provisioned(tmp_path, monkeypatch):
    """Reuse the protected observer fixture without relying on module collection order."""
    return _provisioned.__wrapped__(tmp_path, monkeypatch)


def test_an_ordinary_action_request_with_a_nonpositive_run_id_is_refused(provisioned) -> None:
    """Ownership queries name an exact positive workflow run."""
    application, _, _, _ = provisioned
    query = {"repository": "owner/repo", "head_sha": "e" * 40, "run_id": 0}

    response, result = _request(application=application, path="/ordinary-action", payload=query)

    assert response[0] == "403 Forbidden"
    assert result == {
        "schema": 1,
        "status": "refused",
        "reason": "invalid ordinary action ownership query",
    }
