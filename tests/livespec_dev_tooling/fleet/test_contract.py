"""Tests for `livespec_dev_tooling/fleet/contract.py`.

Covers manifest parsing (valid JSONC with comments through every
malformed shape) and the obligation-table integrity invariants the
two consuming engines rely on.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet.contract import (
    OBLIGATION_ROWS,
    REPO_CLASSES,
    parse_manifest,
    rows_for,
)

__all__: list[str] = []


_VALID_MANIFEST = """\
// fleet-manifest.jsonc — header comment survives JSONC parsing.
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
        "topic-livespec-sibling",
    }
    for repo_class in REPO_CLASSES:
        row_ids = {row.row_id for row in rows_for(repo_class=repo_class)}
        assert universal <= row_ids, repo_class
