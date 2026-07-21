"""Tests for `livespec_dev_tooling/fleet/_rows_claude_plugin.py`.

The Claude-plugin session-start currency row exercised across its full
outcome lattice — pass, definitive-absence finding, can't-read skip,
truncated-tree skip, unparseable-settings finding, wrapper-mismatch
finding — through a canned-response `FleetContext` (no network, no real
`gh`). The shared canned-context fixtures (`make_context`, `tree_table`,
`_MEMBER`) are imported from `test_rows_files` to avoid duplicating them,
the same cross-test-module pattern `test_rows_files` uses for
`test_ensure_plugins`.
"""

from __future__ import annotations

import json

from test_rows_files import _MEMBER, make_context, tree_table

from livespec_dev_tooling.fleet._context import GhResult, RowFinding, RowPass, RowSkip
from livespec_dev_tooling.fleet._rows_claude_plugin import (
    CLAUDE_SETTINGS,
    assert_claude_plugin_currency,
)

__all__: list[str] = []


_PLUGIN_SETTINGS_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.claude/settings.json?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_PLUGIN_JUSTFILE_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/justfile?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
# The repo-metadata read `canonical_ref` resolves the member's default
# branch from; uncanned, it falls back to `master`.
_REPO_ARGS: tuple[str, ...] = ("api", "repos/acme/widget")

_PLUGIN_SETTINGS = json.dumps(
    {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {"type": "command", "command": "mise exec -- just ensure-plugins"},
                        {"type": "command", "command": 7},
                    ],
                },
                "junk",
                {"matcher": "", "hooks": "not-list"},
                {"matcher": "", "hooks": ["junk"]},
            ]
        }
    }
)
_STANDARD_JUSTFILE = (
    "other:\n"
    "    echo ok\n"
    "ensure-plugins:\n"
    "    # comment\n"
    "\n"
    "    mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins\n"
    "next:\n"
    "    echo done\n"
)


def _plugin_currency_table(
    *,
    paths: list[str],
    settings: str | None = _PLUGIN_SETTINGS,
    justfile: str | None = _STANDARD_JUSTFILE,
    truncated: bool = False,
) -> dict[tuple[str, ...], GhResult]:
    """A canned table for the Claude plugin-currency row."""
    table = tree_table(paths=paths, truncated=truncated)
    if settings is not None:
        table[_PLUGIN_SETTINGS_ARGS] = GhResult(returncode=0, stdout=settings, stderr="")
    if justfile is not None:
        table[_PLUGIN_JUSTFILE_ARGS] = GhResult(returncode=0, stdout=justfile, stderr="")
    return table


def test_claude_plugin_currency_edge_outcomes() -> None:
    cases = [
        ({}, RowSkip, "unreadable"),
        (
            _plugin_currency_table(paths=["README.md"]),
            RowFinding,
            CLAUDE_SETTINGS,
        ),
        (
            _plugin_currency_table(paths=["README.md"], truncated=True),
            RowSkip,
            "truncated",
        ),
        (
            _plugin_currency_table(paths=[CLAUDE_SETTINGS], settings="["),
            RowFinding,
            "parseable",
        ),
        (
            _plugin_currency_table(paths=[CLAUDE_SETTINGS], settings="[]"),
            RowFinding,
            "parseable",
        ),
        (
            _plugin_currency_table(paths=[CLAUDE_SETTINGS], settings=json.dumps({"hooks": []})),
            RowFinding,
            "SessionStart",
        ),
        (
            _plugin_currency_table(paths=[CLAUDE_SETTINGS], settings=None),
            RowSkip,
            CLAUDE_SETTINGS,
        ),
        (
            _plugin_currency_table(paths=[CLAUDE_SETTINGS], justfile=None),
            RowFinding,
            "justfile missing",
        ),
        (
            _plugin_currency_table(paths=[CLAUDE_SETTINGS], justfile=None, truncated=True),
            RowSkip,
            "truncated",
        ),
        (
            _plugin_currency_table(paths=[CLAUDE_SETTINGS, "justfile"], justfile=None),
            RowSkip,
            "justfile unreadable",
        ),
        (
            _plugin_currency_table(paths=[CLAUDE_SETTINGS, "justfile"], justfile="other:\n"),
            RowFinding,
            "standard wrapper",
        ),
    ]
    for table, outcome_type, text in cases:
        outcome = assert_claude_plugin_currency(ctx=make_context(table=table), member=_MEMBER)
        assert isinstance(outcome, outcome_type), text
        detail = outcome.reason if isinstance(outcome, RowSkip) else outcome.message
        assert text in detail
        if isinstance(outcome, RowFinding):
            assert outcome.severity == "error"


def test_claude_plugin_currency_passes_standard_wrapper_with_comments() -> None:
    table = _plugin_currency_table(paths=[CLAUDE_SETTINGS, "justfile"])
    assert assert_claude_plugin_currency(ctx=make_context(table=table), member=_MEMBER) == RowPass()


def test_claude_plugin_unreadable_tree_skip_names_the_canonical_ref() -> None:
    """The skip names the ref the tree read used, never a hardcoded `master`.

    An operator debugging a `main`-default member must not be told the
    read failed on a branch that was never addressed.
    """
    table = {
        _REPO_ARGS: GhResult(returncode=0, stdout=json.dumps({"default_branch": "main"}), stderr="")
    }
    outcome = assert_claude_plugin_currency(ctx=make_context(table=table), member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert outcome.reason == "widget: main tree unreadable"
