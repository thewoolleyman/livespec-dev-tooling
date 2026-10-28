"""Tests for `livespec_dev_tooling/checks/_canonical_waivers.py`.

The module is the ONE reader of the `canonical_check_waivers` key that
`check-aggregate-completeness` and the fleet-conformance row
`canonical-check-slugs-wired` share (the "Canonical-check waivers" paragraph of
`SPECIFICATION/contracts.md`). These tests pin the declaration reader and the
stale / malformed judgement the two consumers apply.
"""

from __future__ import annotations

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling.checks._canonical_waivers import (
    CanonicalWaiver,
    DeclaredWaivers,
    PyprojectUnparseable,
    declared_waivers,
    judge_waivers,
)

__all__: list[str] = []


_CANONICAL = ("check-alpha", "check-beta", "check-gamma")


def _declared(*, text: str) -> object:
    parsed = declared_waivers(pyproject_text=text)
    assert isinstance(parsed, Success)
    return parsed.unwrap().value


def test_an_absent_key_or_table_declares_no_waiver() -> None:
    assert _declared(text="") == []
    assert _declared(text="[project]\nname = 'x'\n") == []
    assert _declared(text="[tool.livespec_dev_tooling]\nscenario_tiers = []\n") == []
    assert _declared(text="[tool]\nlivespec_dev_tooling = 3\n") == []


def test_inline_array_and_array_of_tables_spellings_read_identically() -> None:
    inline = (
        "[tool.livespec_dev_tooling]\n"
        'canonical_check_waivers = [{ slug = "check-beta", reason = "Rust member" }]\n'
    )
    expanded = (
        "[[tool.livespec_dev_tooling.canonical_check_waivers]]\n"
        'slug = "check-beta"\n'
        'reason = "Rust member"\n'
    )
    assert _declared(text=inline) == [{"slug": "check-beta", "reason": "Rust member"}]
    assert _declared(text=expanded) == _declared(text=inline)


def test_an_unparseable_pyproject_is_a_failure_not_an_absent_key() -> None:
    parsed = declared_waivers(pyproject_text="[tool.livespec_dev_tooling\nbroken")

    assert isinstance(parsed, Failure)
    assert isinstance(parsed.failure(), PyprojectUnparseable)
    assert parsed.failure().detail
    assert declared_waivers(pyproject_text="") == Success(DeclaredWaivers(value=[]))


def test_a_reasoned_waiver_of_an_omitted_slug_is_honoured() -> None:
    verdict = judge_waivers(
        declared=[{"slug": "check-beta", "reason": "Rust member owns its own map"}],
        canonical=_CANONICAL,
        selected=("check-alpha", "check-gamma"),
    )

    assert verdict.problems == ()
    assert verdict.honoured == (
        CanonicalWaiver(slug="check-beta", reason="Rust member owns its own map"),
    )


def test_no_declaration_yields_an_empty_verdict() -> None:
    verdict = judge_waivers(declared=[], canonical=_CANONICAL, selected=_CANONICAL)

    assert verdict.honoured == ()
    assert verdict.problems == ()


def test_a_waiver_of_a_selected_slug_is_stale_and_names_the_slug() -> None:
    verdict = judge_waivers(
        declared=[{"slug": "check-alpha", "reason": "once needed"}],
        canonical=_CANONICAL,
        selected=_CANONICAL,
    )

    assert verdict.honoured == ()
    assert len(verdict.problems) == 1
    problem = verdict.problems[0]
    assert problem.kind == "stale"
    assert problem.subject == "check-alpha"
    assert "stale" in problem.render()
    assert "check-alpha" in problem.render()


@pytest.mark.parametrize(
    ("declared", "subject"),
    [
        pytest.param("check-beta", "canonical_check_waivers", id="value-is-a-string"),
        pytest.param(
            {"slug": "check-beta", "reason": "x"}, "canonical_check_waivers", id="value-is-a-table"
        ),
        pytest.param(["check-beta"], "entry at position 0", id="entry-is-not-a-table"),
        pytest.param([{"reason": "x"}], "entry at position 0", id="slug-missing"),
        pytest.param([{"slug": "check-beta"}], "check-beta", id="reason-missing"),
        pytest.param(
            [{"slug": "check-beta", "reason": "x", "until": "never"}],
            "check-beta",
            id="extra-key",
        ),
        pytest.param([{"slug": 7, "reason": "x"}], "entry at position 0", id="slug-not-a-string"),
        pytest.param([{"slug": "check-beta", "reason": 7}], "check-beta", id="reason-not-a-string"),
        pytest.param([{"slug": "check-beta", "reason": ""}], "check-beta", id="reason-empty"),
        pytest.param(
            [{"slug": "check-beta", "reason": " \t\n"}], "check-beta", id="reason-whitespace"
        ),
        pytest.param(
            [{"slug": "check-nonesuch", "reason": "x"}], "check-nonesuch", id="slug-not-canonical"
        ),
    ],
)
def test_every_malformed_shape_is_reported_by_slug_or_position(
    *, declared: object, subject: str
) -> None:
    verdict = judge_waivers(declared=declared, canonical=_CANONICAL, selected=("check-alpha",))

    assert verdict.honoured == ()
    assert [(problem.kind, problem.subject) for problem in verdict.problems] == [
        ("malformed", subject)
    ]
    assert "malformed" in verdict.problems[0].render()
    assert subject in verdict.problems[0].render()


def test_position_is_the_array_index_of_the_offending_entry() -> None:
    verdict = judge_waivers(
        declared=[{"slug": "check-beta", "reason": "ok"}, {"reason": "no slug"}],
        canonical=_CANONICAL,
        selected=(),
    )

    assert [waiver.slug for waiver in verdict.honoured] == ["check-beta"]
    assert [problem.subject for problem in verdict.problems] == ["entry at position 1"]


def test_a_malformed_selected_waiver_is_malformed_not_also_stale() -> None:
    verdict = judge_waivers(
        declared=[{"slug": "check-alpha", "reason": ""}],
        canonical=_CANONICAL,
        selected=("check-alpha",),
    )

    assert [(problem.kind, problem.subject) for problem in verdict.problems] == [
        ("malformed", "check-alpha")
    ]


def test_a_duplicate_slug_is_malformed_and_the_first_entry_stands() -> None:
    verdict = judge_waivers(
        declared=[
            {"slug": "check-beta", "reason": "first"},
            {"slug": "check-beta", "reason": "second"},
        ],
        canonical=_CANONICAL,
        selected=(),
    )

    assert verdict.honoured == (CanonicalWaiver(slug="check-beta", reason="first"),)
    assert [(problem.kind, problem.subject) for problem in verdict.problems] == [
        ("malformed", "check-beta")
    ]
