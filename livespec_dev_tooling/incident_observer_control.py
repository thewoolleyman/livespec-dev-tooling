"""Authenticated control operations for the independently provisioned observer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    repository_lock,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_forge_reads import ForgeReads
from livespec_dev_tooling.incident_observer_admission import (
    arm_before_merge,
    bind_after_merge,
)
from livespec_dev_tooling.incident_observer_authority import CurrentAuthorityReader
from livespec_dev_tooling.incident_observer_forge import MergedRunVerifier
from livespec_dev_tooling.incident_observer_invalidation import ObserverCiInvalidation

__all__: list[str] = ["ObserverControl"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wanebl


@dataclass(frozen=True, kw_only=True)
class ObserverControl:
    """Use canonical authority and host-owned identity, never request capabilities."""

    installation: ControllerInstallation

    def execute(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.installation
        if path == "/invalidate-ci":
            return ObserverCiInvalidation(installation=settings).execute(payload=payload)
        if path == "/arm":
            return self._arm(payload=payload)
        if path == "/bind" and set(payload) == {"repository", "head_sha", "run_id"}:
            with repository_lock(
                directory=settings.state, repository=settings.repository
            ) as record_path:
                arm = read_observer_arm(record=load_record(path=record_path))
            if (
                arm is None
                or type(payload["run_id"]) is not int
                or payload["run_id"] <= 0
                or not isinstance(payload["head_sha"], str)
            ):
                return {
                    "status": "refused",
                    "reason": f"retained arm and exact {settings.target_branch} run required",
                }
            # The configured target branch is the only branch a binding can name.
            registration = ObserverRegistration(
                repository=arm.repository,
                incident_item_id=arm.incident_item_id,
                attempt_id=arm.attempt_id,
                operation_id=arm.operation_id,
                generation=arm.generation,
                owner=arm.owner,
                phase=arm.phase,
                head_sha=payload["head_sha"],
                run_id=payload["run_id"],
                required_jobs=arm.required_jobs,
                controller_release=arm.controller_release,
                controller_revision=arm.controller_revision,
                candidate_revision=arm.head_sha,
                authority_receipt=arm.authority_receipt,
                branch=settings.target_branch,
            )
            return asdict(
                bind_after_merge(
                    directory=settings.state,
                    arm=arm,
                    registration=registration,
                    verify_merged_run=MergedRunVerifier(
                        read=ForgeReads.installed(installation=settings),
                        target_branch=settings.target_branch,
                    ),
                )
            )
        return {"status": "refused", "reason": "unknown or malformed control operation"}

    def _arm(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.installation
        snapshot = payload.copy()
        expected = snapshot.pop("expected_arm_id", None)
        if any(
            key in snapshot
            for key in ("controller_release", "controller_revision", "required_jobs")
        ):
            return {
                "status": "refused",
                "reason": "controller identity and job universe belong to host provisioning",
            }
        snapshot.update(
            controller_release=settings.release,
            controller_revision=settings.revision,
            required_jobs=list(settings.jobs),
        )
        arm = read_observer_arm(
            record={
                "observer_arm": snapshot,
                "observer_arm_id": hashlib.sha256(
                    json.dumps(snapshot, sort_keys=True).encode()
                ).hexdigest(),
            }
        )
        if arm is None or (expected is not None and not isinstance(expected, str)):
            return {"status": "refused", "reason": "invalid exact observer arm"}
        reader = CurrentAuthorityReader(
            command=settings.reader,
            repo=settings.repo,
            release=settings.reader_release,
            installed_reader_approved=lambda release, command: (release, command)
            == (settings.reader_release, settings.reader),
        )
        return asdict(
            arm_before_merge(
                directory=settings.state,
                arm=arm,
                expected_arm_id=expected,
                authorize_current=reader,
                released_controller=lambda release, revision: (release, revision)
                == (settings.release, settings.revision),
            )
        )
