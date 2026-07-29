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

The acceptance-mode row is the module's second declaration obligation. It
asserts the member DECLARES `dispatcher.acceptance_mode` explicitly, not
that it declares any particular value: a repo that deliberately chooses
`ai-then-human` still passes, while a repo that says nothing does not. The
distinction is the whole point — the resolver's default is
`ai-then-human`, so silence is indistinguishable from a choice, which is
how five governed repos drifted off the fleet standard un-noticed.
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
    ACCEPTANCE_MODES,
    LIVESPEC_JSONC_PATH,
    assert_acceptance_mode_declared,
    assert_baseline_harnesses,
)

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_JSONC_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.livespec.jsonc?ref=master",
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


def test_genuine_master_absence_finds_even_when_default_branch_carries_the_file() -> None:
    # Hardening for a non-master-default member (livespec-esac): the guard pins
    # BOTH the file read and the tree read to the canonical `master` ref, so a
    # copy on the member's DEFAULT branch cannot mask a genuine `master` absence.
    # Here .livespec.jsonc EXISTS (harnesses-bearing) on the default branch — the
    # no-`?ref=` contents path — but the canonical master tree genuinely LACKS it:
    # the outcome MUST be the vacuous-pass-closure FINDING (zs22.8 M3), not the
    # skip the default-branch copy would yield if file_text read a different ref
    # than tree (file_text used to read the repo DEFAULT branch; tree pins master).
    default_branch_jsonc_args = (
        "api",
        "repos/acme/widget/contents/.livespec.jsonc",
        "-H",
        "Accept: application/vnd.github.raw",
    )
    jsonc = (
        "{\n"
        '  "harnesses": {\n'
        '    "claude": { "status": "supported", "canonical_command": "widget:next" }\n'
        "  }\n"
        "}\n"
    )
    ctx = make_context(
        table={
            default_branch_jsonc_args: _ok(text=jsonc),
            _TREE_ARGS: _tree(paths=("README.md", "justfile")),
        }
    )
    outcome = assert_baseline_harnesses(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert ".livespec.jsonc" in outcome.message


def _config(*, plugin: str = '"acme-orchestrator"', block: str = "") -> str:
    """A `.livespec.jsonc` naming an impl plugin, with `block` as that plugin's body."""
    return (
        "// hermetic test config\n"
        "{\n"
        f'  "implementation": {{ "plugin": {plugin} }},\n'
        f'  "acme-orchestrator": {{{block}}}\n'
        "}\n"
    )


def test_acceptance_modes_are_the_three_resolver_policies() -> None:
    # Lockstep with `_dispatcher_policy_settings._ACCEPTANCE_POLICIES`: a value
    # outside this set is not a choice, it silently falls back to the default.
    assert frozenset({"ai-only", "ai-then-human", "human-only"}) == ACCEPTANCE_MODES


def test_declared_acceptance_mode_passes() -> None:
    jsonc = _config(block='\n    "dispatcher": { "acceptance_mode": "ai-only" }\n  ')
    ctx = make_context(table={_JSONC_ARGS: _ok(text=jsonc)})
    assert assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER) == RowPass()


def test_deliberate_non_fleet_standard_value_still_passes() -> None:
    # The row asserts DECLARATION, never a particular value. A repo that
    # deliberately chooses `ai-then-human` (as livespec-console-beads-fabro did
    # on 2026-07-21, with a recorded reason) must not be forced off its choice
    # by a check whose purpose is only to make SILENCE impossible.
    jsonc = _config(block='\n    "dispatcher": { "acceptance_mode": "ai-then-human" }\n  ')
    ctx = make_context(table={_JSONC_ARGS: _ok(text=jsonc)})
    assert assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER) == RowPass()


def test_dispatcher_block_without_acceptance_mode_is_error_finding() -> None:
    jsonc = _config(block='\n    "dispatcher": { "wip_cap": 5 }\n  ')
    ctx = make_context(table={_JSONC_ARGS: _ok(text=jsonc)})
    outcome = assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "widget" in outcome.message
    assert "acceptance_mode" in outcome.message


def test_absent_dispatcher_block_is_error_finding() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text=_config())})
    outcome = assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"


def test_unknown_acceptance_mode_value_is_error_finding() -> None:
    # The resolver accepts only the three known policies and silently returns
    # its default for anything else, so a typo reads as a declaration while
    # behaving as an omission. That is the exact failure this row exists for.
    jsonc = _config(block='\n    "dispatcher": { "acceptance_mode": "ai_only" }\n  ')
    ctx = make_context(table={_JSONC_ARGS: _ok(text=jsonc)})
    outcome = assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "ai_only" in outcome.message


def test_missing_implementation_plugin_is_error_finding_not_a_vacuous_skip() -> None:
    # No impl-plugin block means the dispatcher settings have no home at all.
    # Skipping here would be a vacuous pass: dropping `implementation.plugin`
    # would silently buy exemption from the row.
    ctx = make_context(table={_JSONC_ARGS: _ok(text='{\n  "template": "livespec"\n}\n')})
    outcome = assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "implementation.plugin" in outcome.message


def test_named_plugin_block_absent_is_error_finding() -> None:
    # `implementation.plugin` names a block the document does not carry, so the
    # dispatcher settings have nowhere to live.
    jsonc = '{\n  "implementation": { "plugin": "acme-orchestrator" }\n}\n'
    ctx = make_context(table={_JSONC_ARGS: _ok(text=jsonc)})
    outcome = assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"


def test_non_object_dispatcher_is_error_finding() -> None:
    jsonc = _config(block='\n    "dispatcher": "nope"\n  ')
    ctx = make_context(table={_JSONC_ARGS: _ok(text=jsonc)})
    outcome = assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"


def test_non_string_implementation_plugin_is_error_finding() -> None:
    jsonc = '{\n  "implementation": { "plugin": 7 }\n}\n'
    ctx = make_context(table={_JSONC_ARGS: _ok(text=jsonc)})
    outcome = assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"


def test_acceptance_mode_row_skips_unparseable_config() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text="{ not valid json ::: ")})
    assert isinstance(assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER), RowSkip)


def test_acceptance_mode_row_skips_non_object_root() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text="[1, 2, 3]\n")})
    assert isinstance(assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER), RowSkip)


def test_acceptance_mode_row_skips_when_absence_is_unprovable() -> None:
    # can't-read-is-not-absent, shared with the harnesses row.
    ctx = make_context(table={})
    assert isinstance(assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER), RowSkip)


def test_acceptance_mode_row_reports_genuinely_absent_config() -> None:
    ctx = make_context(table={_TREE_ARGS: _tree(paths=("README.md", "justfile"))})
    outcome = assert_acceptance_mode_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert ".livespec.jsonc" in outcome.message
