"""Bounded standard-library wire values and complete recovery scope validation."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, cast

from livespec_dev_tooling._incident_inverse_types import LandedIncident
from livespec_dev_tooling._incident_observer_types import RecoveryIntent
from livespec_dev_tooling.incident_strict_json import strict_json

__all__: list[str] = ["JournalValues"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_MAX_TEXT = 65536
_MAX_POSITIVE = 2**63
_MAX_SCOPE_ITEMS = 4096


def _encoded(*, value: Any) -> str:
    if not isinstance(value, bytes):
        message = "only byte fields require canonical encoding"
        raise TypeError(message)
    return base64.b64encode(value).decode("ascii")


class JournalValues:
    """Decode and validate protocol values without creating authority."""

    @staticmethod
    def object(*, value: Any) -> dict[str, Any]:
        return cast("dict[str, Any]", value) if isinstance(value, dict) else {}

    @staticmethod
    def text(*, value: Any) -> bool:
        return isinstance(value, str) and 0 < len(value) <= _MAX_TEXT

    @staticmethod
    def positive(*, value: Any) -> bool:
        return type(value) is int and 0 < value < _MAX_POSITIVE

    @staticmethod
    def digest(*, value: Any) -> bool:
        return isinstance(value, str) and _DIGEST.fullmatch(value) is not None

    @staticmethod
    def sha(*, value: Any) -> bool:
        return isinstance(value, str) and _SHA.fullmatch(value) is not None

    @staticmethod
    def bytes(*, value: Any) -> bytes:
        if not isinstance(value, str) or len(value) > 4 * _MAX_TEXT:
            message = "invalid bounded byte field"
            raise ValueError(message)
        decoded = base64.b64decode(value, validate=True)
        if base64.b64encode(decoded).decode("ascii") != value:
            message = "noncanonical byte field"
            raise ValueError(message)
        return decoded

    @staticmethod
    def scope(*, raw: Any) -> LandedIncident:
        data = JournalValues.object(value=raw)
        texts = {
            "repository",
            "original_base_sha",
            "original_head_sha",
            "before_sha",
            "merge_sha",
            "patch_sha256",
            "authority_sha256",
        }
        lists = {"landed_commits", "landed_trees", "changed_paths"}
        if not (
            set(data) == texts | lists | {"pr_number"}
            and all(JournalValues.text(value=data[key]) for key in texts)
            and JournalValues.positive(value=data["pr_number"])
            and all(
                isinstance(data[key], list)
                and 0 < len(data[key]) <= _MAX_SCOPE_ITEMS
                and all(JournalValues.text(value=v) for v in data[key])
                for key in lists
            )
            and all(
                JournalValues.sha(value=data[key])
                for key in ("original_base_sha", "original_head_sha", "before_sha", "merge_sha")
            )
            and JournalValues.digest(value=data["patch_sha256"])
            and JournalValues.digest(value=data["authority_sha256"])
            and all(
                JournalValues.sha(value=v)
                for key in ("landed_commits", "landed_trees")
                for v in data[key]
            )
            and data["landed_commits"][-1] == data["merge_sha"]
            and len(data["landed_commits"]) == len(data["landed_trees"])
        ):
            message = "invalid complete recovery scope"
            raise ValueError(message)
        return LandedIncident(
            repository=data["repository"],
            pr_number=data["pr_number"],
            original_base_sha=data["original_base_sha"],
            original_head_sha=data["original_head_sha"],
            before_sha=data["before_sha"],
            merge_sha=data["merge_sha"],
            landed_commits=tuple(data["landed_commits"]),
            landed_trees=tuple(data["landed_trees"]),
            patch_sha256=data["patch_sha256"],
            changed_paths=tuple(data["changed_paths"]),
            authority_sha256=data["authority_sha256"],
        )

    @staticmethod
    def scope_matches(*, scope: LandedIncident, intent: RecoveryIntent) -> bool:
        arm, registration = intent.observer_arm, intent.registration
        return (
            scope.repository == registration.repository
            and scope.merge_sha == registration.head_sha
            and scope.authority_sha256 == hashlib.sha256(registration.authority_receipt).hexdigest()
            and (
                arm is None
                or (scope.pr_number, scope.original_base_sha, scope.original_head_sha)
                == (arm.pr_number, arm.base_sha, arm.head_sha)
            )
        )

    @staticmethod
    def decode(*, raw: bytes, limit: int) -> Any:
        """Decode bounded strict JSON without optional application dependencies."""
        return strict_json(text=raw, limit=limit)

    @staticmethod
    def canonical(*, value: Any) -> bytes:
        """Match ProcessInverseForge's canonical payload bytes, including base64."""
        return json.dumps(
            value, sort_keys=True, default=lambda value: _encoded(value=value), allow_nan=False
        ).encode()

    @staticmethod
    def wire(*, value: Any) -> dict[str, Any]:
        return JournalValues.object(
            value=strict_json(text=JournalValues.canonical(value=value), limit=None)
        )
