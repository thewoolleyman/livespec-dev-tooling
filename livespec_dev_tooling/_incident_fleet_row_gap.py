"""Why one audited incident row is unclassified, named for that row.

A claimless row, a claim bound to another manifest identity, a malformed claim, a stale
release build, an unreadable serving version and an unconfirmed re-read are different gaps
with different remedies. Each unclassified row names the first one it has, so an operator
reading the findings knows what to refresh, author or read, rather than one fixed
sentence for every row.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence

__all__: list[str] = ["row_gap"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-v46q5g
_DISPOSITIONS = frozenset({"implemented", "deliberately-normal", "not-applicable"})
_SCOPE_DIGEST = re.compile(r"[0-9a-f]{64}")
_NO_CLAIM = "no committed claim for this consumer and surface"
_INAPPLICABLE_CLAIM = "claim for a runtime surface the instruction-only profile does not carry"
_INCOMPLETE_CLAIM = "claim lacks a source path, proof reference, owner or release build"
_INCOMPLETE_IMPLEMENTED = (
    "implemented claim lacks its incident item, normal factory proof or scope digest"
)
_UNREADABLE = "serving version unreadable: no installed serving build was read (unverified)"


def _claim_gap(*, claim: CapabilityEvidence, manifest_sha256: str, instruction_only: bool) -> str:
    """What the claim itself lacks before any serving read is consulted; "" when nothing."""
    if claim.manifest_sha256 != manifest_sha256:
        return (
            f"claim is bound to manifest {claim.manifest_sha256}, "
            f"not the committed identity {manifest_sha256}"
        )
    if claim.disposition not in _DISPOSITIONS:
        return f"claim names no known disposition: {claim.disposition}"
    if not all((claim.source_path, claim.proof_ref, claim.owner, claim.release_build)):
        return _INCOMPLETE_CLAIM
    if claim.disposition != "implemented":
        return "" if claim.reason else f"claim gives no reason for {claim.disposition}"
    if instruction_only or (
        bool(claim.incident_item and claim.normal_factory_proof)
        and _SCOPE_DIGEST.fullmatch(claim.cumulative_scope) is not None
    ):
        return ""
    return _INCOMPLETE_IMPLEMENTED


def _serving_gap(
    *,
    claim: CapabilityEvidence,
    confirmed: Callable[[CapabilityEvidence], bool],
    explain: Callable[[CapabilityEvidence], str],
) -> str:
    """Why the serving read does not bear the claim out; "" when it does, twice."""
    named = explain(claim)
    if claim.serving_build == "":
        return named or _UNREADABLE
    if claim.release_build != claim.serving_build:
        return named or (
            f"claim release build {claim.release_build} "
            f"is not the serving version read {claim.serving_build}"
        )
    if confirmed(claim) is not True:
        return f"serving version {claim.serving_build} not confirmed by an independent re-read"
    return ""


def row_gap(
    *,
    claim: CapabilityEvidence | None,
    manifest_sha256: str,
    instruction_only: bool,
    inapplicable: bool,
    confirmed: Callable[[CapabilityEvidence], bool],
    explain: Callable[[CapabilityEvidence], str],
) -> str:
    """The first missing evidence of a row; "" when the claim classifies it.

    `claim` carries the serving build the audit read for it. `confirmed` is the
    independent re-read, and `explain` may name why a reader's own read cannot bear the
    claim out (a release-keyed row's reason); its name wins over the generic serving gap.
    """
    if claim is None:
        return _NO_CLAIM
    if inapplicable:
        return _INAPPLICABLE_CLAIM
    return _claim_gap(
        claim=claim, manifest_sha256=manifest_sha256, instruction_only=instruction_only
    ) or _serving_gap(claim=claim, confirmed=confirmed, explain=explain)
