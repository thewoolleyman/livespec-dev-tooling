"""Read optional CI identity trust without weakening mandatory recovery installation."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling._incident_ci_identity_json import identity_json, unbase64url

__all__: list[str] = [
    "CiIdentityPolicy",
    "identity_policy_intact",
    "load_identity_policy",
    "protected_identity_path",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb
_MAX_POLICY = 65536
_MAX_WORKFLOWS = 32
_MAX_KEYS = 16
_MIN_RSA_BITS = 2048
_MAX_RSA_BITS = 8192
_MIN_EXPONENT = 3
_MIN_CHARACTER = 32
_CHARACTER_LIMIT = 127
_FIELDS = frozenset(
    {
        "schema",
        "audience",
        "subject",
        "repository",
        "repository_id",
        "repository_owner_id",
        "approved_reusable_workflows",
        "issuer_keys",
        "crypto",
    }
)
_REPOSITORY = r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+"
_WORKFLOW = re.compile(_REPOSITORY + r"/\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml@([0-9a-f]{40})")


@dataclass(frozen=True, kw_only=True)
class CiIdentityPolicy:
    """A manifest-digest-bound policy; requests never construct this installation field."""

    path: Path
    digest: str
    repository: str
    audience: str
    subject: str
    repository_id: int
    repository_owner_id: int
    workflows: tuple[tuple[str, str], ...]
    keys: tuple[tuple[str, str, str], ...]
    crypto_path: Path
    crypto_sha256: str


def protected_identity_path(*, path: Path) -> bool:
    """Validate ownership of lexical links, resolved targets and every ancestor."""
    try:
        if not path.is_absolute() or not path.exists():
            return False
        resolved = path.resolve(strict=True)
        for entry in (path, *path.parents, resolved, *resolved.parents):
            link, info = entry.lstat(), entry.stat()
            sticky = entry.is_dir() and info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if (
                link.st_uid not in {0, os.geteuid()}
                or info.st_uid not in {0, os.geteuid()}
                or (info.st_mode & 0o022 and not sticky)
            ):
                return False
    except (OSError, RuntimeError):
        return False
    else:
        return True


def identity_policy_intact(*, policy: CiIdentityPolicy) -> bool:
    """Recheck optional data and crypto without adding either to mandatory files."""
    try:
        return (
            protected_identity_path(path=policy.path)
            and policy.path.is_file()
            and not stat.S_IMODE(policy.path.stat().st_mode) & 0o077
            and policy.path.stat().st_size <= _MAX_POLICY
            and hashlib.sha256(policy.path.read_bytes()).hexdigest() == policy.digest
            and protected_identity_path(path=policy.crypto_path)
            and policy.crypto_path.is_file()
            and os.access(policy.crypto_path, os.X_OK)
            and hashlib.sha256(policy.crypto_path.read_bytes()).hexdigest() == policy.crypto_sha256
        )
    except OSError:
        return False


def load_identity_policy(*, descriptor: Any, repository: str) -> CiIdentityPolicy | None:
    """Return unavailable for every invalid OPTIONAL field; recovery still loads."""
    descriptor = _object(value=descriptor)
    try:
        if (
            set(descriptor) != {"path", "sha256"}
            or not isinstance(descriptor["path"], str)
            or not _digest(value=descriptor["sha256"])
        ):
            return None
        path = Path(descriptor["path"])
        if (
            not protected_identity_path(path=path)
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) & 0o077
        ):
            return None
        with path.open("rb") as stream:
            raw = stream.read(_MAX_POLICY + 1)
        if hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            return None
        data = identity_json(raw=raw)
        if not _valid_data(data=data, repository=repository):
            return None
        workflows = tuple((v["ref"], v["sha"]) for v in data["approved_reusable_workflows"])
        keys = tuple((v["kid"], v["n"], v["e"]) for v in data["issuer_keys"])
        policy = CiIdentityPolicy(
            path=path,
            digest=descriptor["sha256"],
            repository=repository,
            audience=data["audience"],
            subject=data["subject"],
            repository_id=data["repository_id"],
            repository_owner_id=data["repository_owner_id"],
            workflows=workflows,
            keys=keys,
            crypto_path=Path(data["crypto"]["path"]),
            crypto_sha256=data["crypto"]["sha256"],
        )
        return policy if identity_policy_intact(policy=policy) else None
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return None


def _valid_data(*, data: dict[str, Any], repository: str) -> bool:
    return (
        frozenset(data) == _FIELDS
        and type(data["schema"]) is int
        and data["schema"] == 1
        and data["repository"] == repository
        and re.fullmatch(_REPOSITORY, repository) is not None
        and repository.rsplit("/", maxsplit=1)[-1] not in {".", ".."}
        and all(
            type(data[k]) is int and 0 < data[k] < 2**63
            for k in ("repository_id", "repository_owner_id")
        )
        and all(_text(value=data[k]) for k in ("audience", "subject"))
        and _workflows(value=data["approved_reusable_workflows"])
        and _keys(value=data["issuer_keys"])
        and _crypto(value=data["crypto"])
    )


def _workflows(*, value: Any) -> bool:
    if not isinstance(value, list) or not 0 < len(cast("list[Any]", value)) <= _MAX_WORKFLOWS:
        return False
    found: set[str] = set()
    for raw in cast("list[Any]", value):
        row = _object(value=raw)
        if set(row) != {"ref", "sha"}:
            return False
        match = _WORKFLOW.fullmatch(row["ref"]) if isinstance(row["ref"], str) else None
        if match is None or row["sha"] != match.group(1) or row["ref"] in found:
            return False
        found.add(row["ref"])
    return True


def _keys(*, value: Any) -> bool:
    if not isinstance(value, list) or not 0 < len(cast("list[Any]", value)) <= _MAX_KEYS:
        return False
    found: set[str] = set()
    for raw in cast("list[Any]", value):
        row = _object(value=raw)
        if set(row) != {"kid", "n", "e"}:
            return False
        if not _text(value=row["kid"], bound=256) or row["kid"] in found:
            return False
        modulus = unbase64url(value=row["n"], limit=1366)
        exponent = unbase64url(value=row["e"], limit=8)
        n, e = int.from_bytes(modulus, "big"), int.from_bytes(exponent, "big")
        if (
            not modulus
            or modulus[0] == 0
            or not exponent
            or exponent[0] == 0
            or not _MIN_RSA_BITS <= n.bit_length() <= _MAX_RSA_BITS
            or n % 2 == 0
            or not _MIN_EXPONENT <= e < 2**32
            or e % 2 == 0
        ):
            return False
        found.add(row["kid"])
    return True


def _digest(*, value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _text(*, value: Any, bound: int = 1024) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= bound
        and all(_MIN_CHARACTER <= ord(v) < _CHARACTER_LIMIT for v in value)
    )


def _object(*, value: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _crypto(*, value: Any) -> bool:
    row = _object(value=value)
    return (
        set(row) == {"path", "sha256"}
        and isinstance(row["path"], str)
        and Path(row["path"]).is_absolute()
        and Path(row["path"]).name == "openssl"
        and _digest(value=row["sha256"])
    )
