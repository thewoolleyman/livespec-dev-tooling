"""The incident-merge runner's credential file: root-owned, mode 0600, or a named refusal.

The incident_observer role projects the merge App's credential into one JSON file,
`{"app_id", "private_key"}`, root-owned at mode 0600 so the observer process and its reader
(which run as the observer account) can never hold the merge principal's key. The runner is
the only reader. Each way the file can be unfit is a separate named condition, so an
operator reads which one failed instead of a generic refusal; nothing falls back to the
environment or to another identity.
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_app_installation import AppRefusal
from livespec_dev_tooling.incident_merge_app import (
    MERGE_APP_ID_ENV,
    MERGE_APP_KEY_ENV,
    MergeAppCredential,
)
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["DEFAULT_CREDENTIAL_PATH", "load_merge_credential"]

DEFAULT_CREDENTIAL_PATH = Path("/etc/livespec-incident/merge-app.json")
_MAX_BYTES = 16384
_MODE = 0o600
_PREFIX = "incident-merge-runner-credential"


def _refusal(*, code: str, detail: str) -> AppRefusal:
    return AppRefusal(code=f"{_PREFIX}-{code}", detail=detail)


def _protection_refusal(*, path: Path, owner_uid: int) -> AppRefusal | None:
    """Name the first way `path` is not a root-owned 0600 regular file, or None."""
    if path.is_symlink() or not path.is_file():
        return _refusal(code="unprotected", detail=f"{path} is not a regular file")
    info = path.lstat()
    if info.st_uid != owner_uid:
        return _refusal(
            code="unprotected", detail=f"{path} is owned by uid {info.st_uid}, not uid {owner_uid}"
        )
    if stat.S_IMODE(info.st_mode) != _MODE:
        return _refusal(
            code="unprotected", detail=f"{path} has mode {stat.S_IMODE(info.st_mode):04o}, not 0600"
        )
    return None


def load_merge_credential(
    *,
    path: Path,
    owner_uid: int,
    merge_integration_id: int | None,
    recovery_integration_id: int | None,
) -> MergeAppCredential | AppRefusal:
    """Read the projected credential, refusing by name before any byte of it is trusted."""
    if not path.exists() and not path.is_symlink():
        return _refusal(code="absent", detail=f"no projected incident-merge credential at {path}")
    unprotected = _protection_refusal(path=path, owner_uid=owner_uid)
    if unprotected is not None:
        return unprotected
    try:
        data: object = strict_json(text=path.read_bytes()[: _MAX_BYTES + 1], limit=None)
    except (OSError, ValueError, IncidentJsonRefusalError):
        data = None
    record = cast("dict[str, object]", data) if isinstance(data, dict) else {}
    app_id, key = record.get("app_id"), record.get("private_key")
    if set(record) != {"app_id", "private_key"} or not isinstance(app_id, str):
        return _refusal(code="malformed", detail=f"{path} must hold exactly app_id and private_key")
    if not isinstance(key, str):
        return _refusal(code="malformed", detail=f"{path} must hold exactly app_id and private_key")
    return MergeAppCredential.from_env(
        environ={MERGE_APP_ID_ENV: app_id, MERGE_APP_KEY_ENV: key},
        merge_integration_id=merge_integration_id,
        recovery_integration_id=recovery_integration_id,
    )
