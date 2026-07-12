"""Tests for `livespec_dev_tooling/fleet/contract.py`.

Covers manifest parsing (valid JSONC with comments through every
malformed shape). The obligation-table integrity invariants live in
the sibling `test_contract_rows.py` (central table) and
`test_contract_local_rows.py` (LOCAL-vantage table).
"""

from __future__ import annotations

from livespec_dev_tooling.fleet.contract import Adopter, parse_manifest

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
    manifest = parse_manifest(source=_VALID_MANIFEST)
    assert manifest is not None
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
    manifest = parse_manifest(source=source)
    assert manifest is not None
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
    manifest = parse_manifest(source=source)
    assert manifest is not None
    assert manifest.adopters == (
        Adopter(repo="acme-app", profile=("baseline", "fleet-infra"), posture="pinned"),
        Adopter(repo="acme-lib", profile=("baseline",), posture="released"),
    )


def test_parse_manifest_rejects_malformed_shapes() -> None:
    malformed = [
        "not json at all {{{",
        "[1, 2]",
        '{"members": []}',
        '{"owner": 7, "members": []}',
        '{"owner": "acme", "members": "nope"}',
        '{"owner": "acme", "members": ["junk"]}',
        '{"owner": "acme", "members": [{"repo": 7, "class": "core"}]}',
        '{"owner": "acme", "members": [{"repo": "x", "class": "unknown-class"}]}',
        '{"owner": "acme", "members": [{"repo": "x"}]}',
        # adopters present but not a list.
        '{"owner": "acme", "members": [], "adopters": "nope"}',
        # adopter entry not an object.
        '{"owner": "acme", "members": [], "adopters": ["junk"]}',
        # adopter missing repo.
        '{"owner": "acme", "members": [], "adopters": [{"profile": ["baseline"], "posture": "none"}]}',
        # adopter repo not a string.
        '{"owner": "acme", "members": [], "adopters": [{"repo": 7, "profile": ["baseline"], "posture": "none"}]}',
        # adopter repo empty.
        '{"owner": "acme", "members": [], "adopters": [{"repo": "", "profile": ["baseline"], "posture": "none"}]}',
        # adopter profile not a list.
        '{"owner": "acme", "members": [], "adopters": [{"repo": "x", "profile": "baseline", "posture": "none"}]}',
        # adopter profile empty.
        '{"owner": "acme", "members": [], "adopters": [{"repo": "x", "profile": [], "posture": "none"}]}',
        # adopter profile layer not a string.
        '{"owner": "acme", "members": [], "adopters": [{"repo": "x", "profile": [7], "posture": "none"}]}',
        # adopter profile layer not a known layer.
        '{"owner": "acme", "members": [], "adopters": [{"repo": "x", "profile": ["bogus"], "posture": "none"}]}',
        # adopter posture not a string.
        '{"owner": "acme", "members": [], "adopters": [{"repo": "x", "profile": ["baseline"], "posture": 7}]}',
        # adopter posture not a known posture.
        '{"owner": "acme", "members": [], "adopters": [{"repo": "x", "profile": ["baseline"], "posture": "bogus"}]}',
    ]
    for source in malformed:
        assert parse_manifest(source=source) is None, source


def test_parse_manifest_rejects_duplicate_members() -> None:
    source = (
        '{"owner": "acme", "members": ['
        '{"repo": "x", "class": "core"}, {"repo": "x", "class": "library"}]}'
    )
    assert parse_manifest(source=source) is None
