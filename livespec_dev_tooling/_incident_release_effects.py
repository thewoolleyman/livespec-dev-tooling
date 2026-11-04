"""Exact effect lookup and unknown-outcome handling for release operations."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from livespec_dev_tooling._incident_observer_store import load_record, repository_lock, save_record
from livespec_dev_tooling._incident_observer_types import ObserverRegistration, RecoveryIntent
from livespec_dev_tooling._incident_release_types import (
    ReleaseAttribution,
    ReleaseLookup,
    ReleaseResult,
    _digest,
    _mapping,
    _object,
    _receipt,
    _registration,
)

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["call_effect", "publish_receipt", "recover_attribution", "release_result"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-vg36aq


def call_effect(
    *,
    operation: str,
    identity: str,
    fresh: bool,
    perform: Callable[[], str],
    lookup_effect: Callable[[str, str], ReleaseLookup] | None,
) -> str | None:
    """Issue once or reconcile exact lookup; unknown outcomes never republish."""
    if not fresh:
        if lookup_effect is None:
            return None
        result = _lookup(function=lambda: lookup_effect(operation, identity))
        if not is_successful(result):
            return None
        lookup = unsafe_perform_io(result.unwrap())
        if not isinstance(lookup, ReleaseLookup) or (
            lookup.operation != operation or lookup.identity != identity
        ):
            return None
        if lookup.status == "recorded":
            return lookup.receipt or None
        if lookup.status != "absent" or lookup.receipt:
            return None
    result = _invoke(function=perform)
    return unsafe_perform_io(result.unwrap()) if is_successful(result) else None


@impure_safe
def _invoke(*, function: Callable[[], str]) -> str:
    return function()


@impure_safe
def _lookup(*, function: Callable[[], object]) -> object:
    return function()


@impure_safe
def _call(*, function: Callable[[], ReleaseResult]) -> ReleaseResult:
    return function()


def release_result(*, function: Callable[[], ReleaseResult]) -> ReleaseResult:
    """Refuse unavailable controller storage without an unlocked fallback."""
    result = _call(function=function)
    if not is_successful(result):
        return ReleaseResult(status="refused")
    return unsafe_perform_io(result.unwrap())


def recover_attribution(
    *,
    directory: Path,
    intent: RecoveryIntent,
    attribution: ReleaseAttribution,
    inverse_receipt: str,
    recover_canonical: Callable[[RecoveryIntent, tuple[ReleaseAttribution, ...], str], str],
    lookup_effect: Callable[[str, str], ReleaseLookup] | None,
) -> ReleaseResult:
    """Assign one historical consumer correction by immutable action identity."""
    registration = intent.registration
    # Only immutable identity participates. Observer receipt reconciliation
    # later adds mutable metadata to its action. A new consumer gets its own
    # operation and cannot repeat correction for an already-owned consumer.
    identity = _digest(
        value=(
            intent.action_id,
            _registration(registration=registration),
            inverse_receipt,
            asdict(attribution),
        )
    )
    with repository_lock(directory=directory, repository=registration.repository) as path:
        record = load_record(path=path)
        entries = _mapping(record=record, field="release_recovery")
        fresh = identity not in entries
        entry = entries.setdefault(
            identity,
            {
                "action_id": intent.action_id,
                "registration": _registration(registration=registration),
                "inverse_receipt": inverse_receipt,
                "attribution": asdict(attribution),
                "receipt": "",
            },
        )
        save_record(path=path, record=record)
        prior = _receipt(value=entry)
    if prior:
        return ReleaseResult(status="reconciled", receipt=prior)
    receipt = call_effect(
        operation="recover",
        identity=identity,
        fresh=fresh,
        lookup_effect=lookup_effect,
        perform=lambda: recover_canonical(intent, (attribution,), identity),
    )
    return publish_receipt(
        directory=directory,
        registration=registration,
        field="release_recovery",
        identity=identity,
        receipt=receipt,
        status="reconciled",
    )


def publish_receipt(
    *,
    directory: Path,
    registration: ObserverRegistration,
    field: str,
    identity: str,
    receipt: str | None,
    status: str,
) -> ReleaseResult:
    """Keep a known exact receipt even when current lifecycle has advanced."""
    if not isinstance(receipt, str) or not receipt:
        return ReleaseResult(status="pending")
    with repository_lock(directory=directory, repository=registration.repository) as path:
        record = load_record(path=path)
        entry = _mapping(record=record, field=field)[identity]
        _object(value=entry)["receipt"] = receipt
        save_record(path=path, record=record)
    return ReleaseResult(status=status, receipt=receipt)
