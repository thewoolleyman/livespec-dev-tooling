"""The committed incident fleet claims are well formed and bind the committed manifest identity.

`load_claims` refuses a malformed file. These assertions hold every claim to the fields its
Definition of Done names (livespec-dev-tooling-v46q5g): a known surface at most once per
consumer, a disposition, an owner, a proof reference naming its repository, a reason unless
implemented, an implemented claim's incident record, and a release build in the serving form
its capability prints. This library's own rows are release-keyed, so they name a tag. Another
consumer's templates read as this library's commit, prefixed. Its gate readers read as a bare
commit. Every claim also binds the committed manifest identity and one of its applicable
consumers. The fixture is livespec core's `.livespec-fleet-manifest.jsonc` (sha256 59912fe1…),
which the audit hashes with the same digest.

No test here names a claim's VALUE (livespec-dev-tooling-bqnzcm.1): a claim is refreshed
from a new read of the fleet, and the audit is what judges it against the build read. The
same checks run on a fixture claims file, so each check is shown to refuse what it guards.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from returns.result import Success

from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling._incident_fleet_command import _applicable_consumers, _digest
from livespec_dev_tooling._incident_fleet_sources import COMMITTED_CLAIMS, load_claims
from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence
from livespec_dev_tooling.fleet.contract import parse_manifest
from livespec_dev_tooling.incident_fleet_audit import SURFACES

_FIXTURES = Path(__file__).parent / "fixtures" / "incident_fleet"
_MANIFEST = _FIXTURES / "core-fleet-manifest.jsonc"
_WELLFORMED = _FIXTURES / "claims-wellformed.json"
_DISPOSITIONS = {"implemented", "deliberately-normal", "not-applicable"}
_RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_SELF = "thewoolleyman/livespec-dev-tooling"


def _serving_form_ok(*, claim: CapabilityEvidence) -> bool:
    if claim.repository == _SELF:
        return _RELEASE_TAG.fullmatch(claim.release_build) is not None
    capability = SURFACE_CAPABILITY.get(claim.surface)
    if capability == "templates":
        prefix, _, commit = claim.release_build.partition("@")
        return prefix == "livespec-dev-tooling" and _COMMIT.fullmatch(commit) is not None
    if capability == "gate-readers":
        return _COMMIT.fullmatch(claim.release_build) is not None
    return bool(claim.release_build)


def _claim_failures(*, claim: CapabilityEvidence, consumers: set[str], identity: str) -> list[str]:
    implemented = claim.disposition == "implemented"
    checks = {
        "unknown-surface": claim.surface in SURFACES,
        "unknown-disposition": claim.disposition in _DISPOSITIONS,
        "missing-field": all(
            (claim.owner, claim.proof_ref, claim.release_build, claim.source_path)
        ),
        "proof-ref-omits-repository": claim.repository in claim.proof_ref,
        "missing-reason": implemented or bool(claim.reason),
        "missing-incident-record": not implemented
        or bool(
            claim.incident_item
            and claim.normal_factory_proof
            and _DIGEST.fullmatch(claim.cumulative_scope)
        ),
        "release-build-not-serving-form": _serving_form_ok(claim=claim),
        "other-manifest-identity": claim.manifest_sha256 == identity,
        "not-an-applicable-consumer": claim.repository in consumers,
    }
    return [f"{claim.repository} {claim.surface}: {name}" for name, ok in checks.items() if not ok]


def _failures(*, claims: Sequence[CapabilityEvidence]) -> list[str]:
    text = _MANIFEST.read_text(encoding="utf-8")
    manifest = parse_manifest(source=text)
    assert isinstance(manifest, Success)
    consumers = set(_applicable_consumers(manifest=manifest.unwrap()))
    identity = _digest(text=text)
    keys = [(claim.repository, claim.surface) for claim in claims]
    found = [f"{key[0]} {key[1]}: duplicate" for key in sorted(set(keys)) if keys.count(key) > 1]
    for claim in claims:
        found += _claim_failures(claim=claim, consumers=consumers, identity=identity)
    return found


def _load(*, path: Path) -> tuple[CapabilityEvidence, ...]:
    loaded = load_claims(path=path)
    assert isinstance(loaded, Success)
    return loaded.unwrap()


def test_the_committed_claims_are_well_formed_and_bind_the_manifest() -> None:
    claims = _load(path=COMMITTED_CLAIMS)
    assert len(claims) > 0
    assert _failures(claims=claims) == []


def test_the_wellformed_fixture_passes_every_check() -> None:
    assert _failures(claims=_load(path=_WELLFORMED)) == []


_BROKEN: list[tuple[int, dict[str, str], str]] = [
    (1, {"surface": "No such surface"}, "unknown-surface"),
    (1, {"disposition": "maybe"}, "unknown-disposition"),
    (1, {"owner": ""}, "missing-field"),
    (1, {"proof_ref": "fixture: read for a test"}, "proof-ref-omits-repository"),
    (1, {"reason": ""}, "missing-reason"),
    (0, {"cumulative_scope": "not-a-digest"}, "missing-incident-record"),
    (
        0,
        {"release_build": "1111111111111111111111111111111111111111"},
        "release-build-not-serving-form",
    ),
    (1, {"release_build": "v1.0.0"}, "release-build-not-serving-form"),
    (2, {"release_build": "v1.0.0"}, "release-build-not-serving-form"),
    (1, {"manifest_sha256": "f" * 64}, "other-manifest-identity"),
    (
        1,
        {"repository": "thewoolleyman/not-a-consumer", "proof_ref": "thewoolleyman/not-a-consumer"},
        "not-an-applicable-consumer",
    ),
]


@pytest.mark.parametrize(("index", "change", "failure"), _BROKEN)
def test_each_check_refuses_a_fixture_claim_that_breaks_it(
    tmp_path: Path, index: int, change: dict[str, str], failure: str
) -> None:
    document = json.loads(_WELLFORMED.read_text(encoding="utf-8"))
    document["evidence"][index].update(change)
    broken = tmp_path / "claims.json"
    broken.write_text(json.dumps(document), encoding="utf-8")
    failures = _failures(claims=_load(path=broken))
    assert [entry.rsplit(": ", 1)[1] for entry in failures] == [failure]


def test_a_repeated_consumer_and_surface_is_refused(tmp_path: Path) -> None:
    document = json.loads(_WELLFORMED.read_text(encoding="utf-8"))
    document["evidence"].append(dict(document["evidence"][1]))
    repeated = tmp_path / "claims.json"
    repeated.write_text(json.dumps(document), encoding="utf-8")
    assert _failures(claims=_load(path=repeated)) == [
        "thewoolleyman/livespec-driver-claude Generated projects: duplicate"
    ]
