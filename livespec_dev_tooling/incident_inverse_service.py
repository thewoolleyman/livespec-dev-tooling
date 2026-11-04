"""Versioned process adapter for the independent scoped recovery principal.

The host provisions and authenticates this service separately from candidates,
CI and the tenant wrapper. This adapter grants no forge capability by itself.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from typing import cast

from livespec_dev_tooling._incident_inverse_types import (
    InverseConflictRequest,
    InversePublishRequest,
    InversePublishResult,
    LandedIncident,
)
from livespec_dev_tooling._incident_observer_store import (
    REPOSITORY_FENCE_FD_ENV,
    current_repository_fence,
)
from livespec_dev_tooling._incident_observer_types import RecoveryIntent

__all__: list[str] = ["ProcessInverseForge"]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac
_MAX_TIMEOUT_SECONDS = 60
_LOOKUP_REFUSAL = "exact action receipt is unobservable or reserved; publication refused"


@dataclass(frozen=True, kw_only=True)
class ProcessInverseForge:
    """Call an installed controller-owned principal, never candidate executables.

    The service contract requires exact action-id idempotency, durable intent
    reservation BEFORE effects, expected-master-head CAS, and atomic receipt
    recovery. `head-moved` alone certifies that no effect occurred. A timeout,
    malformed answer or missing receipt is unknown, never permission to retry.
    Scope resolution authenticates the original armed PR/base/head and complete
    landed chain/trees/full patch; it does not rely on terminal merge SHA alone.
    """

    command: tuple[str, ...]
    timeout_seconds: int = 15

    def landed_incident(self, *, intent: RecoveryIntent) -> LandedIncident | None:
        response = self._call(operation="landed", payload={"intent": asdict(intent)})
        scope = response.get("scope")
        if not isinstance(scope, dict):
            return None
        data = cast("dict[str, object]", scope)
        texts = (
            "repository",
            "original_base_sha",
            "original_head_sha",
            "before_sha",
            "merge_sha",
            "patch_sha256",
            "authority_sha256",
        )
        lists = ("landed_commits", "landed_trees", "changed_paths")
        if (
            set(data) != {*texts, *lists, "pr_number"}
            or not all(isinstance(data.get(key), str) for key in texts)
            or type(data.get("pr_number")) is not int
            or not all(_text_list(value=data.get(key)) for key in lists)
        ):
            return None
        return LandedIncident(
            repository=cast("str", data["repository"]),
            pr_number=cast("int", data["pr_number"]),
            original_base_sha=cast("str", data["original_base_sha"]),
            original_head_sha=cast("str", data["original_head_sha"]),
            before_sha=cast("str", data["before_sha"]),
            merge_sha=cast("str", data["merge_sha"]),
            landed_commits=tuple(cast("list[str]", data["landed_commits"])),
            landed_trees=tuple(cast("list[str]", data["landed_trees"])),
            patch_sha256=cast("str", data["patch_sha256"]),
            changed_paths=tuple(cast("list[str]", data["changed_paths"])),
            authority_sha256=cast("str", data["authority_sha256"]),
        )

    def authorize_inverse(self, *, intent: RecoveryIntent, scope: LandedIncident) -> bool:
        return (
            self._call(
                operation="authorize", payload={"intent": asdict(intent), "scope": asdict(scope)}
            ).get("authorized")
            is True
        )

    def read_master_head(self, *, repository: str, branch: str) -> str:
        return (
            _text(
                value=self._call(
                    operation="head", payload={"repository": repository, "branch": branch}
                ).get("head")
            )
            or ""
        )

    def read_exact_receipt(self, *, intent: RecoveryIntent) -> str | None:
        """None means definitive no-effect; unavailable or reserved is a refusal."""
        response = self._call(operation="lookup", payload={"intent": asdict(intent)})
        receipt = _text(value=response.get("receipt"))
        if response.get("status") == "recorded" and receipt:
            return receipt
        if response.get("status") == "absent" and response.get("receipt") is None:
            return None
        raise OSError(_LOOKUP_REFUSAL)

    def publish_inverse(self, *, request: InversePublishRequest) -> InversePublishResult:
        response = self._call(operation="publish", payload={"request": asdict(request)})
        status = response.get("status")
        if not isinstance(status, str) or status not in {"committed", "head-moved"}:
            return InversePublishResult(status="unknown")
        return InversePublishResult(
            status=status,
            merge_sha=_text(value=response.get("merge_sha")),
            tree_sha=_text(value=response.get("tree_sha")),
        )

    def record_conflict(self, *, request: InverseConflictRequest) -> str | None:
        return _text(
            value=self._call(operation="conflict", payload={"request": asdict(request)}).get(
                "receipt"
            )
        )

    def _call(self, *, operation: str, payload: dict[str, object]) -> dict[str, object]:
        if not self.command or not 0 < self.timeout_seconds < _MAX_TIMEOUT_SECONDS:
            return {}
        binding = {
            "request_sha256": hashlib.sha256(
                json.dumps(
                    payload, sort_keys=True, default=lambda value: _bytes(value=value)
                ).encode()
            ).hexdigest()
        }
        body = {"schema": 1, "operation": operation, "binding": binding, **payload}
        environment = {
            key: value for key, value in os.environ.items() if key != REPOSITORY_FENCE_FD_ENV
        }
        fence = current_repository_fence(repository=_repository(payload=payload))
        descriptors: tuple[int, ...] = ()
        if fence is not None:
            descriptors = (fence.descriptor,)
            environment[REPOSITORY_FENCE_FD_ENV] = str(fence.descriptor)
        try:
            result = subprocess.run(  # noqa: S603 — controller-owned provisioned argv; no shell or candidate command.
                [*self.command],
                input=json.dumps(body, default=lambda value: _bytes(value=value)).encode(),
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
                env=environment,
                pass_fds=descriptors,
            )
            response: object = json.loads(result.stdout) if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {}
        if not isinstance(response, dict):
            return {}
        data = cast("dict[str, object]", response)
        return (
            data
            if (
                type(data.get("schema")) is int
                and data.get("schema") == 1
                and data.get("operation") == operation
                and data.get("binding") == binding
            )
            else {}
        )


def _text(*, value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _text_list(*, value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) for item in cast("list[object]", value)
    )


def _bytes(*, value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _repository(*, payload: dict[str, object]) -> str:
    direct = payload.get("repository")
    if isinstance(direct, str):
        return direct
    value = payload.get("request", payload)
    if not isinstance(value, dict):
        return ""
    intent = cast("dict[str, object]", value).get("intent")
    registration = (
        cast("dict[str, object]", intent).get("registration") if isinstance(intent, dict) else None
    )
    repository = (
        cast("dict[str, object]", registration).get("repository")
        if isinstance(registration, dict)
        else None
    )
    return repository if isinstance(repository, str) else ""
