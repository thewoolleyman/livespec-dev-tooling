"""Append independently observed historical outcomes to a retained CI job attachment."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from livespec_dev_tooling._incident_ci_attachment_store import (
    TERMINAL_STATUSES,
    attachment_tree,
    observation_receipt,
    observation_reply,
    valid_collection_id,
)
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling.incident_ci_job_history import observe_retained_job
from livespec_dev_tooling.incident_forge_reads import ForgeReads

if TYPE_CHECKING:
    from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

__all__: list[str] = ["CiJobCollection"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
_MAX_OBSERVATIONS = 256
_HEX = re.compile(r"[0-9a-f]{64}")
_FALSE = {
    "authorizes_current_effects": False,
    "ci_admission": False,
    "authorizes_merge": False,
    "normal_factory_proof": False,
}


@dataclass(frozen=True, kw_only=True)
class CiJobCollection:
    """Control collects; query only inspects. A locator grants no capability."""

    installation: ControllerInstallation

    def execute(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            if path == "/ci/jobs/collect" and set(payload) == {
                "repository",
                "attachment_id",
                "collection_id",
            }:
                return self._collect(payload=payload)
            if path == "/ci/jobs/inspect" and set(payload) == {"repository", "attachment_id"}:
                return self._inspect(payload=payload)
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return _refused(reason="CI job attachment state unavailable")
        return _refused(reason="unknown or malformed CI job operation")

    def _collect(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.installation
        attachment_id, collection_id = payload["attachment_id"], payload["collection_id"]
        if not _locator(value=attachment_id) or not valid_collection_id(value=collection_id):
            return _refused(reason="exact attachment and collection identity required")
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            tree = attachment_tree(record=load_record(path=path))
        previous = _recovered(tree=tree, attachment_id=attachment_id, collection_id=collection_id)
        entry = tree["attachments"].get(attachment_id)
        if previous is not None or entry is None:
            return previous or _refused(reason="retained CI job attachment unavailable")
        # Forge I/O runs outside the effect lock so recovery and other writers progress.
        status, facts = observe_retained_job(
            binding=entry["binding"], read=ForgeReads.installed(installation=settings)
        )
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            record = load_record(path=path)
            tree = attachment_tree(record=record)
            previous = _recovered(
                tree=tree, attachment_id=attachment_id, collection_id=collection_id
            )
            if previous is not None:
                return previous
            current = tree["attachments"].get(attachment_id)
            if current is None or current["binding_digest"] != entry["binding_digest"]:
                return _refused(reason="retained CI job attachment changed")
            rows: list[dict[str, Any]] = current["observations"]
            if len(rows) >= _MAX_OBSERVATIONS:
                return _refused(reason="CI observation history full; nothing was pruned")
            observation = _observation(
                rows=rows, collection_id=collection_id, status=status, facts=facts
            )
            observation["receipt"] = observation_receipt(
                attachment_id=attachment_id,
                digest=current["binding_digest"],
                observation=observation,
            )
            rows.append(observation)
            tree["collections"][collection_id] = {
                "attachment_id": attachment_id,
                "sequence": observation["sequence"],
            }
            record["ci_job_attachments"] = tree
            save_record(path=path, record=record)
        return observation_reply(attachment_id=attachment_id, observation=observation)

    def _inspect(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.installation
        if not _locator(value=payload["attachment_id"]):
            return _refused(reason="exact attachment identity required")
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            tree = attachment_tree(record=load_record(path=path))
        entry = tree["attachments"].get(payload["attachment_id"])
        if entry is None:
            return _refused(reason="retained CI job attachment unavailable")
        return {
            "schema": 1,
            "status": "inspected",
            "attachment": entry["receipt"],
            "attached_at": entry["attached_at"],
            "observations": entry["observations"],
            "observation_count": len(entry["observations"]),
            **_FALSE,
        }


def _observation(
    *, rows: list[dict[str, Any]], collection_id: str, status: str, facts: dict[str, Any]
) -> dict[str, Any]:
    """Contradictory terminal evidence is explicit conflict; nothing earlier is replaced."""
    earlier = {row["facts"]["snapshot_status"] for row in rows} & TERMINAL_STATUSES
    if status in TERMINAL_STATUSES and earlier - {status}:
        status = "conflict"
        facts = facts | {"reason": "contradicts earlier terminal observation"}
    return {
        "sequence": len(rows) + 1,
        "collection_id": collection_id,
        "observed_at": int(time.time()),
        "status": status,
        "facts": facts,
    }


def _recovered(
    *, tree: dict[str, Any], attachment_id: str, collection_id: str
) -> dict[str, Any] | None:
    stored = tree["collections"].get(collection_id)
    if stored is None:
        return None
    if stored["attachment_id"] != attachment_id:
        return _refused(reason="collection identity conflicts with another attachment")
    rows = tree["attachments"][attachment_id]["observations"]
    return observation_reply(attachment_id=attachment_id, observation=rows[stored["sequence"] - 1])


def _locator(*, value: object) -> bool:
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _refused(*, reason: str) -> dict[str, Any]:
    return {"schema": 1, "status": "refused", "reason": reason}
