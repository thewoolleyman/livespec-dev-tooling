"""The incident-merge principal's own GitHub App identity and its scoped forge access.

The incident-merge principal that SPECIFICATION/contracts.md defines for expedited
incident execution merges one green expedited repair pull request outside the
merge queue. It is an INDEPENDENTLY provisioned App: never the
recovery App, whose installation is the bypass that lets an exact incident inverse
reach master, and never the fleet factory or publishing bot.

Its credential is read from the two variables the credential wrapper projects,
`LIVESPEC_INCIDENT_MERGE_APP_ID` and `LIVESPEC_INCIDENT_MERGE_APP_PRIVATE_KEY`, and
it is accepted only when the App id it names is the repository's committed
`incident_merge_integration_id` and is not the committed recovery integration id. A
missing, malformed or mismatched credential is a NAMED refusal; nothing falls back
to another identity.

Its installation token holds exactly what merging a verified pull request needs:
`contents: read`, `pull_requests: write`, `checks: read`, `statuses: read` and
GitHub's mandatory `metadata: read`. A token reporting any other grant, including
`administration` or `workflows`, or a weaker one, is refused, so this principal can
merge a pull request but can never push, move a ref or edit protection.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_runtime_budget.github_budget import (  # noqa: E402 — vendor-path-aware import.
    GithubBudgetedClient,
    GithubBudgetResponse,
)

from livespec_dev_tooling._incident_app_installation import (  # noqa: E402
    AppRefusal,
    InstallationScope,
    installation_request,
    mint_installation_token,
)
from livespec_dev_tooling._incident_recovery_signing import openssl_sign  # noqa: E402
from livespec_dev_tooling.incident_recovery_app import (  # noqa: E402
    pem_private_key,
    urllib_transport,
)

__all__: list[str] = [
    "MERGE_APP_ID_ENV",
    "MERGE_APP_KEY_ENV",
    "MERGE_SCOPE",
    "MergeAppCredential",
    "MergeForge",
]

MERGE_APP_ID_ENV = "LIVESPEC_INCIDENT_MERGE_APP_ID"
MERGE_APP_KEY_ENV = "LIVESPEC_INCIDENT_MERGE_APP_PRIVATE_KEY"
_MERGE_GRANT = {
    "contents": "read",
    "pull_requests": "write",
    "checks": "read",
    "statuses": "read",
    "metadata": "read",
}
MERGE_SCOPE = InstallationScope(
    identity="incident-merge App",
    code_prefix="incident-merge-app",
    grant_label="incident-merge",
    permissions=dict(_MERGE_GRANT),
    accepted=(dict(_MERGE_GRANT),),
)


def _refusal(*, code: str, detail: str) -> AppRefusal:
    return AppRefusal(code=f"incident-merge-app-{code}", detail=detail)


@dataclass(frozen=True, kw_only=True)
class MergeAppCredential:
    """The incident-merge App's id and private key, read from the projected variables."""

    app_id: str
    private_key: str = field(repr=False)

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str],
        merge_integration_id: int | None,
        recovery_integration_id: int | None,
    ) -> MergeAppCredential | AppRefusal:
        """Read the projected App id and key, refusing any id but the committed merge App's."""
        app_id, key = environ.get(MERGE_APP_ID_ENV, ""), environ.get(MERGE_APP_KEY_ENV, "")
        if not app_id or not key:
            return _refusal(
                code="credential-absent",
                detail=f"{MERGE_APP_ID_ENV} and {MERGE_APP_KEY_ENV} are not both projected",
            )
        pem = pem_private_key(key=key)
        if not (app_id.isascii() and app_id.isdigit()) or pem is None:
            return _refusal(
                code="credential-malformed",
                detail=f"{MERGE_APP_ID_ENV} must be a numeric id and {MERGE_APP_KEY_ENV} a PEM key",
            )
        if merge_integration_id is None:
            return _refusal(
                code="not-declared",
                detail="no incident_merge_integration_id is committed for this repository",
            )
        if int(app_id) == recovery_integration_id:
            return _refusal(
                code="is-the-recovery-app",
                detail=f"App {app_id} is the recovery App, never the incident-merge principal",
            )
        if int(app_id) != merge_integration_id:
            return _refusal(
                code="not-the-declared-app",
                detail=f"App {app_id} is not the committed incident-merge App",
            )
        return cls(app_id=app_id, private_key=pem)


@dataclass(frozen=True, kw_only=True)
class MergeForge:
    """One process's REST access as the incident-merge App installation on one repository."""

    repository: str
    token: str = field(repr=False)
    client: GithubBudgetedClient

    @classmethod
    def connect(
        cls,
        *,
        repository: str,
        credential: MergeAppCredential,
        transport: Callable[..., GithubBudgetResponse] = urllib_transport,
        clock: Callable[[], float] = time.time,
        signer: Callable[..., bytes] = openssl_sign,
    ) -> MergeForge | AppRefusal:
        """Mint the installation token scoped to `repository` with exactly the merge grant."""
        minted = mint_installation_token(
            repository=repository,
            app_id=credential.app_id,
            private_key=credential.private_key,
            scope=MERGE_SCOPE,
            transport=transport,
            clock=clock,
            signer=signer,
        )
        if isinstance(minted, AppRefusal):
            return minted
        token, client = minted
        return cls(repository=repository, token=token, client=client)

    def request(self, *, method: str, path: str, value: object | None = None) -> tuple[int, object]:
        """One installation-authenticated call under `repos/<repository>/`."""
        return installation_request(
            client=self.client,
            repository=self.repository,
            token=self.token,
            method=method,
            path=path,
            value=value,
        )
