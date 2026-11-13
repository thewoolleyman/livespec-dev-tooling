"""Record a PASSED incident CI aggregate its protected CI job publishes to the controller.

`POST /ci/publish` takes the job's forge-issued OIDC identity token as
`Authorization: Bearer <JWT>` and exactly `query` (the six-field retained arm
query `/ci/attach` takes), `aggregate` (the released aggregate, which must have
PASSED for the query's head) and `release` (the released build that produced it).
The controller verifies the publication exactly as it verifies an attachment, by
attaching the publishing job, and then, under the repository lock and against the
identical unbound, unrevoked retained arm, retains a `published` record holding the
aggregate digest, its passed and deferred members, the omitted members it derives
itself from the coverage and spec deferrals, and the attachment id of the publishing
job. The run sweep then writes it onto the incident item through the ledger port.

A repeated publication of the same aggregate answers `retained` and writes nothing.
A different aggregate for a run attempt that already holds a published one is kept
as a `conflict` record naming both digests, never as a replacement. A publication
whose query no longer matches the retained arm is refused as `publication-stale`
and records no published record; when the publishing job was already attached, the
refusal is retained as an `unpublished` record with the conclusion `unknown`, so it
reaches the item. An installation with no CI identity policy answers
`identity-not-provisioned`. Every reply carries the four false authority fields: a
publication authorizes no current effects, no CI admission, no merge and no factory
proof.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import Event
from typing import TYPE_CHECKING, Any, cast

from livespec_dev_tooling._incident_ci_identity_json import identity_json
from livespec_dev_tooling._incident_observer_dispatch import json_reply
from livespec_dev_tooling._incident_observer_store import load_record, repository_lock, save_record
from livespec_dev_tooling._incident_pr_run_store import (
    KEY_INTS,
    KEY_TEXTS,
    add_record,
    published_digests,
    run_slot,
)
from livespec_dev_tooling.incident_ci_attachment import CiJobAttachment
from livespec_dev_tooling.incident_ci_identity import identity_query
from livespec_dev_tooling.incident_ci_identity_policy import CiIdentityPolicy
from livespec_dev_tooling.incident_observer_admission import arm_record_matches
from livespec_dev_tooling.incident_observer_endpoint import _read_request
from livespec_dev_tooling.incident_pr_run_records import NOT_PROVISIONED
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError

if TYPE_CHECKING:
    from livespec_dev_tooling._incident_observer_types import ObserverArmQuery
    from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

__all__: list[str] = [
    "INVALID",
    "STALE",
    "UNAVAILABLE",
    "UNVERIFIED",
    "CiPublication",
    "aggregate_digest",
    "publication_reply",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
INVALID = "publication-invalid"
STALE = "publication-stale"
UNVERIFIED = "identity-unverified"
UNAVAILABLE = "state-unavailable"
_DIGEST = b"livespec-incident-ci-aggregate-v1\0"
_OMITTING = frozenset({"incident-policy:coverage", "incident-policy:spec"})
_AGGREGATE = frozenset(
    {"status", "head_sha", "scope", "passed", "failed", "missing", "deferred", "context_name"}
)
_PUBLICATION = frozenset({"query", "aggregate", "release"})
_MAX_MEMBERS = 4096
_NAME = re.compile(r"check-[a-z0-9-]{1,120}")
_REASON = re.compile(r"[A-Za-z0-9:_.-]{1,128}")
_RELEASE = re.compile(r"v[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}")
_FALSE = {
    "authorizes_current_effects": False,
    "ci_admission": False,
    "authorizes_merge": False,
    "normal_factory_proof": False,
}
_STATUSES = {"published": "202 Accepted", "retained": "202 Accepted", "conflict": "409 Conflict"}
_StartResponse = Callable[[str, list[tuple[str, str]]], object]


def aggregate_digest(*, aggregate: dict[str, Any]) -> str:
    """Domain-separated digest of the canonical aggregate JSON."""
    raw = json.dumps(aggregate, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(_DIGEST + raw).hexdigest()


def publication_reply(
    *,
    installation: ControllerInstallation,
    wake: Event,
    environ: dict[str, Any],
    start_response: _StartResponse,
) -> Iterable[bytes]:
    """Serve one publication: 202 when its published record is held, 409 on a conflict."""
    result = _reply(status="refused", reason=INVALID)
    try:
        payload = identity_json(raw=_read_request(environ=environ) or b"")
        result = CiPublication(installation=installation, wake=wake).execute(
            authorization=str(environ.get("HTTP_AUTHORIZATION", "")), payload=payload
        )
    except (OSError, ValueError, IncidentJsonRefusalError, TypeError, RecursionError):
        pass
    status = result["status"]
    return json_reply(
        start_response=start_response,
        status=_STATUSES.get(status, "403 Forbidden"),
        result=result,
    )


@dataclass(frozen=True, kw_only=True)
class CiPublication:
    """Verify one publication as an attachment, then retain its record under the lock."""

    installation: ControllerInstallation
    wake: Event

    def execute(self, *, authorization: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(getattr(self.installation, "ci_identity_policy", None), CiIdentityPolicy):
            return _reply(status="refused", reason=NOT_PROVISIONED)
        query = _query(payload=payload, repository=self.installation.repository)
        if query is None:
            return _reply(status="refused", reason=INVALID)
        receipt = CiJobAttachment(installation=self.installation).execute(
            authorization=authorization, payload=payload["query"]
        )
        try:
            if receipt["status"] != "attached":
                return _reply(status="refused", reason=self._unattached(query=query))
            return self._retain(query=query, payload=payload, receipt=receipt)
        except (OSError, ValueError, IncidentJsonRefusalError, TypeError, KeyError):
            return _reply(status="refused", reason=UNAVAILABLE)

    def _unattached(self, *, query: ObserverArmQuery) -> str:
        settings = self.installation
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            current = arm_record_matches(record=load_record(path=path), query=query)
        return UNVERIFIED if current else STALE

    def _retain(
        self, *, query: ObserverArmQuery, payload: dict[str, Any], receipt: dict[str, Any]
    ) -> dict[str, Any]:
        settings = self.installation
        binding = receipt["binding"]
        key = {name: binding[name] for name in sorted(KEY_INTS | KEY_TEXTS)}
        aggregate = payload["aggregate"]
        digest = aggregate_digest(aggregate=aggregate)
        slot = run_slot(run_id=key["run_id"], run_attempt=key["run_attempt"])
        attachment_id = receipt["attachment_id"]
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            record = load_record(path=path)
            retained = published_digests(record=record, slot=slot)
            if digest in retained:
                return _reply(status="retained", reason=None, digest=digest)
            if not arm_record_matches(record=record, query=query):
                kind, content = "unpublished", {"conclusion": "unknown", "refusal": STALE}
                result = _reply(status="refused", reason=STALE)
            elif retained:
                kind, content = (
                    "conflict",
                    {
                        "attachment_id": attachment_id,
                        "retained_digest": retained[0],
                        "offered_digest": digest,
                    },
                )
                result = _reply(status="conflict", reason=None, digest=digest)
            else:
                kind, content = (
                    "published",
                    _content(payload=payload, attachment_id=attachment_id, digest=digest),
                )
                result = _reply(status="published", reason=None, digest=digest)
            if add_record(record=record, kind=kind, key=key, content=content):
                save_record(path=path, record=record)
        self.wake.set()
        return result


def _query(*, payload: dict[str, Any], repository: str) -> ObserverArmQuery | None:
    """The exact arm query of a well-formed publication of a PASSED aggregate, or None."""
    if frozenset(payload) != _PUBLICATION:
        return None
    raw_query, aggregate, release = payload["query"], payload["aggregate"], payload["release"]
    query = (
        identity_query(payload=cast("dict[str, Any]", raw_query))
        if isinstance(raw_query, dict)
        else None
    )
    if (
        query is None
        or query.repository != repository
        or not isinstance(release, str)
        or _RELEASE.fullmatch(release) is None
        or not isinstance(aggregate, dict)
        or not _passed(aggregate=cast("dict[str, Any]", aggregate), head_sha=query.head_sha)
    ):
        return None
    return query


def _passed(*, aggregate: dict[str, Any], head_sha: str) -> bool:
    """A PASSED aggregate for exactly this head: members passed, none failed or missing."""
    passed, deferred = aggregate.get("passed"), aggregate.get("deferred")
    return (
        frozenset(aggregate) == _AGGREGATE
        and aggregate["status"] == "passed"
        and aggregate["head_sha"] == head_sha
        and aggregate["context_name"] == "ci-green"
        and isinstance(aggregate["scope"], str)
        and re.fullmatch(r"[0-9a-f]{64}", aggregate["scope"]) is not None
        and aggregate["failed"] == []
        and aggregate["missing"] == []
        and isinstance(passed, list)
        and 0 < len(cast("list[object]", passed)) <= _MAX_MEMBERS
        and all(isinstance(n, str) and _NAME.fullmatch(n) for n in cast("list[object]", passed))
        and isinstance(deferred, list)
        and len(cast("list[object]", deferred)) <= _MAX_MEMBERS
        and all(_deferral(row=row) for row in cast("list[object]", deferred))
    )


def _deferral(*, row: object) -> bool:
    if not isinstance(row, dict):
        return False
    data = cast("dict[str, object]", row)
    name, reason = data.get("name"), data.get("reason")
    return (
        set(data) == {"name", "reason"}
        and isinstance(name, str)
        and _NAME.fullmatch(name) is not None
        and isinstance(reason, str)
        and _REASON.fullmatch(reason) is not None
    )


def _content(*, payload: dict[str, Any], attachment_id: str, digest: str) -> dict[str, Any]:
    aggregate = payload["aggregate"]
    deferred = [{"name": d["name"], "reason": d["reason"]} for d in aggregate["deferred"]]
    return {
        "controller_build": payload["release"],
        "attachment_id": attachment_id,
        "aggregate_digest": digest,
        "passed": list(aggregate["passed"]),
        "deferred": deferred,
        "omitted": sorted(d["name"] for d in deferred if d["reason"] in _OMITTING),
    }


def _reply(*, status: str, reason: str | None, digest: str | None = None) -> dict[str, Any]:
    reply: dict[str, Any] = {"schema": 1, "status": status}
    if reason is not None:
        reply["reason"] = reason
    if digest is not None:
        reply["aggregate_digest"] = digest
    return reply | _FALSE
