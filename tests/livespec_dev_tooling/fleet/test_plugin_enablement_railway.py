"""`enabled_plugin_names` — the enablement PARSER's failure track (qndn cluster 7).

The plugin seam's OTHER conversion. `livespec-dev-tooling-6e83` put the
INVOCATION half of `_ensure_plugin_commands` on the railway — a command that
never ran stopped being a fabricated `returncode=127`. The PARSING half kept
its own sentinel: `enabled_plugin_names` answered every malformed
`enabledPlugins` value with `None`, the same word it uses for nothing at all
being wrong.

THE SENTINEL COLLAPSED THREE CONDITIONS THAT CALL FOR THREE DIFFERENT EDITS to
`.claude/settings.json`, and told the operator which one it was in NONE of
them:

- the value is not a collection at all (`"enabledPlugins": 7`),
- it is a list holding something that is not a plugin name (`[7]`),
- it is a mapping holding something that is not an enable flag (`{"p": "yes"}`).

And the two answers stayed apart from the failure only by CONVENTION: `()` —
"there is no enablement, and that is fine" — is a legitimate answer that a
caller must not confuse with "the enablement is unreadable". `Success(())` and
a `Failure` cannot be confused; `()` and `None` differ by one `is None` arm
somebody has to remember to write, and `not ()` and `not None` are both true.

⛔ `check-public-api-result-typed` IS A NO-OP IN THIS REPOSITORY —
`pure_trees` is declared `not_applicable`, so the role-absence gate returns
before the scan — which means nothing mechanical would notice a regression to
the bare `tuple[str, ...] | None`. `test_the_public_answer_is_railway_typed`
is the arming that stands in for it until the scan universe is, and it reads
the property through the SHIPPED detector's own terminal-name rule rather than
through a spelling of its own.
"""

from __future__ import annotations

import json

from returns.result import Failure, Success

from livespec_dev_tooling.fleet._ensure_plugin_commands import (
    ENABLEMENT_FLAG_NOT_A_BOOLEAN,
    ENABLEMENT_NAME_NOT_A_STRING,
    ENABLEMENT_NOT_A_COLLECTION,
    PluginEnablementMalformed,
    enabled_plugin_names,
    planned_commands,
)
from livespec_dev_tooling.fleet.ensure_plugins import settings_findings

__all__: list[str] = []

# The two names `checks/public_api_result_typed` accepts as railway-typed, and
# the terminal-name reduction it applies before comparing. Restated here rather
# than imported so this test pins the PROPERTY the shipped detector reads,
# independently of that module continuing to exist in its current shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})


def _terminal_return_name(*, rendered: str) -> str:
    """`Result[tuple[str, ...], PluginEnablementMalformed]` → `Result`.

    Mirrors `public_api_result_typed._annotation_head_name`: drop the
    subscript, then drop any dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def _malformation(*, raw: object) -> PluginEnablementMalformed:
    """The failure `raw` produces, failing loudly if the parser ANSWERED instead.

    A bare `== Failure(...)` would read the same but says nothing when the
    parser succeeds: the assertion reports two opaque containers. This names
    which half went wrong, the way `test_local_context_predicate_railway`'s
    `_answer` does for the other track.
    """
    outcome = enabled_plugin_names(raw=raw)
    assert isinstance(outcome, Failure), f"expected a failure, got an answer: {outcome!r}"
    failure: object = outcome.failure()
    assert isinstance(failure, PluginEnablementMalformed), f"wrong failure type: {failure!r}"
    return failure


def test_an_absent_enablement_is_an_empty_answer_not_a_failure() -> None:
    """ABSENT travels the SUCCESS track — the whole point of the split.

    A settings file that declares no `enabledPlugins` at all is well-formed and
    simply enables nothing. If absence were a failure every marketplace-only
    settings file would report unreadable, which is the fix over-reaching
    rather than working.
    """
    assert enabled_plugin_names(raw=None) == Success(())


def test_a_list_enablement_answers_in_file_order() -> None:
    """The legacy list spelling: every entry is enabled, order preserved."""
    outcome = enabled_plugin_names(raw=["two@beta", "one@alpha"])

    assert isinstance(outcome, Success), f"expected an answer, got a failure: {outcome!r}"
    assert outcome.unwrap() == ("two@beta", "one@alpha")


def test_a_mapping_enablement_answers_only_the_true_keys() -> None:
    """A `false` value is an explicit DISABLE, not an enablement — and not a failure."""
    outcome = enabled_plugin_names(raw={"on@alpha": True, "off@beta": False})

    assert isinstance(outcome, Success), f"expected an answer, got a failure: {outcome!r}"
    assert outcome.unwrap() == ("on@alpha",)


def test_a_value_that_is_not_a_collection_is_a_failure() -> None:
    """`"enabledPlugins": 7` is unreadable, and the failure names the type it saw."""
    failure = _malformation(raw=7)

    assert failure.kind == ENABLEMENT_NOT_A_COLLECTION
    assert "int" in failure.detail


def test_a_list_entry_that_is_not_a_plugin_name_is_a_failure() -> None:
    """The failure names WHICH entry, which the sentinel could not carry at all.

    An operator fixing a long `enabledPlugins` array needs the index; `None`
    sent them to re-read the whole array.
    """
    failure = _malformation(raw=["one@alpha", 7])

    assert failure.kind == ENABLEMENT_NAME_NOT_A_STRING
    assert "entry 1" in failure.detail


def test_a_flag_that_is_not_a_boolean_is_a_failure() -> None:
    """The failure names WHICH key, for the same reason the list failure names the index.

    `"yes"` is the shape this actually takes in the field — a hand-edited
    settings file quoting what looks like a boolean.
    """
    failure = _malformation(raw={"one@alpha": "yes"})

    assert failure.kind == ENABLEMENT_FLAG_NOT_A_BOOLEAN
    assert "one@alpha" in failure.detail


def test_the_three_malformations_stay_told_apart() -> None:
    """⛔ THE POINT OF THE CONVERSION, asserted as one property rather than three.

    Three conditions, three `kind` words. Collapsed onto one `None` they were
    the same word, and each of the three is a DIFFERENT edit to
    `.claude/settings.json`: change the value's type, fix one array entry, or
    fix one mapping value. A future edit that merges any two of these kinds
    puts the sentinel back under a new name, and this is what catches it.
    """
    kinds = {
        _malformation(raw=7).kind,
        _malformation(raw=[7]).kind,
        _malformation(raw={"one@alpha": "yes"}).kind,
    }

    assert len(kinds) == 3, f"three distinct malformations must not share a kind; got {kinds}"


def test_the_public_answer_is_railway_typed() -> None:
    """THE CONVERSION ITSELF: the public answer may not be a bare value.

    `checks/public_api_result_typed` reads a function as on the railway when
    its return annotation's terminal name is `Result` or `IOResult` (or it
    carries a `safe` / `impure_safe` decorator). That check is a NO-OP in this
    repository — `pure_trees` is declared `not_applicable` — so nothing else
    here would notice a regression to `tuple[str, ...] | None`.
    """
    rendered = str(enabled_plugin_names.__annotations__["return"])

    assert _terminal_return_name(rendered=rendered) in _RAILWAY_RETURN_NAMES, (
        f"enabled_plugin_names must return a Result so its failure track is "
        f"expressible; got the bare annotation {rendered!r}"
    )


def test_the_planner_consumes_the_failure_track_and_keeps_the_marketplace_commands() -> None:
    """Caller 1 — `planned_commands`, whose behaviour the conversion PRESERVES.

    An unreadable enablement derives no install/update commands, and the
    marketplace registrations it could derive still stand. The planner's
    contract is "the commands this text supports", and the malformation itself
    is reported by `settings_findings`, which `ensure` runs BEFORE the planner
    — so swallowing the track here strands no diagnostic.
    """
    settings = json.dumps(
        {
            "extraKnownMarketplaces": {"alpha": {"source": {"repo": "owner/repo", "ref": "v1"}}},
            "enabledPlugins": 7,
        }
    )

    assert planned_commands(settings_text=settings) == (
        ("claude", "plugin", "marketplace", "add", "owner/repo@v1"),
    )


def test_the_settings_gate_forwards_the_parsers_own_reason() -> None:
    """Caller 2 — `_split_enablement`, which now REPORTS what the track carries.

    It used to answer every unreadable list with one fixed sentence, because
    the sentinel gave it nothing else to say. The finding now names the
    offending entry, which is the operator-visible payoff of the conversion
    rather than a restatement of it.
    """
    findings = settings_findings(settings_text=json.dumps({"enabledPlugins": ["one@alpha", 7]}))

    assert len(findings) == 1, f"expected exactly one shape finding; got {findings}"
    assert "entry 1" in findings[0], f"the finding must name the offending entry; got {findings[0]}"
