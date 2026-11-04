"""Immutable release receipts and controller-owned serialization helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal, cast

from livespec_dev_tooling._incident_observer_store import registration_record
from livespec_dev_tooling._incident_observer_types import ObserverRegistration

__all__: list[str] = [
    "ReleaseAttribution",
    "ReleaseLookup",
    "ReleaseResult",
    "_attributions",
    "_digest",
    "_fenced",
    "_mapping",
    "_object",
    "_receipt",
    "_registration",
    "_valid",
]
_INVALID_RECEIPT = "invalid controller release receipt"

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-vg36aq


@dataclass(frozen=True, kw_only=True)
class ReleaseAttribution:
    """Authenticated source, published artifact, carrier and installed consumer."""

    source_sha: str
    release_tag: str
    image_digest: str
    pin_carrier: str
    consumer_repository: str
    installed_revision: str
    installation_receipt: str
    irreversible: bool = False
    compensation_receipt: str = ""


@dataclass(frozen=True, kw_only=True)
class ReleaseResult:
    """Unresolved work never becomes an adoption or recovery success."""

    status: str
    receipt: str = ""


@dataclass(frozen=True, kw_only=True)
class ReleaseLookup:
    """A trusted service's exact bound no-effect/recorded/unknown answer."""

    operation: str
    identity: str
    status: Literal["absent", "recorded", "unknown"]
    receipt: str = ""


def _digest(*, value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid(
    *,
    registration: ObserverRegistration,
    attribution: ReleaseAttribution,
    allow_uninstalled: bool = False,
) -> bool:
    return (
        bool(registration.authority_receipt)
        and all(
            isinstance(value, str) and value
            for key, value in asdict(attribution).items()
            if key not in {"irreversible", "compensation_receipt"}
            and not (allow_uninstalled and key == "installation_receipt")
        )
        and type(attribution.irreversible) is bool
        and (not attribution.irreversible or bool(attribution.compensation_receipt))
    )


def _object(*, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(_INVALID_RECEIPT)
    return cast("dict[str, object]", value)


def _mapping(*, record: dict[str, object], field: str) -> dict[str, object]:
    return _object(value=record.setdefault(field, {}))


def _receipt(*, value: object) -> str:
    receipt = _object(value=value).get("receipt")
    return receipt if isinstance(receipt, str) else ""


def _attributions(
    *, record: dict[str, object], registration: ObserverRegistration
) -> tuple[ReleaseAttribution, ...]:
    matches: list[ReleaseAttribution] = []
    for raw in _mapping(record=record, field="release_attribution").values():
        entry = _object(value=raw)
        if entry.get("registration") == _registration(registration=registration):
            values = _object(value=entry["attribution"])
            attribution = _decode_attribution(values=values)
            if not _valid(registration=registration, attribution=attribution):
                raise TypeError(_INVALID_RECEIPT)
            matches.append(attribution)
    return tuple(matches)


def _fenced(*, record: dict[str, object], registration: ObserverRegistration) -> bool:
    identity = _registration(registration=registration)
    return any(
        _object(value=entry).get("registration") == identity
        for name in ("actions", "release_regressions")
        for entry in _mapping(record=record, field=name).values()
    )


def _decode_attribution(*, values: dict[str, object]) -> ReleaseAttribution:
    return ReleaseAttribution(
        source_sha=cast("str", values["source_sha"]),
        release_tag=cast("str", values["release_tag"]),
        image_digest=cast("str", values["image_digest"]),
        pin_carrier=cast("str", values["pin_carrier"]),
        consumer_repository=cast("str", values["consumer_repository"]),
        installed_revision=cast("str", values["installed_revision"]),
        installation_receipt=cast("str", values["installation_receipt"]),
        irreversible=cast("bool", values["irreversible"]),
        compensation_receipt=cast("str", values["compensation_receipt"]),
    )


def _registration(*, registration: ObserverRegistration) -> dict[str, object]:
    return _object(value=json.loads(json.dumps(registration_record(registration=registration))))
