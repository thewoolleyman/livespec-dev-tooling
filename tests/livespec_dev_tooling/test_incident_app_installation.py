"""An installation-authenticated call reports the forge's own status and message.

The incident-merge principal turns a refused merge into a named refusal carrying
`HTTP <status> <message>`. A 403 that carries rate-limit headers used to reach it as
`HTTP 0`, because the budgeted client's failure dropped the status and the body
(livespec-dev-tooling-eimhed, measured on PR 5157).
"""

from __future__ import annotations

from livespec_runtime_budget.github_budget import GithubBudgetedClient, GithubBudgetResponse

from livespec_dev_tooling.incident_merge_app import MergeAppCredential, MergeForge

_INSTALLATION = "repos/owner/repo/installation"
_TOKENS = "app/installations/9/access_tokens"
_MERGE = "repos/owner/repo/pulls/7/merge-async"
_GRANT = {
    "contents": "read",
    "pull_requests": "write",
    "checks": "read",
    "statuses": "read",
    "metadata": "read",
}
_RATE_HEADERS = {
    "x-ratelimit-limit": "5000",
    "x-ratelimit-remaining": "4990",
    "x-ratelimit-used": "10",
    "x-ratelimit-reset": "1900000000",
    "x-ratelimit-resource": "core",
}
_FORBIDDEN = {"message": "Resource not accessible by integration"}


def _answer(*, status, value, headers=None):
    return GithubBudgetResponse(
        status_code=status,
        headers=headers or {},
        value=value,
        primary_budget_spent=1,
    )


def _forge_transport(*, request):
    answers = {
        _INSTALLATION: _answer(status=200, value={"id": 9}),
        _TOKENS: _answer(status=201, value={"token": "ghs_m", "permissions": dict(_GRANT)}),
        _MERGE: _answer(status=403, value=_FORBIDDEN, headers=_RATE_HEADERS),
    }
    return answers[request.resource]


def _connect():
    return MergeForge.connect(
        repository="owner/repo",
        credential=MergeAppCredential(app_id="4242", private_key="PEM"),
        transport=_forge_transport,
        clock=lambda: 1_000_000.0,
        signer=lambda **_: b"sig",
    )


def test_a_403_with_rate_limit_headers_reports_its_status_and_forge_message():
    forge = _connect()
    status, answer = forge.request(method="PUT", path="pulls/7/merge-async", value={})
    assert (status, answer) == (403, _FORBIDDEN)


def test_a_failure_with_no_recorded_response_reports_status_zero_naming_its_cause():
    forge = _connect()
    client = GithubBudgetedClient(transport=_forge_transport, max_attempts=1)
    forge_with_plain_client = type(forge)(
        repository=forge.repository, token=forge.token, client=client
    )
    status, answer = forge_with_plain_client.request(
        method="PUT", path="pulls/7/merge-async", value={}
    )
    facts = [status == 0, "blocked by" in str(answer)]
    assert all(facts)
