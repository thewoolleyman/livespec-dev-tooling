"""Every OIDC route that reports a reason names a signing key the policy does not pin."""

from __future__ import annotations

import pytest

from tests.livespec_dev_tooling import test_incident_ci_attachment as attachment_tests
from tests.livespec_dev_tooling import test_incident_ci_identity as identity_tests
from tests.livespec_dev_tooling import test_incident_ci_oidc_refusals as refusal_tests

trusted = identity_tests.trusted
correlated = identity_tests.correlated
authenticated = identity_tests.authenticated

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
_ROTATED = {"typ": "JWT", "alg": "RS256", "kid": "k-2027"}


@pytest.mark.parametrize("path", ["/ci/identity", "/ci/attach"])
def test_a_rotated_signing_key_is_refused_by_its_key_id(authenticated, trusted, path) -> None:
    application, query, _, _, calls, effects = authenticated
    rotated = refusal_tests.resign(trusted, header=_ROTATED)
    (status, _), reply = attachment_tests.call(application, path, query, rotated)
    assert reply["reason"] == "identity-key-unknown: kid k-2027"
    assert (status, reply["status"]) == ("403 Forbidden", "refused")
    assert (calls, effects) == ([], [])


@pytest.mark.parametrize("path", ["/ci/identity", "/ci/attach"])
def test_a_pinned_key_that_fails_verification_keeps_the_generic_reason(
    authenticated, trusted, path
) -> None:
    application, query, _, _, _, _ = authenticated
    forged = refusal_tests.resign(trusted, claims=trusted[3] | {"aud": "someone-else"})
    (status, _), reply = attachment_tests.call(application, path, query, forged)
    assert (status, reply["reason"]) == (
        "403 Forbidden",
        "CI issuer identity unverifiable or unsupported",
    )
