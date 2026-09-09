"""The enablement parse's failure track — `livespec-dev-tooling-qndn.6`.

`enabled_plugin_names` answered `tuple[str, ...] | None`, and that pair of
spellings carried FOUR facts. `()` meant "this settings file enables nothing",
which is a legitimate answer an operator may well intend. `None` meant any one
of three unrelated authoring mistakes in the committed `.claude/settings.json`:
the value is the wrong KIND of JSON, a legacy list carries an entry that is not
a plugin name, or a mapping carries a value that is not an enablement flag.

THE COLLAPSE WAS NOT INERT. Both spellings reach `planned_commands` as "derive
no plugin command", so a settings file nobody could parse planned exactly what
a deliberately-empty one plans, and the only thing separating the two for an
operator was that `settings_findings` happened to re-derive the shape itself.
The three tests naming a `reason` below are what keeps the three mistakes told
apart now that they have somewhere to be told apart IN.

The parse rides `Result` rather than `IOResult` because it performs no I/O: it
is handed the already-decoded settings value. The command seam in the same
module is honestly `IOResult` — it runs subprocesses — and the two are not the
same claim.
"""

from __future__ import annotations

import json

from returns.result import Failure, Success

from livespec_dev_tooling.fleet._ensure_plugin_commands import (
    ENABLEMENT_ENTRY_NOT_A_STRING,
    ENABLEMENT_NOT_A_LIST_OR_MAPPING,
    ENABLEMENT_VALUE_NOT_A_BOOLEAN,
    enabled_plugin_names,
)
from livespec_dev_tooling.fleet.ensure_plugins import planned_commands, settings_findings

__all__: list[str] = []

# The two names `checks/public_api_result_typed` accepts as railway-typed, and
# the terminal-name reduction it applies before comparing. Restated here rather
# than imported so this file pins the PROPERTY the shipped detector reads,
# independently of that module continuing to exist in its current shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})


def _terminal_return_name(*, rendered: str) -> str:
    """`Result[tuple[str, ...], EnablementUnreadable]` → `Result`.

    Mirrors `public_api_result_typed._annotation_head_name`: drop the
    subscript, then drop any dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def test_the_enablement_parse_is_railway_typed() -> None:
    """THE CONVERSION ITSELF: the public answer may not be a bare value.

    `checks/public_api_result_typed` reads a function as on the railway when
    its return annotation's terminal name is `Result` or `IOResult`. That check
    is a NO-OP in this repository — `pure_trees` is declared `not_applicable` —
    so nothing else here would notice a regression to the bare
    `tuple[str, ...] | None` this used to return. This is the arming that
    stands in for it until the scan universe is.
    """
    rendered = str(enabled_plugin_names.__annotations__["return"])

    assert _terminal_return_name(rendered=rendered) in _RAILWAY_RETURN_NAMES, (
        f"enabled_plugin_names must return a Result/IOResult so its failure track is "
        f"expressible; got the bare annotation {rendered!r}"
    )


def test_an_absent_enablement_key_is_a_success_enabling_nothing() -> None:
    """The legitimate absence, which must never share a spelling with a mistake."""
    outcome = enabled_plugin_names(raw=None)

    assert isinstance(outcome, Success)
    assert outcome.unwrap() == ()


def test_a_mapping_answers_with_the_names_it_marks_true_in_file_order() -> None:
    outcome = enabled_plugin_names(
        raw={"one@alpha": True, "off@alpha": False, "two@beta": True},
    )

    assert isinstance(outcome, Success)
    assert outcome.unwrap() == ("one@alpha", "two@beta")


def test_an_all_false_mapping_is_a_success_enabling_nothing() -> None:
    """An explicit disable is an ANSWER, not a shape nobody could read."""
    outcome = enabled_plugin_names(raw={"off@alpha": False})

    assert isinstance(outcome, Success)
    assert outcome.unwrap() == ()


def test_a_legacy_list_answers_with_every_entry_in_file_order() -> None:
    outcome = enabled_plugin_names(raw=["one@alpha", "two@beta"])

    assert isinstance(outcome, Success)
    assert outcome.unwrap() == ("one@alpha", "two@beta")


def test_a_value_that_is_neither_list_nor_mapping_is_the_failure_track() -> None:
    outcome = enabled_plugin_names(raw=7)

    assert isinstance(outcome, Failure)
    assert outcome.failure().reason == ENABLEMENT_NOT_A_LIST_OR_MAPPING
    assert "int" in outcome.failure().detail


def test_a_list_entry_that_is_not_a_string_is_the_failure_track() -> None:
    outcome = enabled_plugin_names(raw=["one@alpha", 7])

    assert isinstance(outcome, Failure)
    assert outcome.failure().reason == ENABLEMENT_ENTRY_NOT_A_STRING
    assert "entry 1" in outcome.failure().detail


def test_a_mapping_value_that_is_not_a_boolean_is_the_failure_track() -> None:
    outcome = enabled_plugin_names(raw={"one@alpha": "yes"})

    assert isinstance(outcome, Failure)
    assert outcome.failure().reason == ENABLEMENT_VALUE_NOT_A_BOOLEAN
    assert "'one@alpha'" in outcome.failure().detail


def test_the_finding_line_names_the_reason_and_the_detail() -> None:
    """What an operator reads: the failure has to say which edit to make."""
    outcome = enabled_plugin_names(raw=["one@alpha", 7])

    assert isinstance(outcome, Failure)
    finding = outcome.failure().finding
    assert ENABLEMENT_ENTRY_NOT_A_STRING in finding
    assert "entry 1" in finding


def test_settings_findings_report_the_unreadable_list_from_the_failure_track() -> None:
    """The caller consumes the TRACK, so the operator sees which entry offended.

    Before the conversion this arm re-derived a fixed line of its own from the
    `None` sentinel, which could name the mistake but never the entry.
    """
    text = json.dumps({"extraKnownMarketplaces": {}, "enabledPlugins": ["one@alpha", 7]})

    findings = settings_findings(settings_text=text)

    assert any(ENABLEMENT_ENTRY_NOT_A_STRING in finding for finding in findings)
    assert any("entry 1" in finding for finding in findings)


def test_planned_commands_derive_no_plugin_command_from_an_unreadable_mapping() -> None:
    """The failure track authorizes no install, and the marketplace half survives.

    `ensure` gates on `settings_findings` before it plans anything, so this arm
    is the defensive one — but planning an install from a value nobody could
    read is the single thing it must not do.
    """
    text = json.dumps(
        {
            "extraKnownMarketplaces": {
                "alpha": {"source": {"source": "github", "repo": "acme/alpha", "ref": "release"}}
            },
            "enabledPlugins": {"one@alpha": "yes"},
        }
    )

    assert planned_commands(settings_text=text) == (
        ("claude", "plugin", "marketplace", "add", "acme/alpha@release"),
    )
