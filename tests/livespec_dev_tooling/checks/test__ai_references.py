"""Unit tests for `livespec_dev_tooling/checks/_ai_references.py`.

The pure `.ai/<topic>.md` reference helper: the concrete-reference
regex (a backtick-wrapped real path matches; the `.ai/<topic>.md`
angle-bracket placeholder and a `foo.ai/x.md` tail-of-token do NOT),
the per-line reference iterator with 1-indexed line numbers, and the
excluded-segment predicate.
"""

from __future__ import annotations

from livespec_dev_tooling.checks._ai_references import (
    AGENTS_FILENAME,
    is_excluded_agents_path,
    iter_ai_references,
)

__all__: list[str] = []


def test_agents_filename_constant() -> None:
    assert AGENTS_FILENAME == "AGENTS.md"


def test_iter_ai_references_matches_backtick_wrapped_concrete_ref() -> None:
    text = "Read `.ai/agent-disciplines.md` when ending a session."
    assert iter_ai_references(text=text) == [(1, ".ai/agent-disciplines.md")]


def test_iter_ai_references_ignores_angle_bracket_placeholder() -> None:
    text = "A member MAY disclose detail into `.ai/<topic>.md` files."
    assert iter_ai_references(text=text) == []


def test_iter_ai_references_ignores_tail_of_token() -> None:
    text = "The path foo.ai/x.md is a larger token, not a reference."
    assert iter_ai_references(text=text) == []


def test_iter_ai_references_reports_correct_line_numbers() -> None:
    text = "\n".join(
        (
            "intro line with no reference",
            "see `.ai/one.md` here",
            "no reference on this line either",
            "and `.ai/two.md` plus `.ai/three.md` on one line",
        )
    )
    assert iter_ai_references(text=text) == [
        (2, ".ai/one.md"),
        (4, ".ai/two.md"),
        (4, ".ai/three.md"),
    ]


def test_is_excluded_agents_path_true_for_archive_segment() -> None:
    assert is_excluded_agents_path(segments=("archive", "AGENTS.md")) is True


def test_is_excluded_agents_path_true_for_nested_vendor_segment() -> None:
    assert is_excluded_agents_path(segments=("pkg", "_vendor", "AGENTS.md")) is True


def test_is_excluded_agents_path_false_for_root_agents() -> None:
    assert is_excluded_agents_path(segments=("AGENTS.md",)) is False
