"""Canned-context tests for the foreman-valve-disposition declaration row.

Exercises `assert_foreman_valve_declared` against a canned-response
`FleetContext` (no network, no real `gh`), mirroring the sibling
`test_rows_decision_authority` pattern.

WHAT THIS ROW ASSERTS, and the distinction is the whole design: the member
DECLARES `livespec-overseer.foreman_valve_disposition` explicitly. It does NOT
mandate which value. A repo may deliberately choose `report-only`; what it may
not do is arrive there SILENTLY by omitting the key, because the resolver
fail-closes to `report-only` and nothing surfaces that it did.

That silent default is the measured failure. On 2026-08-21 only 5 of 14
governed repos declared the key, and the other 9 had been surfacing every human
valve and acting on none of them for weeks. A live foreman reported its own
disposition as `configured: null, source: default` while a picker it had
surfaced sat over two hours. Nobody had chosen `report-only` for those repos —
they had simply never chosen anything.

BOTH DIRECTIONS ARE CONTROLLED HERE, and a third case that a presence-only test
would wave through: `_TYPO_CONFIG` declares a value the resolver does not
recognize. That silently falls back to `report-only` exactly like omission, so
it must be a finding too — a check that accepted it would report a repo as
compliant while it ran on the default it was written to prevent.
"""

from __future__ import annotations

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_foreman_valve import (
    assert_foreman_valve_declared,
    declared_valve_disposition,
    parsed_config,
)

__all__: list[str] = []

_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_CONFIG_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.livespec.jsonc?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)

# Declared, in the shape the fleet actually landed on 2026-08-21: a top-level
# `livespec-overseer` object carrying the key, with jsonc comments around it.
_DECLARED_CONFIG = "\n".join(
    (
        "{",
        "  // Foreman human-valve disposition.",
        '  "livespec-overseer": { "foreman_valve_disposition": "consensus" },',
        '  "template": "livespec"',
        "}",
    )
)

# Declared as report-only. A DELIBERATE choice, and it MUST pass: this row
# judges whether the repo chose, not what it chose.
_REPORT_ONLY_CONFIG = "\n".join(
    (
        "{",
        '  "livespec-overseer": { "foreman_valve_disposition": "report-only" },',
        '  "template": "livespec"',
        "}",
    )
)

# The failure this row exists to catch: no key at all, so the resolver
# fail-closes to report-only and nothing says so.
_UNDECLARED_CONFIG = "\n".join(
    (
        "{",
        '  "template": "livespec",',
        '  "spec_root": "SPECIFICATION"',
        "}",
    )
)

# Present but unrecognized. Falls back to report-only just like omission.
_TYPO_CONFIG = "\n".join(
    (
        "{",
        '  "livespec-overseer": { "foreman_valve_disposition": "concensus" },',
        '  "template": "livespec"',
        "}",
    )
)

# The nesting the resolver also honours: the bare top-level key.
_TOP_LEVEL_KEY_CONFIG = "\n".join(
    (
        "{",
        '  "foreman_valve_disposition": "consensus",',
        '  "template": "livespec"',
        "}",
    )
)


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def _ok(*, stdout: str) -> GhResult:
    return GhResult(returncode=0, stdout=stdout, stderr="")


def test_a_member_declaring_consensus_passes() -> None:
    ctx = make_context(table={_CONFIG_ARGS: _ok(stdout=_DECLARED_CONFIG)})
    assert assert_foreman_valve_declared(ctx=ctx, member=_MEMBER) == RowPass()


def test_a_member_deliberately_declaring_report_only_also_passes() -> None:
    """The row judges whether the repo CHOSE, never which value it chose."""
    ctx = make_context(table={_CONFIG_ARGS: _ok(stdout=_REPORT_ONLY_CONFIG)})
    assert assert_foreman_valve_declared(ctx=ctx, member=_MEMBER) == RowPass()


def test_a_member_with_no_declaration_is_a_finding_naming_the_repo() -> None:
    ctx = make_context(table={_CONFIG_ARGS: _ok(stdout=_UNDECLARED_CONFIG)})
    outcome = assert_foreman_valve_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.message.startswith("widget: ")
    assert "foreman_valve_disposition" in outcome.message


def test_an_unrecognized_value_is_a_finding_because_it_falls_back_silently() -> None:
    ctx = make_context(table={_CONFIG_ARGS: _ok(stdout=_TYPO_CONFIG)})
    outcome = assert_foreman_valve_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "concensus" in outcome.message


def test_the_bare_top_level_key_is_honoured_like_the_resolver_does() -> None:
    assert declared_valve_disposition(config_text=_TOP_LEVEL_KEY_CONFIG) == "consensus"


def test_an_absent_declaration_reads_as_none_rather_than_a_default() -> None:
    assert declared_valve_disposition(config_text=_UNDECLARED_CONFIG) is None


def test_a_config_whose_root_is_not_an_object_reads_as_unparseable() -> None:
    """Valid JSON that is not an object cannot carry the key and must not
    be mistaken for a repo that merely omitted it."""
    assert parsed_config(config_text="[1, 2, 3]") is None


def test_declared_valve_disposition_reads_none_for_unparseable_text() -> None:
    """`None` here is deliberately ambiguous between absent and unparseable;
    the row separates the two by calling `parsed_config` itself."""
    assert declared_valve_disposition(config_text="{ not json at all") is None


def test_unparseable_config_skips_rather_than_finding() -> None:
    ctx = make_context(table={_CONFIG_ARGS: _ok(stdout="{ not json at all")})
    outcome = assert_foreman_valve_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "widget" in outcome.reason


def test_unreadable_config_skips_rather_than_finding() -> None:
    ctx = make_context(table={})
    outcome = assert_foreman_valve_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "widget" in outcome.reason
