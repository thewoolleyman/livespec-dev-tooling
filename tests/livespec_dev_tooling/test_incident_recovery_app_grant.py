"""The recovery token grant admits GitHub's mandatory metadata read and nothing wider.

GitHub reports every App installation token's grant with `metadata: read` beside
whatever was requested, because no App can drop that permission. A live mint for
the recovery App on 2026-11-07 answered `{"contents": "write", "metadata": "read"}`
to a request for `{"contents": "write"}`. Any other read, any other write, or a
missing or weaker contents grant is still refused by name.
"""

from __future__ import annotations

import pytest
from livespec_runtime_budget.github_budget import GithubBudgetResponse

from livespec_dev_tooling.incident_recovery_app import RecoveryAppCredential, RecoveryForge

_INSTALLATION = "repos/owner/repo/installation"
_TOKENS = "app/installations/7/access_tokens"


def _connect(*, grant):
    answers = {
        _INSTALLATION: (200, {"id": 7}),
        _TOKENS: (201, {"token": "ghs_x", "permissions": grant}),
    }

    def transport(*, request):
        status, value = answers.get(request.resource, (404, None))
        return GithubBudgetResponse(
            status_code=status, headers={}, value=value, primary_budget_spent=1
        )

    return RecoveryForge.connect(
        repository="owner/repo",
        credential=RecoveryAppCredential(app_id="12345", private_key="PEM"),
        transport=transport,
        clock=lambda: 1_000_000.0,
        signer=lambda **_: b"sig",
    )


def test_the_live_grant_with_mandatory_metadata_read_connects():
    assert isinstance(_connect(grant={"contents": "write", "metadata": "read"}), RecoveryForge)


@pytest.mark.parametrize(
    "grant",
    [
        {"contents": "write", "metadata": "read", "issues": "read"},
        {"contents": "write", "metadata": "read", "workflows": "write"},
        {"contents": "write", "metadata": "write"},
        {"contents": "write", "pull_requests": "write"},
        {"contents": "read", "metadata": "read"},
        {"metadata": "read"},
    ],
)
def test_a_grant_wider_or_weaker_than_contents_write_and_metadata_read_is_refused(grant):
    assert _connect(grant=grant).code == "recovery-app-token-refused"
