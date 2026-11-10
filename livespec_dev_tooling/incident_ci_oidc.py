"""Authenticate supported issuer claims; the result grants no incident capability."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from livespec_dev_tooling._incident_ci_identity_json import identity_json, unbase64url
from livespec_dev_tooling.incident_ci_identity_policy import CiIdentityPolicy
from livespec_dev_tooling.incident_ci_jws import verify_ci_signature
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError

__all__: list[str] = ["OidcIdentity", "oidc_current", "verify_oidc"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb
_MAX_TOKEN = 16384
_JWS_PARTS = 3
_MIN_CHARACTER = 32
_CHARACTER_LIMIT = 127
_ISSUER = "https://token.actions.githubusercontent.com"
_SHA = re.compile(r"[0-9a-f]{40}")
_REF = re.compile(r"refs/pull/([1-9][0-9]{0,18})/merge")
_HEADER = frozenset({"alg", "typ", "kid", "x5t", "x5t#S256"})


@dataclass(frozen=True, kw_only=True)
class OidcIdentity:
    """Cryptographic invocation identity, before independent forge correlation."""

    repository: str
    repository_id: int
    repository_owner_id: int
    run_id: int
    run_attempt: int
    check_run_id: int
    pr_number: int
    merge_sha: str
    ref: str
    base_ref: str
    head_ref: str
    caller_workflow_ref: str
    caller_workflow_sha: str
    reusable_workflow_ref: str
    reusable_workflow_sha: str
    issued_at: int
    not_before: int
    expires_at: int


def oidc_current(*, identity: OidcIdentity, now: float) -> bool:
    """Require actual standard integer time claims, including after external reads."""
    return (
        identity.issued_at <= now
        and identity.not_before <= now < identity.expires_at
        and 0 < identity.issued_at < identity.expires_at
        and 0 < identity.not_before < identity.expires_at
    )


def verify_oidc(*, token: str, policy: CiIdentityPolicy, now: float) -> OidcIdentity | None:
    """Verify the original signing bytes with only independently pinned issuer keys."""
    try:
        if len(token) > _MAX_TOKEN:
            return None
        parts = token.split(".")
        if len(parts) != _JWS_PARTS:
            return None
        header = identity_json(raw=unbase64url(value=parts[0], limit=5462), limit=4096)
        claims = identity_json(raw=unbase64url(value=parts[1], limit=10923), limit=8192)
        signature = unbase64url(value=parts[2], limit=1366)
        if not _header_valid(header=header):
            return None
        identity = _identity(claims=claims, policy=policy)
        if identity is None or not oidc_current(identity=identity, now=now):
            return None
        return (
            identity
            if verify_ci_signature(
                policy=policy,
                kid=header["kid"],
                message=(parts[0] + "." + parts[1]).encode("ascii"),
                signature=signature,
            )
            else None
        )
    except (
        ValueError,
        IncidentJsonRefusalError,
        TypeError,
        KeyError,
        UnicodeError,
        RecursionError,
    ):
        return None


def _header_valid(*, header: dict[str, Any]) -> bool:
    return (
        set(header) <= _HEADER
        and {"alg", "typ", "kid"} <= set(header)
        and header["alg"] == "RS256"
        and header["typ"] == "JWT"
        and all(_text(value=value, limit=256) for value in header.values())
    )


def _number(*, value: Any) -> int | None:
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,18}", value):
        value = int(value)
    return value if type(value) is int and 0 < value < 2**63 else None


def _text(*, value: Any, limit: int = 1024) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and all(_MIN_CHARACTER <= ord(c) < _CHARACTER_LIMIT for c in value)
    )


def _identity(*, claims: dict[str, Any], policy: CiIdentityPolicy) -> OidcIdentity | None:
    if (
        claims.get("iss") != _ISSUER
        or claims.get("aud") != policy.audience
        or claims.get("sub") != policy.subject
        or claims.get("repository") != policy.repository
        or _number(value=claims.get("repository_id")) != policy.repository_id
        or _number(value=claims.get("repository_owner_id")) != policy.repository_owner_id
        or claims.get("event_name") != "pull_request"
    ):
        return None
    numbers = {
        key: _number(value=claims.get(key)) for key in ("run_id", "run_attempt", "check_run_id")
    }
    if any(value is None for value in numbers.values()):
        return None
    ref = claims.get("ref")
    match = _REF.fullmatch(ref) if isinstance(ref, str) else None
    if match is None or not all(type(claims.get(k)) is int for k in ("iat", "nbf", "exp")):
        return None
    ref = cast("str", ref)
    workflow = (claims.get("job_workflow_ref"), claims.get("job_workflow_sha"))
    caller = claims.get("workflow_ref")
    prefix = (
        re.escape(policy.repository)
        + r"/\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml@"
        + re.escape(ref)
    )
    if (
        workflow not in policy.workflows
        or not all(_text(value=claims.get(k)) for k in ("base_ref", "head_ref"))
        or not isinstance(caller, str)
        or re.fullmatch(prefix, caller) is None
        or not all(
            isinstance(claims.get(k), str) and _SHA.fullmatch(claims[k])
            for k in ("sha", "workflow_sha")
        )
    ):
        return None
    return OidcIdentity(
        repository=policy.repository,
        repository_id=policy.repository_id,
        repository_owner_id=policy.repository_owner_id,
        run_id=cast("int", numbers["run_id"]),
        run_attempt=cast("int", numbers["run_attempt"]),
        check_run_id=cast("int", numbers["check_run_id"]),
        pr_number=int(match.group(1)),
        merge_sha=claims["sha"],
        ref=ref,
        base_ref=claims["base_ref"],
        head_ref=claims["head_ref"],
        caller_workflow_ref=caller,
        caller_workflow_sha=claims["workflow_sha"],
        reusable_workflow_ref=workflow[0],
        reusable_workflow_sha=workflow[1],
        issued_at=claims["iat"],
        not_before=claims["nbf"],
        expires_at=claims["exp"],
    )
