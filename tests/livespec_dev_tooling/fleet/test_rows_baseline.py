"""Tests for `livespec_dev_tooling/fleet/_rows_baseline.py`.

The baseline-harnesses row asserts that a governed member declares a
non-empty top-level `harnesses` object in `.livespec.jsonc` (the
Conformance Pattern's cross-harness plugin-resolution concern, concern
#2). It reports at ERROR severity (the M6-g required-key flip): the
declaration is required fleet-wide, so an un-declared member is a hard
fleet-conformance failure. Exercised across pass (a non-empty harnesses
object), error-finding (harnesses absent / empty / not an object), and
skip (file unreadable, unparseable, or non-object root) through a
canned-response `FleetContext` (no network, no real `gh`).
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_baseline import (
    LIVESPEC_JSONC_PATH,
    assert_baseline_harnesses,
)

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_JSONC_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.livespec.jsonc",
    "-H",
    "Accept: application/vnd.github.raw",
)
_TREE_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/git/trees/master?recursive=1",
)


def _tree(*, paths: tuple[str, ...], truncated: bool = False) -> GhResult:
    """A canned `git/trees` payload listing `paths` (each a regular blob)."""
    entries = ", ".join(f'{{"path": "{p}", "mode": "100644"}}' for p in paths)
    truncated_json = "true" if truncated else "false"
    return _ok(text=f'{{"truncated": {truncated_json}, "tree": [{entries}]}}')


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def _ok(*, text: str) -> GhResult:
    return GhResult(returncode=0, stdout=text, stderr="")


def test_path_constant_points_at_livespec_jsonc() -> None:
    assert LIVESPEC_JSONC_PATH == ".livespec.jsonc"


def test_declared_harnesses_object_passes() -> None:
    jsonc = (
        "// hermetic test config\n"
        "{\n"
        '  "template": "livespec",\n'
        '  "harnesses": {\n'
        '    "claude": { "status": "supported", "canonical_command": "widget:next" }\n'
        "  }\n"
        "}\n"
    )
    ctx = make_context(table={_JSONC_ARGS: _ok(text=jsonc)})
    assert assert_baseline_harnesses(ctx=ctx, member=_MEMBER) == RowPass()


def test_absent_harnesses_is_error_finding_naming_the_member() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text='{\n  "template": "livespec"\n}\n')})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "widget" in outcome.message
    assert "harnesses" in outcome.message


def test_empty_harnesses_object_is_error_finding() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text='{\n  "harnesses": {}\n}\n')})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"


def test_non_object_harnesses_is_error_finding() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text='{\n  "harnesses": "nope"\n}\n')})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"


def test_missing_file_with_unreadable_tree_skips() -> None:
    # Empty table: both the contents read AND the tree read fail (returncode 1),
    # so the tree is unreadable — can't-read is not absent → SKIP.
    ctx = make_context(table={})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "widget" in outcome.reason


def test_genuinely_absent_livespec_jsonc_is_error_finding() -> None:
    # The contents read fails (no _JSONC_ARGS canned) but the master tree IS
    # readable and does NOT list .livespec.jsonc — genuine absence, the
    # vacuous-pass hole (zs22.8 M3). A governed manifest member with no config
    # is a FINDING, not a skip.
    ctx = make_context(table={_TREE_ARGS: _tree(paths=("README.md", "justfile"))})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "widget" in outcome.message
    assert ".livespec.jsonc" in outcome.message


def test_present_file_unreadable_contents_skips() -> None:
    # The master tree lists .livespec.jsonc (the file exists) but the contents
    # read fails transiently — can't-read is not absent → SKIP, not a finding.
    ctx = make_context(table={_TREE_ARGS: _tree(paths=("README.md", ".livespec.jsonc"))})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)


def test_absent_file_with_truncated_tree_skips() -> None:
    # A truncated tree cannot prove absence (the missing path may have been
    # dropped by truncation) — inconclusive → SKIP.
    ctx = make_context(table={_TREE_ARGS: _tree(paths=("README.md",), truncated=True)})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)


def test_unparseable_livespec_jsonc_skips() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text="{ this is not valid json ::: ")})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)


def test_non_object_root_skips() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text="[1, 2, 3]\n")})
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
