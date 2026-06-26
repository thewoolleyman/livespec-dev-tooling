"""Tests for `livespec_dev_tooling/fleet/contract.py`.

Covers manifest parsing (valid JSONC with comments through every
malformed shape) and the obligation-table integrity invariants the
two consuming engines rely on.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._reconcile import reconcile_merge_settings
from livespec_dev_tooling.fleet._rows_baseline import assert_baseline_harnesses
from livespec_dev_tooling.fleet._rows_github import assert_merge_settings
from livespec_dev_tooling.fleet._rows_instructions import assert_agent_ai_references_resolve
from livespec_dev_tooling.fleet.contract import (
    OBLIGATION_ROWS,
    REPO_CLASSES,
    Adopter,
    parse_manifest,
    rows_for,
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


def test_obligation_row_ids_are_unique_and_classes_known() -> None:
    row_ids = [row.row_id for row in OBLIGATION_ROWS]
    assert len(set(row_ids)) == len(row_ids)
    for row in OBLIGATION_ROWS:
        assert row.applies_to <= frozenset(REPO_CLASSES), row.row_id
        assert row.obligation_type in {"committed-file", "github-state"}, row.row_id


def test_every_row_is_reconcilable_or_carries_a_manual_hint() -> None:
    for row in OBLIGATION_ROWS:
        assert row.reconcile is not None or row.manual_hint, row.row_id


def test_rows_for_filters_by_class() -> None:
    impl_rows = {row.row_id for row in rows_for(repo_class="impl-plugin")}
    assert "copier-answers" in impl_rows
    assert "dev-tooling-pin" in impl_rows
    enforcement_rows = {row.row_id for row in rows_for(repo_class="enforcement-suite")}
    assert "copier-answers" not in enforcement_rows
    assert "dev-tooling-pin" not in enforcement_rows
    assert "workflow-bump-pin-from-dispatch" in enforcement_rows
    core_rows = {row.row_id for row in rows_for(repo_class="core")}
    assert "copier-answers" not in core_rows
    assert "dev-tooling-pin" in core_rows


def test_universal_rows_apply_to_every_class() -> None:
    universal = {
        "workflow-ci",
        "no-tracked-gitlinks",
        "secret-names",
        "app-installation",
        "branch-protection",
        "merge-settings",
        "topic-livespec-sibling",
    }
    for repo_class in REPO_CLASSES:
        row_ids = {row.row_id for row in rows_for(repo_class=repo_class)}
        assert universal <= row_ids, repo_class


def test_merge_settings_row_is_wired_with_assert_and_reconcile() -> None:
    # The merge-settings row must be registered with BOTH its assert
    # (fleet_conformance, CI mode) and its reconcile (wire-fleet-member),
    # exactly like branch-protection — so a freshly-scaffolded fleet
    # repo's default allow_merge_commit=true is both caught and fixed.
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "merge-settings"), None)
    assert row is not None
    assert row.obligation_type == "github-state"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_merge_settings
    assert row.reconcile is reconcile_merge_settings


def test_agent_ai_references_resolve_row_is_wired_for_every_class() -> None:
    # The .ai/-reference resolvability obligation applies to EVERY member
    # (livespec core itself carries a concrete .ai/ reference), is a
    # committed-file fact, and is not machine-reconcilable from the central
    # vantage point — so it carries a manual hint instead of a reconcile.
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "agent-ai-references-resolve"), None)
    assert row is not None
    assert row.obligation_type == "committed-file"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_agent_ai_references_resolve
    assert row.reconcile is None
    assert row.manual_hint


def test_baseline_harnesses_row_is_wired_for_every_class() -> None:
    # The baseline-harnesses obligation (Conformance Pattern concern #2,
    # cross-harness plugin-resolution) applies to EVERY governed member, is
    # a committed-file fact (the .livespec.jsonc `harnesses` declaration),
    # and is not machine-reconcilable from the central vantage point — so it
    # carries a manual hint instead of a reconcile.
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "baseline-harnesses"), None)
    assert row is not None
    assert row.obligation_type == "committed-file"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_baseline_harnesses
    assert row.reconcile is None
    assert row.manual_hint
