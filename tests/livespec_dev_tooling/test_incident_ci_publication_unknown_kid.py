"""A token signed under a key the policy does not pin is refused by its key id, with no effect."""

from __future__ import annotations

from unittest.mock import Mock

from livespec_dev_tooling import incident_ci_publication as publication_module
from tests.livespec_dev_tooling import test_incident_ci_identity as identity_tests
from tests.livespec_dev_tooling import test_incident_ci_oidc_refusals as refusal_tests
from tests.livespec_dev_tooling import test_incident_ci_publication as publication_tests
from tests.livespec_dev_tooling import test_incident_ci_publication_no_side_effect as effect_tests

trusted = identity_tests.trusted
correlated = identity_tests.correlated
authenticated = identity_tests.authenticated
published = publication_tests.published

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4


def test_a_rotated_signing_key_is_refused_by_name_before_any_state_is_touched(
    published, trusted, monkeypatch
):
    application, query, _ = published
    rotated = refusal_tests.resign(trusted, header={"typ": "JWT", "alg": "RS256", "kid": "k-2027"})
    locks = Mock(wraps=publication_module.repository_lock)
    monkeypatch.setattr(publication_module, "repository_lock", locks)
    before = effect_tests.snapshot(application.installation.state)
    status, reply = publication_tests.call(
        application, rotated, publication_tests.publication(query)
    )
    assert reply["reason"] == "identity-key-unknown: kid k-2027"
    assert (status, reply["status"]) == ("403 Forbidden", "refused")
    assert locks.call_count == 0
    assert effect_tests.snapshot(application.installation.state) == before


def test_a_pinned_key_that_fails_verification_stays_identity_unverified(published, trusted):
    application, query, _ = published
    forged = refusal_tests.resign(trusted, claims=trusted[3] | {"aud": "someone-else"})
    status, reply = publication_tests.call(
        application, forged, publication_tests.publication(query)
    )
    assert (status, reply["reason"]) == ("403 Forbidden", "identity-unverified")
