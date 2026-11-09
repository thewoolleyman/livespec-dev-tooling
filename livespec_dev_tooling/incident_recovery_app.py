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

import base64
import json
import os
import stat
import subprocess
import sys
import tempfile
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
from returns.io import IOFailure  # noqa: E402

from livespec_dev_tooling.budgeted_gh import github_api_url  # noqa: E402
from livespec_dev_tooling.incident_strict_json import (  # noqa: E402
    IncidentJsonRefusalError,
    strict_json,
)

__all__: list[str] = [
    "RECOVERY_APP_CREDENTIAL",
    "AppRefusal",
    "RecoveryAppCredential",
    "RecoveryForge",
]

RECOVERY_APP_CREDENTIAL = "recovery-app.json"
_OPENSSL = "/usr/bin/openssl"
_TIMEOUT_SECONDS = 10.0
_JWT_BACKDATE_SECONDS = 60
_JWT_LIFETIME_SECONDS = 540
_MAX_CREDENTIAL_BYTES = 16384
_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NOT_MODIFIED = 304
ForgeAccess = Literal["read", "write"]


def _scoped_grants(*, access: ForgeAccess) -> tuple[dict[str, str], dict[str, str]]:
    """The grants a minted token may report; any other read or write fails.

    GitHub reports every App installation token's grant with `metadata: read` beside
    what was requested, because no App can drop that permission (measured on the live
    recovery App for both accesses, 2026-11-07).
    """
    return {"contents": access}, {"contents": access, "metadata": "read"}


@dataclass(frozen=True, kw_only=True)
class AppRefusal:
    """A named reason the recovery App identity cannot act; it grants nothing."""

    code: str
    detail: str


def _protected_file(*, path: Path) -> bool:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
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
        pem = _pem(key=key) if isinstance(key, str) else None
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


def _pem(*, key: str) -> str | None:
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


def openssl_sign(*, message: bytes, private_key: str) -> bytes:
    """RS256 over `message` with the installed system crypto; empty bytes on refusal.

    The rewrapped key exists only inside a private temporary directory for the
    one signing call, the shape the fleet's installation-token minter uses.
    """
    with tempfile.TemporaryDirectory(prefix="livespec-recovery-app-") as name:
        key = Path(name) / "key.pem"
        descriptor = os.open(key, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            _ = stream.write(private_key)
        try:
            done = subprocess.run(  # noqa: S603 — fixed system crypto argv; no shell or caller input.
                [_OPENSSL, "dgst", "-sha256", "-sign", str(key), "-binary"],
                input=message,
                capture_output=True,
                check=False,
                env={"PATH": "/usr/bin:/bin", "HOME": name, "OPENSSL_CONF": "/dev/null"},
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return b""
    return done.stdout if done.returncode == 0 else b""


def _segment(*, value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


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
        client = GithubBudgetedClient(transport=transport, max_attempts=1)
        now = int(clock())
        claims = {
            "iat": now - _JWT_BACKDATE_SECONDS,
            "exp": now + _JWT_LIFETIME_SECONDS,
            "iss": credential.app_id,
        }
        unsigned = ".".join(
            _segment(value=json.dumps(part, separators=(",", ":")).encode())
            for part in ({"alg": "RS256", "typ": "JWT"}, claims)
        )
        signature = signer(message=unsigned.encode(), private_key=credential.private_key)
        if not signature:
            return AppRefusal(
                code="recovery-app-signing-unavailable",
                detail="the system crypto could not sign the recovery App JWT",
            )
        jwt = {"Authorization": f"Bearer {unsigned}.{_segment(value=signature)}"}
        status, found = _call(
            client=client, method="GET", resource=f"repos/{repository}/installation", headers=jwt
        )
        installation = (
            cast("dict[str, object]", found).get("id") if isinstance(found, dict) else None
        )
        if status != _HTTP_OK or type(installation) is not int:
            return AppRefusal(
                code="recovery-app-not-installed",
                detail=f"the recovery App installation does not cover {repository}",
            )
        status, minted = _call(
            client=client,
            method="POST",
            resource=f"app/installations/{installation}/access_tokens",
            headers=jwt,
            value={
                "repositories": [repository.split("/", 1)[1]],
                "permissions": {"contents": access},
            },
        )
        grant = cast("dict[str, object]", minted) if isinstance(minted, dict) else {}
        token, granted = grant.get("token"), grant.get("permissions")
        if (
            status != _HTTP_CREATED
            or not isinstance(token, str)
            or not token
            or granted not in _scoped_grants(access=access)
        ):
            return AppRefusal(
                code="recovery-app-token-refused",
                detail=f"no contents-{access} installation token was minted for {repository}",
            )
        return cls(repository=repository, token=token, client=client)

    def request(self, *, method: str, path: str, value: object | None = None) -> tuple[int, object]:
        """One installation-authenticated call under `repos/<repository>/`."""
        return _call(
            client=self.client,
            method=method,
            resource=f"repos/{self.repository}/{path}",
            headers={"Authorization": f"Bearer {self.token}"},
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
        return 0, None
    response = outcome.unwrap()
    # A revalidated read answers 304 with the retained body: to a caller that is the
    # resource as it stands, so it reads as an ordinary 200 (measured live, 2026-11-07).
    status = _HTTP_OK if response.status_code == _HTTP_NOT_MODIFIED else response.status_code
    return status, response.value
