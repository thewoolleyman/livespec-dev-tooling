"""One GitHub App installation token, minted with exactly the grant its identity allows.

Each incident App identity (the recovery App in `incident_recovery_app`, the
incident-merge App in `incident_merge_app`) signs its own JWT, finds its own
installation on the one observed repository, and mints a token scoped to that
repository. An `InstallationScope` names the identity in every refusal and lists the
only grants the minted token may report; a token reporting any other read, any
other write, or a missing permission is refused by name and never used.

Every request travels through the budgeted client the caller's transport backs;
the token is never written to a reply, a record or a log.
"""

from __future__ import annotations

import base64
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_runtime_budget.github_budget import (  # noqa: E402 — vendor-path-aware import.
    GithubBudgetedClient,
    GithubBudgetResponse,
)
from returns.io import IOFailure  # noqa: E402

__all__: list[str] = [
    "AppRefusal",
    "InstallationScope",
    "installation_request",
    "mint_installation_token",
]

_JWT_BACKDATE_SECONDS = 60
_JWT_LIFETIME_SECONDS = 540
_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NOT_MODIFIED = 304


@dataclass(frozen=True, kw_only=True)
class AppRefusal:
    """A named reason an incident App identity cannot act; it grants nothing."""

    code: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class InstallationScope:
    """One App identity's refusal names and the exact grants its installation token may hold.

    `permissions` is what a mint requests; `accepted` lists every grant the minted
    token may report, and any other read, write or missing permission is refused.
    """

    identity: str
    code_prefix: str
    grant_label: str
    permissions: dict[str, str]
    accepted: tuple[dict[str, str], ...]


class _RecordingTransport:
    """The injected transport, remembering the last response it answered.

    The budgeted client turns a 403 that carries rate-limit headers into a failure
    that holds no status and no body. The merge principal must name the forge's own
    status and message, so the response is kept here and `_call` reads it back.
    """

    def __init__(self, *, transport: Callable[..., GithubBudgetResponse]) -> None:
        self._transport = transport
        self.last: GithubBudgetResponse | None = None

    def __call__(self, *, request: object) -> GithubBudgetResponse:
        self.last = self._transport(request=request)
        return self.last


def _segment(*, value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def mint_installation_token(  # noqa: PLR0913 — the App identity, its scope and the three injected collaborators.
    *,
    repository: str,
    app_id: str,
    private_key: str,
    scope: InstallationScope,
    transport: Callable[..., GithubBudgetResponse],
    clock: Callable[[], float],
    signer: Callable[..., bytes],
) -> tuple[str, GithubBudgetedClient] | AppRefusal:
    """Mint one installation token on `repository` holding exactly a grant `scope` accepts."""
    client = GithubBudgetedClient(
        transport=_RecordingTransport(transport=transport), max_attempts=1
    )
    now = int(clock())
    claims = {
        "iat": now - _JWT_BACKDATE_SECONDS,
        "exp": now + _JWT_LIFETIME_SECONDS,
        "iss": app_id,
    }
    unsigned = ".".join(
        _segment(value=json.dumps(part, separators=(",", ":")).encode())
        for part in ({"alg": "RS256", "typ": "JWT"}, claims)
    )
    signature = signer(message=unsigned.encode(), private_key=private_key)
    if not signature:
        return AppRefusal(
            code=f"{scope.code_prefix}-signing-unavailable",
            detail=f"the system crypto could not sign the {scope.identity} JWT",
        )
    jwt = {"Authorization": f"Bearer {unsigned}.{_segment(value=signature)}"}
    status, found = _call(
        client=client, method="GET", resource=f"repos/{repository}/installation", headers=jwt
    )
    installation = cast("dict[str, object]", found).get("id") if isinstance(found, dict) else None
    if status != _HTTP_OK or type(installation) is not int:
        return AppRefusal(
            code=f"{scope.code_prefix}-not-installed",
            detail=f"the {scope.identity} installation does not cover {repository}",
        )
    status, minted = _call(
        client=client,
        method="POST",
        resource=f"app/installations/{installation}/access_tokens",
        headers=jwt,
        value={"repositories": [repository.split("/", 1)[1]], "permissions": scope.permissions},
    )
    grant = cast("dict[str, object]", minted) if isinstance(minted, dict) else {}
    token, granted = grant.get("token"), grant.get("permissions")
    if (
        status != _HTTP_CREATED
        or not isinstance(token, str)
        or not token
        or granted not in scope.accepted
    ):
        return AppRefusal(
            code=f"{scope.code_prefix}-token-refused",
            detail=f"no {scope.grant_label} installation token was minted for {repository}",
        )
    return token, client


def installation_request(
    *,
    client: GithubBudgetedClient,
    repository: str,
    token: str,
    method: str,
    path: str,
    value: object | None = None,
) -> tuple[int, object]:
    """One installation-authenticated call under `repos/<repository>/`."""
    return _call(
        client=client,
        method=method,
        resource=f"repos/{repository}/{path}",
        headers={"Authorization": f"Bearer {token}"},
        value=value,
    )


def _call(
    *,
    client: GithubBudgetedClient,
    method: str,
    resource: str,
    headers: dict[str, str],
    value: object | None = None,
) -> tuple[int, object]:
    outcome = client.request(method=method, resource=resource, headers=headers, value=value)
    if isinstance(outcome, IOFailure):
        # The client failed the call; the forge's own answer, when one was recorded, is
        # the status and message the caller must see. With none, 0 names the cause.
        last = getattr(client.transport, "last", None)
        if last is not None:
            return last.status_code, last.value
        return 0, {"message": str(outcome.failure())}
    response = outcome.unwrap()
    # A revalidated read answers 304 with the retained body: to a caller that is the
    # resource as it stands, so it reads as an ordinary 200 (measured live, 2026-11-07).
    status = _HTTP_OK if response.status_code == _HTTP_NOT_MODIFIED else response.status_code
    return status, response.value
