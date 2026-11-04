"""Read-only, freshly fenced incident queries from the independent controller."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    repository_lock,
)
from livespec_dev_tooling._incident_observer_types import ObserverArm, ObserverArmQuery
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_observer_authority import CurrentAuthorityReader

__all__: list[str] = ["ObserverQuery"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wanebl
_QUERY_FIELDS = frozenset(
    {"repository", "arm_id", "pr_number", "base_sha", "head_sha", "receipt_digest"}
)


@dataclass(frozen=True, kw_only=True)
class ObserverQuery:
    """Inspect the protected arm without granting mutation or recovery authority."""

    installation: ControllerInstallation

    def execute(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.installation
        if (
            path not in {"/admitted", "/current"}
            or not _valid_query(payload=payload)
            or payload["repository"] != settings.repository
        ):
            return _refused(reason="invalid exact protected query")
        query = ObserverArmQuery(**payload)
        arm = self._snapshot(query=query)
        if arm is None:
            return _refused(reason="exact unbound pre-merge arm unavailable")
        if path == "/current":
            reader = CurrentAuthorityReader(
                command=settings.reader,
                repo=settings.repo,
                release=settings.reader_release,
                installed_reader_approved=lambda release, command: (release, command)
                == (settings.reader_release, settings.reader),
            )
            # Never hold the effect lock while a tenant/credential read can block.
            if not reader(arm) or self._snapshot(query=query) != arm:
                return _refused(reason="canonical authority stale, unavailable or arm changed")
        return {
            "schema": 1,
            "status": "current" if path == "/current" else "admitted",
            "query": asdict(query),
        }

    def _snapshot(self, *, query: ObserverArmQuery) -> ObserverArm | None:
        settings = self.installation
        with repository_lock(
            directory=settings.state, repository=settings.repository
        ) as record_path:
            record = load_record(path=record_path)
            arm = read_observer_arm(record=record)
            if (
                arm is None
                or record.get("observer_arm_id") != query.arm_id
                or record.get("observer_arm_bound")
                or record.get("observer_arm_invalidated") is not None
                or (arm.repository, arm.pr_number, arm.base_sha, arm.head_sha)
                != (query.repository, query.pr_number, query.base_sha, query.head_sha)
                or hashlib.sha256(arm.authority_receipt).hexdigest() != query.receipt_digest
            ):
                return None
            return arm


def _valid_query(*, payload: dict[str, Any]) -> bool:
    return (
        frozenset(payload) == _QUERY_FIELDS
        and type(payload["pr_number"]) is int
        and payload["pr_number"] > 0
        and all(isinstance(payload[name], str) for name in _QUERY_FIELDS - {"pr_number"})
        and all(
            re.fullmatch(r"[0-9a-f]{64}", payload[name]) is not None
            for name in ("arm_id", "receipt_digest")
        )
        and all(
            re.fullmatch(r"[0-9a-f]{40}", payload[name]) is not None
            for name in ("base_sha", "head_sha")
        )
    )


def _refused(*, reason: str) -> dict[str, Any]:
    return {"schema": 1, "status": "refused", "reason": reason}
