"""Read-only, freshly fenced incident queries from the independent controller.

``/ordinary-action`` is the master-health reconciler's ownership question. The
reconciler runs on a GitHub-hosted runner, far from the controller's protected
state directory, so it asks over the authenticated query route immediately
before each rerun, classification or revert step it would take.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any, cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    repository_lock,
)
from livespec_dev_tooling._incident_observer_types import ObserverArm, ObserverArmQuery
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_observer import route_reconciler_window
from livespec_dev_tooling.incident_observer_authority import CurrentAuthorityReader

__all__: list[str] = [
    "MAX_WINDOW_SHAS",
    "ORDINARY_ACTION_PATH",
    "RECONCILER_ACTIONS",
    "ObserverQuery",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wanebl
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
_QUERY_FIELDS = frozenset(
    {"repository", "arm_id", "pr_number", "base_sha", "head_sha", "receipt_digest"}
)
ORDINARY_ACTION_PATH = "/ordinary-action"
_ORDINARY_ACTION_FIELDS = frozenset({"repository", "action", "window_shas"})
# Every master-health reconciler step that touches the repository. `none` takes
# no action and is never asked. The decision core's STEP_* constants are the
# source; a test keeps this set equal to them.
RECONCILER_ACTIONS = frozenset(
    {"rerun-failed-jobs", "open-revert", "release-revert", "close-revert", "needs-attention"}
)
# The reconciler records a 30-commit window by default; this bounds the reply
# and the lock-held set lookup well above that, never the episode itself.
MAX_WINDOW_SHAS = 128


@dataclass(frozen=True, kw_only=True)
class ObserverQuery:
    """Inspect the protected arm without granting mutation or recovery authority."""

    installation: ControllerInstallation

    def execute(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.installation
        if path == ORDINARY_ACTION_PATH:
            return self._ordinary_action(payload=payload)
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

    def _ordinary_action(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        """Answer who owns the reconciler's next step over its whole window.

        The answer is taken under the shared repository fence. ``incident-owned``
        leaves rerun, classification and revert to the observer; ``ordinary``
        carries the receipt of the one reconciler step it lets run.
        """
        settings = self.installation
        if (
            not _valid_ordinary_action(payload=payload)
            or payload["repository"] != settings.repository
        ):
            return _refused(reason="invalid ordinary-action ownership query")
        action = cast("str", payload["action"])
        result = route_reconciler_window(
            directory=settings.state,
            repository=settings.repository,
            window_shas=frozenset(cast("list[str]", payload["window_shas"])),
            perform=lambda: "ordinary " + action + " retained by the master-health reconciler",
        )
        return {
            "schema": 1,
            "status": result.status,
            "reason": result.reason,
            "receipt": result.receipt,
            "query": payload,
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


def _valid_ordinary_action(*, payload: dict[str, Any]) -> bool:
    shas: object = payload.get("window_shas")
    action: object = payload.get("action")
    if not isinstance(shas, list):
        return False
    window = cast("list[object]", shas)
    return (
        frozenset(payload) == _ORDINARY_ACTION_FIELDS
        and isinstance(payload["repository"], str)
        and isinstance(action, str)
        and action in RECONCILER_ACTIONS
        and len(window) <= MAX_WINDOW_SHAS
        and all(
            isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) is not None
            for sha in window
        )
        and len(set(cast("list[str]", window))) == len(window)
    )


def _refused(*, reason: str) -> dict[str, Any]:
    return {"schema": 1, "status": "refused", "reason": reason}
