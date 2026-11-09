"""Read-only release and pin dispatch screen over the observer's retained incident record.

`SPECIFICATION/contracts.md` section "Expedited incident execution": recovery
MUST fence queued stale adoption. A release or pin dispatch entrance asks this
query route, with the query credential, before its effect. The screen reads
only the controller's own record and its independent reference clone; it never
writes, never calls the canonical reader and grants no adoption authority.

A release is refused by name, `incident-release-recovery-retained`, when its
source commit or tag is attributed to an incident registration that a retained
recovery action or regression fences, or when an unfinished recovery action's
landed head is an ancestor of the release source. When that ancestry cannot be
decided the release is refused as `incident-release-source-unverifiable`. A
record with no retained action answers `clear`, so a release with no incident
record proceeds exactly as before.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_dev_tooling._incident_inverse_git import IsolatedGit
from livespec_dev_tooling._incident_observer_store import load_record, repository_lock
from livespec_dev_tooling._incident_release_types import _mapping, _object
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

__all__: list[str] = ["RELEASE_SCREEN_PATH", "ReleaseScreen"]

RELEASE_SCREEN_PATH = "/release/screen"
_RETAINED = "incident-release-recovery-retained"
_UNVERIFIABLE = "incident-release-source-unverifiable"
_FIELDS = frozenset({"repository", "source_sha", "tag"})
_SHA = re.compile(r"[0-9a-f]{40}")
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
_ATTRIBUTED = ("release_attribution", "release_adoption_intents")
_FENCES = ("actions", "release_regressions")
_DETAIL = {
    _RETAINED: "this release source is fenced by the retained recovery of incident",
    _UNVERIFIABLE: "the reference clone cannot decide whether this source contains incident",
}


@dataclass(frozen=True, kw_only=True)
class ReleaseScreen:
    """Answer clear or a named refusal for one exact release source and tag."""

    installation: ControllerInstallation

    def execute(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Screen one release against the retained record, without mutation."""
        settings = self.installation
        if (
            path != RELEASE_SCREEN_PATH
            or frozenset(payload) != _FIELDS
            or payload["repository"] != settings.repository
            or not isinstance(payload["source_sha"], str)
            or _SHA.fullmatch(payload["source_sha"]) is None
            or not isinstance(payload["tag"], str)
            or _TAG.fullmatch(payload["tag"]) is None
        ):
            return {
                "schema": 1,
                "status": "refused",
                "reason": "invalid exact release screen query",
            }
        with repository_lock(
            directory=settings.state, repository=settings.repository
        ) as record_path:
            record = load_record(path=record_path)
        refusal = _attributed_refusal(record=record, payload=payload) or _pending_refusal(
            record=record, root=settings.repo, source=payload["source_sha"]
        )
        if refusal is not None:
            return {"schema": 1, "status": "refused", **refusal, "query": payload}
        return {"schema": 1, "status": "clear", "query": payload}


def _attributed_refusal(
    *, record: dict[str, object], payload: dict[str, Any]
) -> dict[str, str] | None:
    fenced = [
        _object(value=entry).get("registration")
        for field in _FENCES
        for entry in _mapping(record=record, field=field).values()
    ]
    for field in _ATTRIBUTED:
        for raw in _mapping(record=record, field=field).values():
            entry = _object(value=raw)
            attribution = _object(value=entry.get("attribution"))
            if entry.get("registration") in fenced and (
                attribution.get("source_sha") == payload["source_sha"]
                or attribution.get("release_tag") == payload["tag"]
            ):
                return _named(code=_RETAINED, registration=entry.get("registration"))
    return None


def _pending_refusal(
    *, record: dict[str, object], root: Path, source: str
) -> dict[str, str] | None:
    for raw in _mapping(record=record, field="actions").values():
        action = _object(value=raw)
        if action.get("status") == "completed":
            continue
        registration = _object(value=action.get("registration"))
        contained = _contains(root=root, ancestor=registration.get("head_sha"), descendant=source)
        if contained is None:
            return _named(code=_UNVERIFIABLE, registration=registration)
        if contained:
            return _named(code=_RETAINED, registration=registration)
    return None


def _contains(*, root: Path, ancestor: object, descendant: str) -> bool | None:
    """Whether `ancestor` is reachable from `descendant`; None when undecidable."""
    if not isinstance(ancestor, str) or _SHA.fullmatch(ancestor) is None:
        return None
    try:
        with IsolatedGit.view(root=root) as (administration, objects):
            base = IsolatedGit.run(
                root=root,
                args=("merge-base", ancestor, descendant),
                administration=administration,
                objects=objects,
            )
    except (OSError, subprocess.SubprocessError):
        return None
    return base.decode().strip() == ancestor


def _named(*, code: str, registration: object) -> dict[str, str]:
    identity = _object(value=registration)
    item = str(identity.get("incident_item_id", ""))
    return {"reason": code, "incident_item_id": item, "detail": f"{code}: {_DETAIL[code]} {item}"}
