"""Expose exact authenticated CI identity without granting admission or mutation."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from livespec_dev_tooling._incident_observer_types import ObserverArmQuery
from livespec_dev_tooling.incident_ci_identity_policy import (
    CiIdentityPolicy,
    identity_policy_intact,
)
from livespec_dev_tooling.incident_ci_job_identity import CiJobVerifier
from livespec_dev_tooling.incident_ci_oidc import oidc_current, verify_oidc
from livespec_dev_tooling.incident_observer_admission import observer_arm_admitted

if TYPE_CHECKING:
    from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

__all__: list[str] = ["CiIdentityVerifier", "identity_query"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb
_FIELDS = frozenset({"repository", "arm_id", "pr_number", "base_sha", "head_sha", "receipt_digest"})


def identity_query(*, payload: dict[str, Any]) -> ObserverArmQuery | None:
    """Reject a consistency query before using any value as a forge path."""
    if (
        frozenset(payload) != _FIELDS
        or type(payload["pr_number"]) is not int
        or payload["pr_number"] <= 0
        or not all(isinstance(payload[k], str) for k in _FIELDS - {"pr_number"})
        or any(
            re.fullmatch(r"[0-9a-f]{64}", payload[k]) is None for k in ("arm_id", "receipt_digest")
        )
        or any(re.fullmatch(r"[0-9a-f]{40}", payload[k]) is None for k in ("base_sha", "head_sha"))
    ):
        return None
    return ObserverArmQuery(**payload)


@dataclass(frozen=True, kw_only=True)
class CiIdentityVerifier:
    """Only the protected installed policy selects signature and forge trust."""

    installation: ControllerInstallation

    def execute(self, *, authorization: str, payload: dict[str, Any]) -> dict[str, Any]:
        policy = getattr(self.installation, "ci_identity_policy", None)
        if not isinstance(policy, CiIdentityPolicy):
            return _refused(reason="protected CI identity policy unavailable")
        try:
            query = identity_query(payload=payload)
            if (
                query is None
                or query.repository != self.installation.repository
                or not authorization.startswith("Bearer ")
                or not observer_arm_admitted(directory=self.installation.state, query=query)
            ):
                return _refused(reason="exact retained CI identity arm unavailable")
            token = authorization.removeprefix("Bearer ")
            identity = verify_oidc(token=token, policy=policy, now=time.time())
            if identity is None:
                return _refused(reason="CI issuer identity unverifiable or unsupported")
            job = CiJobVerifier(identity=identity, query=query).verify()
            if (
                job is None
                or not oidc_current(identity=identity, now=time.time())
                or not identity_policy_intact(policy=policy)
                or not observer_arm_admitted(directory=self.installation.state, query=query)
            ):
                return _refused(reason="CI identity observations changed or unavailable")
            return {
                "schema": 1,
                "status": "authenticated",
                "identity": asdict(identity) | asdict(job) | asdict(query),
                "policy_sha256": policy.digest,
                "authorizes_current_effects": False,
                "ci_admission": False,
                "authorizes_merge": False,
                "normal_factory_proof": False,
            }
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return _refused(reason="CI identity state or observations unavailable")


def _refused(*, reason: str) -> dict[str, Any]:
    return {"schema": 1, "status": "refused", "reason": reason}
