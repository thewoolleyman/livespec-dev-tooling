"""The dedicated incident recovery GitHub App identity and its scoped forge access.

The recovery principal acts on the forge as ONE identity: a GitHub App provisioned
only for incident recovery, distinct from the fleet factory and publishing bot
(`GITHUB_APP_ID` / `GITHUB_PRIVATE_KEY`). Master's ruleset bypass names only this
App, so its installation token is the narrow capability that lets an exact
incident inverse reach master without waiting for checks.

THE CREDENTIAL IS A PROJECTED FILE, NEVER A REPOSITORY VALUE OR AN AMBIENT
VARIABLE. The incident_observer role writes `recovery-app.json` beside the
protected controller configuration at apply, under `no_log`, from the
`LIVESPEC_RECOVERY_APP_ID` and `LIVESPEC_RECOVERY_APP_PRIVATE_KEY` values the
credential wrapper projects on the control node. The canonical reader never holds
the key. Only the principal process mints a `contents: write` token; the observer
and the operator entrance mint `contents: read` for their forge reads
(`incident_forge_reads`). A missing, unprotected or malformed file is a NAMED
refusal and every caller fails closed; nothing falls back to another identity.

Every request travels through the budgeted client with the fixed API origin the
sanctioned boundary owns (`budgeted_gh.github_api_url`). The installation token
is minted per operation or process, scoped to the one observed repository, and
never written to a reply, a record or a log.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_runtime_budget.github_budget import (  # noqa: E402 — vendor-path-aware import.
    GithubBudgetedClient,
    GithubBudgetRequest,
    GithubBudgetResponse,
)

from livespec_dev_tooling._incident_app_installation import (  # noqa: E402
    AppRefusal,
    InstallationScope,
    installation_request,
    mint_installation_token,
)
from livespec_dev_tooling._incident_recovery_signing import openssl_sign  # noqa: E402
from livespec_dev_tooling.budgeted_gh import github_api_url  # noqa: E402
from livespec_dev_tooling.incident_protected_path import protected_path  # noqa: E402
from livespec_dev_tooling.incident_strict_json import (  # noqa: E402
    IncidentJsonRefusalError,
    strict_json,
)

__all__: list[str] = [
    "RECOVERY_APP_CREDENTIAL",
    "AppRefusal",
    "RecoveryAppCredential",
    "RecoveryForge",
    "pem_private_key",
    "recovery_scope",
]

RECOVERY_APP_CREDENTIAL = "recovery-app.json"
_TIMEOUT_SECONDS = 10.0
_MAX_CREDENTIAL_BYTES = 16384
ForgeAccess = Literal["read", "write"]


def recovery_scope(*, access: ForgeAccess) -> InstallationScope:
    """The recovery App's grant: contents `access` and nothing wider.

    GitHub reports every App installation token's grant with `metadata: read` beside
    what was requested, because no App can drop that permission (measured on the live
    recovery App for both accesses, 2026-11-07).
    """
    return InstallationScope(
        identity="recovery App",
        code_prefix="recovery-app",
        grant_label=f"contents-{access}",
        permissions={"contents": access},
        accepted=({"contents": access}, {"contents": access, "metadata": "read"}),
    )


def _protected_file(*, path: Path) -> bool:
    if not protected_path(path=path) or path.is_symlink() or not path.is_file():
        return False
    info = path.stat()
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid in {0, os.geteuid()}
        and not stat.S_IMODE(info.st_mode) & 0o077
    )


@dataclass(frozen=True, kw_only=True)
class RecoveryAppCredential:
    """The recovery App's id and private key, read from the projected file only."""

    app_id: str
    private_key: str = field(repr=False)

    @classmethod
    def load(cls, *, path: Path) -> RecoveryAppCredential | AppRefusal:
        """Read `{"app_id", "private_key"}` from a protected 0600 file, or refuse by name."""
        try:
            if not path.exists():
                return AppRefusal(
                    code="recovery-app-credential-absent",
                    detail=f"no projected recovery App credential at {path}",
                )
            if not _protected_file(path=path):
                return AppRefusal(
                    code="recovery-app-credential-unprotected",
                    detail=f"{path} must be a regular 0600 file owned by this account",
                )
            data: object = strict_json(
                text=path.read_bytes()[: _MAX_CREDENTIAL_BYTES + 1], limit=None
            )
        except (OSError, ValueError, IncidentJsonRefusalError):
            data = None
        record = cast("dict[str, object]", data) if isinstance(data, dict) else {}
        app_id, key = record.get("app_id"), record.get("private_key")
        pem = pem_private_key(key=key) if isinstance(key, str) else None
        if (
            set(record) != {"app_id", "private_key"}
            or not isinstance(app_id, str)
            or not app_id.isdigit()
            or pem is None
        ):
            return AppRefusal(
                code="recovery-app-credential-malformed",
                detail=f"{path} must hold exactly a numeric app_id and a PEM private_key",
            )
        return cls(app_id=app_id, private_key=pem)


def pem_private_key(*, key: str) -> str | None:
    """Rewrap a (possibly single-line) projected PEM private key, or None if it is not one.

    The wrapper projects the key as ONE line (`.ai/fleet-and-secrets.md`), and the
    system crypto parses a PEM only when its guards sit on their own lines.
    """
    begin = key.find("-----BEGIN ")
    label_end = key.find("-----", begin + len("-----BEGIN ")) if begin >= 0 else -1
    label = key[begin + len("-----BEGIN ") : label_end] if label_end >= 0 else ""
    end = key.find(f"-----END {label}-----", label_end) if label.endswith("PRIVATE KEY") else -1
    body = "".join(key[label_end + len("-----") : end].split()) if end >= 0 else ""
    if not body:
        return None
    wrapped = "\n".join(body[index : index + 64] for index in range(0, len(body), 64))
    return f"-----BEGIN {label}-----\n{wrapped}\n-----END {label}-----\n"


def urllib_transport(*, request: GithubBudgetRequest) -> GithubBudgetResponse:
    """POST/GET one REST resource; status 0 means no answer was observed."""
    body = None if request.value is None else json.dumps(request.value).encode()
    outgoing = urllib.request.Request(  # noqa: S310 — fixed https API origin, never configured.
        github_api_url(path=request.resource),
        data=body,
        method=request.method,
        headers={
            **request.headers,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    status, headers, raw = 0, {}, b""
    try:
        with urllib.request.urlopen(outgoing, timeout=_TIMEOUT_SECONDS) as answer:  # noqa: S310
            status, headers, raw = answer.status, dict(answer.headers), answer.read()
    except urllib.error.HTTPError as refused:
        status, headers, raw = refused.code, dict(refused.headers), refused.read()
    except (urllib.error.URLError, OSError, ValueError):
        pass
    try:
        value: object = strict_json(text=raw, limit=None) if raw else None
    except (ValueError, IncidentJsonRefusalError):
        value = None
    return GithubBudgetResponse(
        status_code=status, headers=headers, value=value, primary_budget_spent=1
    )


@dataclass(frozen=True, kw_only=True)
class RecoveryForge:
    """One process's REST access as the recovery App installation on one repository."""

    repository: str
    token: str = field(repr=False)
    client: GithubBudgetedClient

    @classmethod
    def connect(
        cls,
        *,
        repository: str,
        credential: RecoveryAppCredential,
        transport: Callable[..., GithubBudgetResponse] = urllib_transport,
        clock: Callable[[], float] = time.time,
        signer: Callable[..., bytes] = openssl_sign,
        access: ForgeAccess = "write",
    ) -> RecoveryForge | AppRefusal:
        """Mint the installation token scoped to `repository` with exactly `access` on contents."""
        minted = mint_installation_token(
            repository=repository,
            app_id=credential.app_id,
            private_key=credential.private_key,
            scope=recovery_scope(access=access),
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
