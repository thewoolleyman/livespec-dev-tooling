"""Tests for `livespec_dev_tooling/fleet/contract.py`.

Covers manifest parsing (valid JSONC with comments through every
malformed shape). The obligation-table integrity invariants live in
the sibling `test_contract_rows.py` (central table) and
`test_contract_local_rows.py` (LOCAL-vantage table).

Every rejection is asserted by its `ManifestParseError.reason`, not
merely as "it refused". Before the railway conversion all eight causes
were one `None`, so a test could only assert that SOMETHING was wrong —
which is precisely the bit of information the two fetching engines could
not report to an operator either. Asserting the reason is what stops the
causes silently collapsing back together.
"""

from __future__ import annotations

from returns.result import Failure, Success

from livespec_dev_tooling.fleet.contract import (
    Adopter,
    ManifestParseError,
    ManifestParseReason,
    parse_manifest,
)

__all__: list[str] = []


_VALID_MANIFEST = """\
// .livespec-fleet-manifest.jsonc — header comment survives JSONC parsing.
{
  "owner": "acme",
  "members": [
    { "repo": "livespec", "class": "core" },
    { "repo": "livespec-dev-tooling", "class": "enforcement-suite" },
    { "repo": "livespec-impl-x", "class": "impl-plugin" },
    { "repo": "livespec-driver-y", "class": "driver-plugin" },
    { "repo": "livespec-runtime", "class": "library" }
  ]
}
"""


def test_parse_manifest_accepts_commented_jsonc() -> None:
    outcome = parse_manifest(source=_VALID_MANIFEST)
    assert isinstance(outcome, Success), outcome
    manifest = outcome.unwrap()
    assert manifest.owner == "acme"
    assert [member.repo for member in manifest.members] == [
        "livespec",
        "livespec-dev-tooling",
        "livespec-impl-x",
        "livespec-driver-y",
        "livespec-runtime",
    ]
    assert manifest.members[0].repo_class == "core"
    assert manifest.member_names() == frozenset(
        {
            "livespec",
            "livespec-dev-tooling",
            "livespec-impl-x",
            "livespec-driver-y",
            "livespec-runtime",
        }
    )
    # The legacy `members` manifest carries no `adopters` array, so the
    # absent key parses to an empty tuple (adopters is OPTIONAL).
    assert manifest.adopters == ()


def test_parse_manifest_reads_fleet_key() -> None:
    # The manifest fleet array is read from the `fleet` key (the locked
    # rename of the legacy `members` key); a `fleet`-only manifest with no
    # `members` key parses identically to the legacy form.
    source = """\
{
  "owner": "acme",
  "fleet": [
    { "repo": "livespec", "class": "core" },
    { "repo": "livespec-dev-tooling", "class": "enforcement-suite" }
  ]
}
"""
    outcome = parse_manifest(source=source)
    assert isinstance(outcome, Success), outcome
    manifest = outcome.unwrap()
    assert manifest.owner == "acme"
    assert [member.repo for member in manifest.members] == [
        "livespec",
        "livespec-dev-tooling",
    ]
    assert manifest.members[1].repo_class == "enforcement-suite"
    assert manifest.adopters == ()


def test_parse_manifest_parses_adopters() -> None:
    # A present `adopters` array parses into `Adopter` records; each
    # carries a repo, a non-empty profile of known layers, and a known
    # posture. The two-layer profile exercises the multi-layer loop. Pairs
    # the legacy `members` key with adopters (back-compat + adopters).
    source = """\
{
  "owner": "acme",
  "members": [
    { "repo": "livespec", "class": "core" }
  ],
  "adopters": [
    { "repo": "acme-app", "profile": ["baseline", "fleet-infra"], "posture": "pinned" },
    { "repo": "acme-lib", "profile": ["baseline"], "posture": "released" }
  ]
}
"""
    outcome = parse_manifest(source=source)
    assert isinstance(outcome, Success), outcome
    assert outcome.unwrap().adopters == (
        Adopter(repo="acme-app", profile=("baseline", "fleet-infra"), posture="pinned"),
        Adopter(repo="acme-lib", profile=("baseline",), posture="released"),
    )


# Every malformed shape paired with the reason it MUST report. The pairs
# are the point: the pre-conversion suite asserted `is None` for all of
# them, which passed just as happily when two different causes collapsed
# into one answer.
_MALFORMED: list[tuple[str, ManifestParseReason]] = [
    ("not json at all {{{", "invalid-jsonc"),
    ("[1, 2]", "root-not-object"),
    ('{"members": []}', "owner-not-string"),
    ('{"owner": 7, "members": []}', "owner-not-string"),
    ('{"owner": "acme", "members": "nope"}', "fleet-not-list"),
    # Neither `fleet` nor `members` present: the fallback lands on None,
    # which is not a list.
    ('{"owner": "acme"}', "fleet-not-list"),
    ('{"owner": "acme", "members": ["junk"]}', "malformed-member"),
    ('{"owner": "acme", "members": [{"repo": 7, "class": "core"}]}', "malformed-member"),
    (
        '{"owner": "acme", "members": [{"repo": "x", "class": "unknown-class"}]}',
        "malformed-member",
    ),
    ('{"owner": "acme", "members": [{"repo": "x"}]}', "malformed-member"),
    # adopters present but not a list.
    ('{"owner": "acme", "members": [], "adopters": "nope"}', "adopters-not-list"),
    # adopter entry not an object.
    ('{"owner": "acme", "members": [], "adopters": ["junk"]}', "malformed-adopter"),
    # adopter missing repo.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"profile": ["baseline"], "posture": "none"}]}',
        "malformed-adopter",
    ),
    # adopter repo not a string.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"repo": 7, "profile": ["baseline"], "posture": "none"}]}',
        "malformed-adopter",
    ),
    # adopter repo empty.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"repo": "", "profile": ["baseline"], "posture": "none"}]}',
        "malformed-adopter",
    ),
    # adopter profile not a list.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"repo": "x", "profile": "baseline", "posture": "none"}]}',
        "malformed-adopter",
    ),
    # adopter profile empty.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"repo": "x", "profile": [], "posture": "none"}]}',
        "malformed-adopter",
    ),
    # adopter profile layer not a string.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"repo": "x", "profile": [7], "posture": "none"}]}',
        "malformed-adopter",
    ),
    # adopter profile layer not a known layer.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"repo": "x", "profile": ["bogus"], "posture": "none"}]}',
        "malformed-adopter",
    ),
    # adopter posture not a string.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"repo": "x", "profile": ["baseline"], "posture": 7}]}',
        "malformed-adopter",
    ),
    # adopter posture not a known posture.
    (
        '{"owner": "acme", "members": [], '
        '"adopters": [{"repo": "x", "profile": ["baseline"], "posture": "bogus"}]}',
        "malformed-adopter",
    ),
]


def test_parse_manifest_rejects_malformed_shapes_naming_the_cause() -> None:
    for source, expected_reason in _MALFORMED:
        outcome = parse_manifest(source=source)
        assert isinstance(outcome, Failure), source
        assert outcome.failure() == ManifestParseError(reason=expected_reason), source


def test_parse_manifest_rejects_duplicate_members() -> None:
    source = (
        '{"owner": "acme", "members": ['
        '{"repo": "x", "class": "core"}, {"repo": "x", "class": "library"}]}'
    )
    outcome = parse_manifest(source=source)
    assert isinstance(outcome, Failure), outcome
    # DISTINCT from `malformed-member`, and that distinction is the
    # conversion's whole point here: every entry below is individually
    # well-formed, so "fix the malformed record" is the wrong advice —
    # the list needs deduplicating instead.
    assert outcome.failure() == ManifestParseError(reason="duplicate-member")


def test_every_declared_reason_is_reachable() -> None:
    # A `Literal` reason set is only honest if each member can actually be
    # produced. Without this, adding a reason nobody emits would typecheck,
    # read as coverage, and mean nothing — the uninhabited failure track
    # the ROP triage exists to prevent, arriving one level down in the
    # payload instead of in the signature.
    produced: set[str] = set()
    for source, _ in _MALFORMED:
        outcome = parse_manifest(source=source)
        assert isinstance(outcome, Failure), source
        produced.add(outcome.failure().reason)
    produced.add("duplicate-member")
    assert produced == set(ManifestParseReason.__args__)


def test_absent_adopters_key_is_success_not_failure() -> None:
    # `adopters` is OPTIONAL. The railway must not promote "you did not
    # declare adopters" into an error — the pre-conversion code already
    # got this right (`()` vs `None`) and the conversion preserves it.
    outcome = parse_manifest(source='{"owner": "acme", "members": []}')
    assert isinstance(outcome, Success), outcome
    assert outcome.unwrap().adopters == ()
    assert outcome.unwrap().members == ()


def test_outermost_cause_wins_when_several_are_wrong() -> None:
    # Check ORDER became observable at the conversion: before it, every
    # order produced the same `None`. A manifest that is wrong in two
    # places reports the OUTERMOST cause, so the reader is sent to the
    # thing that has to be fixed first.
    both_wrong = '{"owner": 7, "members": ["junk"]}'
    outcome = parse_manifest(source=both_wrong)
    assert isinstance(outcome, Failure), outcome
    assert outcome.failure() == ManifestParseError(reason="owner-not-string")
