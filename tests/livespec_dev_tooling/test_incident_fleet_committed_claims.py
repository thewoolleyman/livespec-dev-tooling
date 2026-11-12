"""The committed incident fleet claims are exactly the ones read from the fleet, and still bind.

`load_claims` refuses a malformed file; these assertions hold the committed file to the
fields its Definition of Done names (livespec-dev-tooling-v46q5g): every claim states a
disposition, an owner, a proof reference and the release build its consumer is expected
to serve, for a known surface, at most once per consumer and surface.

They also pin the claim set itself. The fixture is livespec core's
`.livespec-fleet-manifest.jsonc` (sha256 59912fe1…), the identity the audit binds to: the
audit hashes the manifest text it reads from core's master with the same digest used
here. A claim added, removed, bound to another manifest identity, held by a repository
that is not an applicable consumer of that manifest, or naming a disposition or release
build other than the pinned ones fails this test. Refresh a claim from a new
read of the fleet, then update its tag and commit here.
"""

from __future__ import annotations

import re
from pathlib import Path

from returns.result import Success

from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling._incident_fleet_command import _applicable_consumers, _digest
from livespec_dev_tooling._incident_fleet_sources import COMMITTED_CLAIMS, load_claims
from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence
from livespec_dev_tooling.fleet.contract import parse_manifest
from livespec_dev_tooling.incident_fleet_audit import SURFACES

_DISPOSITIONS = {"implemented", "deliberately-normal", "not-applicable"}
_MANIFEST = Path(__file__).parent / "fixtures" / "incident_fleet" / "core-fleet-manifest.jsonc"
_RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_OWNER = "thewoolleyman"

_SELF = f"{_OWNER}/livespec-dev-tooling"
_T197 = "a8360faf87c6d374d42ea2cccbb4807832667d45"
_T195 = "d4b723761270091517e83dd3ac5d5db48e9f2205"
_NA = "not-applicable"
_IDENTITY = "59912fe1d3cad2938389deba186b0478759f0278be2bfea462c20a39d2a9054c"
# (repository, surface) -> (disposition, this library's release tag, the commit that tag names).
_EXPECTED_CLAIMS: dict[tuple[str, str], tuple[str, str, str]] = {
    (_SELF, "Generated projects"): (_NA, "v1.198.0", "a17a87b18d934dbfb7953f4d2209badc7d6dcee4"),
    (f"{_OWNER}/livespec-console-beads-fabro", "Generated projects"): (_NA, "v1.197.0", _T197),
    (f"{_OWNER}/livespec-driver-claude", "Generated projects"): (_NA, "v1.197.0", _T197),
    (f"{_OWNER}/livespec-driver-codex", "Generated projects"): (_NA, "v1.197.0", _T197),
    (f"{_OWNER}/livespec-driver-pi", "Generated projects"): (_NA, "v1.197.0", _T197),
    (f"{_OWNER}/livespec-overseer", "Generated projects"): (_NA, "v1.197.0", _T197),
    (f"{_OWNER}/livespec-runtime", "Generated projects"): (_NA, "v1.197.0", _T197),
    (f"{_OWNER}/hetzner-xubuntu-info", "Focused test selection"): (_NA, "v1.195.0", _T195),
    (f"{_OWNER}/hetzner-xubuntu-info", "Touched-file coverage"): (_NA, "v1.195.0", _T195),
    (f"{_OWNER}/hetzner-xubuntu-info", "Full coverage producers/consumers"): (
        _NA,
        "v1.195.0",
        _T195,
    ),
}


def _serving_form(*, repository: str, surface: str, tag: str, commit: str) -> str:
    """The release build as the surface's serving reader prints it for that release.

    This library serves its own gate readers and templates, so its rows are release-keyed
    and a claim names the tag itself; another consumer's templates read as this library's
    commit, prefixed, and its gate readers as the bare commit its `.venv` records.
    """
    if repository == _SELF:
        return tag
    if SURFACE_CAPABILITY[surface] == "templates":
        return f"livespec-dev-tooling@{commit}"
    return commit


def _claims() -> tuple[CapabilityEvidence, ...]:
    loaded = load_claims(path=COMMITTED_CLAIMS)
    assert isinstance(loaded, Success)
    return loaded.unwrap()


def test_every_committed_claim_names_disposition_owner_proof_and_release_build() -> None:
    claims = _claims()
    keys = [(claim.repository, claim.surface) for claim in claims]
    facts = (
        len(claims) > 0,
        len(set(keys)) == len(keys),
        all(claim.surface in SURFACES for claim in claims),
        all(claim.disposition in _DISPOSITIONS for claim in claims),
        all(claim.owner and claim.proof_ref and claim.release_build for claim in claims),
        all(claim.source_path and len(claim.manifest_sha256) == 64 for claim in claims),
        all(claim.reason for claim in claims if claim.disposition != "implemented"),
        all(claim.repository in claim.proof_ref for claim in claims),
    )
    assert all(facts)


def test_the_committed_claim_set_is_exactly_the_pinned_one() -> None:
    keys = [(claim.repository, claim.surface) for claim in _claims()]
    assert sorted(keys) == sorted(_EXPECTED_CLAIMS)


def test_every_claim_binds_the_committed_manifest_identity_and_one_of_its_consumers() -> None:
    text = _MANIFEST.read_text(encoding="utf-8")
    manifest = parse_manifest(source=text)
    assert isinstance(manifest, Success)
    consumers = set(_applicable_consumers(manifest=manifest.unwrap()))
    identity = _digest(text=text)
    assert identity == _IDENTITY
    for claim in _claims():
        assert claim.manifest_sha256 == identity, claim.repository
        assert claim.repository in consumers, claim.repository


def test_every_claim_carries_its_pinned_disposition_and_release_build() -> None:
    for claim in _claims():
        disposition, tag, commit = _EXPECTED_CLAIMS[(claim.repository, claim.surface)]
        assert claim.disposition == disposition, (claim.repository, claim.surface)
        assert _RELEASE_TAG.fullmatch(tag) is not None
        assert _COMMIT.fullmatch(commit) is not None
        expected = _serving_form(
            repository=claim.repository, surface=claim.surface, tag=tag, commit=commit
        )
        assert claim.release_build == expected, (claim.repository, claim.surface)
