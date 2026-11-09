"""Retain one immutable, non-authorizing attachment for a freshly authenticated CI job."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from livespec_dev_tooling._incident_ci_attachment_store import (
    attachment_receipt,
    attachment_slot,
    attachment_tree,
)
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    repository_lock,
    save_record,
)
from livespec_dev_tooling.incident_ci_identity import (
    VerifiedCiInvocation,
    identity_query,
    verify_ci_invocation,
)
from livespec_dev_tooling.incident_ci_identity_policy import (
    CiIdentityPolicy,
    identity_policy_intact,
)
from livespec_dev_tooling.incident_ci_oidc import OidcIdentity, oidc_current, verify_oidc
from livespec_dev_tooling.incident_observer_admission import arm_record_matches
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError

if TYPE_CHECKING:
    from livespec_dev_tooling._incident_observer_types import ObserverArmQuery
    from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

__all__: list[str] = ["CiJobAttachment", "attachment_binding"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
_MAX_ATTACHMENTS = 1024
_TIMES = frozenset({"issued_at", "not_before", "expires_at"})


def attachment_binding(
    *, verified: VerifiedCiInvocation, release: str, revision: str
) -> dict[str, Any]:
    """Whitelist the stable public binding; never the token, its times or raw receipt."""
    arm = verified.arm
    return {
        **_signed(identity=verified.identity, query=verified.query),
        "incident_item_id": arm.incident_item_id,
        "attempt_id": arm.attempt_id,
        "operation_id": arm.operation_id,
        "generation": arm.generation,
        "owner": arm.owner,
        "phase": arm.phase,
        "job_id": verified.job.job_id,
        "check_suite_id": verified.job.check_suite_id,
        "policy_sha256": verified.policy.digest,
        "controller_release": release,
        "controller_revision": revision,
    }


@dataclass(frozen=True, kw_only=True)
class CiJobAttachment:
    """Only actual issuer authentication attaches; identical retries recover the receipt."""

    installation: ControllerInstallation

    def execute(self, *, authorization: str, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.installation
        policy = getattr(settings, "ci_identity_policy", None)
        if not isinstance(policy, CiIdentityPolicy):
            return _refused(reason="protected CI identity policy unavailable")
        try:
            query = identity_query(payload=payload)
            if (
                query is None
                or query.repository != settings.repository
                or not authorization.startswith("Bearer ")
            ):
                return _refused(reason="exact CI attachment query required")
            identity = verify_oidc(
                token=authorization.removeprefix("Bearer "), policy=policy, now=time.time()
            )
            if identity is None:
                return _refused(reason="CI issuer identity unverifiable or unsupported")
            return self._attach(identity=identity, query=query, policy=policy)
        except (OSError, ValueError, IncidentJsonRefusalError, TypeError, KeyError, RecursionError):
            return _refused(reason="CI attachment state or observations unavailable")

    def _attach(
        self, *, identity: OidcIdentity, query: ObserverArmQuery, policy: CiIdentityPolicy
    ) -> dict[str, Any]:
        settings = self.installation
        slot = _slot(identity=identity)
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            existing = attachment_tree(record=load_record(path=path))["attachments"].get(slot)
        if existing is not None:
            return _recover(entry=existing, identity=identity, query=query, policy=policy)
        # Fresh attachment repeats full protected verification outside the effect lock.
        verified = verify_ci_invocation(
            installation=settings, policy=policy, query=query, identity=identity
        )
        if verified is None:
            return _refused(reason="CI identity observations changed or unavailable")
        return self._commit(verified=verified, slot=slot)

    def _commit(self, *, verified: VerifiedCiInvocation, slot: str) -> dict[str, Any]:
        settings = self.installation
        binding = attachment_binding(
            verified=verified, release=settings.release, revision=settings.revision
        )
        receipt = attachment_receipt(binding=binding)
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            record = load_record(path=path)
            tree = attachment_tree(record=record)
            entries: dict[str, dict[str, Any]] = tree["attachments"]
            existing = entries.get(slot)
            if existing is not None:
                return (
                    existing["receipt"]
                    if existing["receipt"] == receipt
                    else _refused(reason="CI attachment slot holds another immutable binding")
                )
            if (
                not oidc_current(identity=verified.identity, now=time.time())
                or not identity_policy_intact(policy=verified.policy)
                or not arm_record_matches(record=record, query=verified.query)
                or read_observer_arm(record=record) != verified.arm
            ):
                return _refused(reason="CI identity, policy or retained arm changed")
            if any(
                (v["binding"]["repository_id"], v["binding"]["job_id"])
                == (binding["repository_id"], binding["job_id"])
                for v in entries.values()
            ):
                return _refused(reason="CI job is already attached to another signed check")
            if len(entries) >= _MAX_ATTACHMENTS:
                return _refused(reason="CI attachment capacity exhausted; nothing was pruned")
            entries[slot] = {
                "binding": binding,
                "binding_digest": receipt["binding_digest"],
                "receipt": receipt,
                "attached_at": int(time.time()),
                "observations": [],
            }
            record["ci_job_attachments"] = tree
            save_record(path=path, record=record)
        return receipt


def _signed(*, identity: OidcIdentity, query: ObserverArmQuery) -> dict[str, Any]:
    signed = {k: v for k, v in asdict(identity).items() if k not in _TIMES}
    return signed | asdict(query)


def _slot(*, identity: OidcIdentity) -> str:
    return attachment_slot(
        repository_id=identity.repository_id,
        run_id=identity.run_id,
        run_attempt=identity.run_attempt,
        check_run_id=identity.check_run_id,
    )


def _recover(
    *,
    entry: dict[str, Any],
    identity: OidcIdentity,
    query: ObserverArmQuery,
    policy: CiIdentityPolicy,
) -> dict[str, Any]:
    """Read-only: an exact retry returns its original receipt and never reattaches."""
    binding = entry["binding"]
    claims = _signed(identity=identity, query=query) | {"policy_sha256": policy.digest}
    if any(binding[k] != v for k, v in claims.items()):
        return _refused(reason="CI attachment slot conflicts with immutable binding")
    return entry["receipt"]


def _refused(*, reason: str) -> dict[str, Any]:
    return {"schema": 1, "status": "refused", "reason": reason}
