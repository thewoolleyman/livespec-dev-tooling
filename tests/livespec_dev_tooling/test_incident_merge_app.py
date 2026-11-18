"""The incident-merge App credential is its own identity with exactly the merge grant.

SPECIFICATION/contracts.md gives the expedited incident merge to an INDEPENDENTLY
provisioned incident-merge principal. Its App id
must be the committed incident-merge integration id and never the recovery App's,
and its installation token may hold only contents read, pull_requests write, checks
read, statuses read and GitHub's mandatory metadata read.
"""

from __future__ import annotations

import pytest
from livespec_runtime_budget.github_budget import GithubBudgetResponse

from livespec_dev_tooling.incident_merge_app import (
    MERGE_APP_ID_ENV,
    MERGE_APP_KEY_ENV,
    MergeAppCredential,
    MergeForge,
)
from livespec_dev_tooling.incident_recovery_app import AppRefusal

_BODY = "".join(chr(65 + index % 26) for index in range(130))
_KEY = f"-----BEGIN RSA PRIVATE KEY----- {_BODY} -----END RSA PRIVATE KEY-----"
_MERGE_ID = 4242
_RECOVERY_ID = 1717
_INSTALLATION = "repos/owner/repo/installation"
_TOKENS = "app/installations/9/access_tokens"
_GRANT = {
    "contents": "read",
    "pull_requests": "write",
    "checks": "read",
    "statuses": "read",
    "metadata": "read",
}


def _load(*, environ, merge=_MERGE_ID, recovery=_RECOVERY_ID):
    return MergeAppCredential.from_env(
        environ=environ, merge_integration_id=merge, recovery_integration_id=recovery
    )


def test_the_committed_merge_app_loads_with_a_rewrapped_key_never_in_repr():
    credential = _load(environ={MERGE_APP_ID_ENV: "4242", MERGE_APP_KEY_ENV: _KEY})
    assert isinstance(credential, MergeAppCredential)
    lines = credential.private_key.splitlines()
    facts = [
        credential.app_id == "4242",
        lines[0] == "-----BEGIN RSA PRIVATE KEY-----",
        "".join(lines[1:-1]) == _BODY,
        _BODY not in repr(credential),
    ]
    assert all(facts)


@pytest.mark.parametrize(
    ("environ", "merge", "recovery", "code"),
    [
        ({}, _MERGE_ID, _RECOVERY_ID, "incident-merge-app-credential-absent"),
        (
            {MERGE_APP_ID_ENV: "4242"},
            _MERGE_ID,
            _RECOVERY_ID,
            "incident-merge-app-credential-absent",
        ),
        (
            {MERGE_APP_KEY_ENV: _KEY},
            _MERGE_ID,
            _RECOVERY_ID,
            "incident-merge-app-credential-absent",
        ),
        (
            {MERGE_APP_ID_ENV: "app", MERGE_APP_KEY_ENV: _KEY},
            _MERGE_ID,
            _RECOVERY_ID,
            "incident-merge-app-credential-malformed",
        ),
        (
            {MERGE_APP_ID_ENV: "\uff14\uff12", MERGE_APP_KEY_ENV: _KEY},
            _MERGE_ID,
            _RECOVERY_ID,
            "incident-merge-app-credential-malformed",
        ),
        (
            {MERGE_APP_ID_ENV: "4242", MERGE_APP_KEY_ENV: "not a key"},
            _MERGE_ID,
            _RECOVERY_ID,
            "incident-merge-app-credential-malformed",
        ),
        (
            {MERGE_APP_ID_ENV: "4242", MERGE_APP_KEY_ENV: _KEY},
            None,
            _RECOVERY_ID,
            "incident-merge-app-not-declared",
        ),
        (
            {MERGE_APP_ID_ENV: "4243", MERGE_APP_KEY_ENV: _KEY},
            _MERGE_ID,
            _RECOVERY_ID,
            "incident-merge-app-not-the-declared-app",
        ),
        (
            {MERGE_APP_ID_ENV: "1717", MERGE_APP_KEY_ENV: _KEY},
            _MERGE_ID,
            _RECOVERY_ID,
            "incident-merge-app-is-the-recovery-app",
        ),
        (
            {MERGE_APP_ID_ENV: "1717", MERGE_APP_KEY_ENV: _KEY},
            _RECOVERY_ID,
            _RECOVERY_ID,
            "incident-merge-app-is-the-recovery-app",
        ),
    ],
)
def test_an_absent_malformed_or_foreign_merge_app_is_a_named_refusal(
    environ, merge, recovery, code
):
    refusal = _load(environ=environ, merge=merge, recovery=recovery)
    assert isinstance(refusal, AppRefusal)
    assert refusal.code == code


def test_no_declared_recovery_app_admits_the_committed_merge_app():
    credential = _load(environ={MERGE_APP_ID_ENV: "4242", MERGE_APP_KEY_ENV: _KEY}, recovery=None)
    assert isinstance(credential, MergeAppCredential)


class _Forge:
    def __init__(self, **answers):
        self.answers, self.requests = answers, []

    def __call__(self, *, request):
        self.requests.append(request)
        status, value = self.answers.get(request.resource, (404, None))
        return GithubBudgetResponse(
            status_code=status, headers={}, value=value, primary_budget_spent=1
        )


def _connect(forge, *, signer=lambda **_: b"sig"):
    return MergeForge.connect(
        repository="owner/repo",
        credential=MergeAppCredential(app_id="4242", private_key="PEM"),
        transport=forge,
        clock=lambda: 1_000_000.0,
        signer=signer,
    )


def test_connect_requests_exactly_the_merge_grant_and_calls_as_the_installation():
    forge = _Forge(
        **{
            _INSTALLATION: (200, {"id": 9}),
            _TOKENS: (201, {"token": "ghs_m", "permissions": dict(_GRANT)}),
            "repos/owner/repo/pulls/7": (200, {"number": 7}),
        }
    )
    connected = _connect(forge)
    assert isinstance(connected, MergeForge)
    answer = connected.request(method="GET", path="pulls/7")
    facts = [
        "ghs_m" not in repr(connected),
        forge.requests[1].value == {"repositories": ["repo"], "permissions": _GRANT},
        answer == (200, {"number": 7}),
        forge.requests[2].headers["Authorization"] == "Bearer ghs_m",
    ]
    assert all(facts)


@pytest.mark.parametrize(
    "grant",
    [
        {**_GRANT, "administration": "write"},
        {**_GRANT, "administration": "read"},
        {**_GRANT, "workflows": "write"},
        {**_GRANT, "issues": "write"},
        {**_GRANT, "contents": "write"},
        {**_GRANT, "pull_requests": "read"},
        {key: value for key, value in _GRANT.items() if key != "checks"},
        {key: value for key, value in _GRANT.items() if key != "metadata"},
        {"contents": "write", "metadata": "read"},
    ],
)
def test_a_grant_wider_or_weaker_than_the_merge_grant_is_refused(grant):
    forge = _Forge(
        **{
            _INSTALLATION: (200, {"id": 9}),
            _TOKENS: (201, {"token": "ghs_m", "permissions": grant}),
        }
    )
    refusal = _connect(forge)
    assert isinstance(refusal, AppRefusal)
    assert refusal.code == "incident-merge-app-token-refused"


@pytest.mark.parametrize(
    ("answers", "signer", "code"),
    [
        ({}, lambda **_: b"", "incident-merge-app-signing-unavailable"),
        ({}, lambda **_: b"sig", "incident-merge-app-not-installed"),
    ],
)
def test_connect_names_the_merge_app_in_every_refusal(answers, signer, code):
    refusal = _connect(_Forge(**answers), signer=signer)
    assert isinstance(refusal, AppRefusal)
    assert refusal.code == code
    assert "incident-merge App" in refusal.detail
