"""The check stops reaching a public function with no expected failure mode.

livespec v179 member 1, wired into `_find_offenders`. The analysis itself is
tested on fixtures in `test_no_expected_failure_mode.py`; what this file pins is
that the CHECK consults it — a correct analysis nothing calls would be the
manufactured-confidence shape this whole epic exists to remove, arriving one
level up in the wiring rather than in the rule.

A separate file from `test_public_api_result_typed.py` because that one is a
multi-assertion suite and this is the Red-recorded half of a Red→Green pair.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders

__all__: list[str] = []


_REL = Path("pkg/a.py")
_TOTAL = "def total(*, n: int) -> int:\n    return n + 1\n"
_FAILING = "def failing(*, n: int) -> int:\n    if n:\n        raise ValueError(n)\n    return n\n"


def _offender_names(*, source: str, exempt: frozenset[str]) -> list[str]:
    return [
        name
        for _lineno, name in _find_offenders(
            source=source,
            rel_path=_REL,
            commands_trees=(),
            public_names=frozenset({"total", "failing"}),
            no_expected_failure_mode=exempt,
        )
    ]


def test_a_public_function_with_no_expected_failure_mode_is_not_an_offender() -> None:
    """Member 1's answer removes the function from the reported set."""
    assert _offender_names(source=_TOTAL, exempt=frozenset({"total"})) == []


def test_the_same_function_is_an_offender_when_member_1_does_not_exempt_it() -> None:
    """The control. Without the exemption the identical source still reports.

    Asserted beside the positive case because a wiring bug that dropped EVERY
    offender would satisfy the test above on its own — and an empty offender
    list is exactly what this check's whole history looks like when it is
    silently doing nothing.
    """
    assert _offender_names(source=_TOTAL, exempt=frozenset()) == ["total"]


def test_a_public_function_that_raises_is_still_an_offender() -> None:
    """Member 1 exempts nothing that raises, so the rule still reaches it."""
    assert _offender_names(source=_FAILING, exempt=frozenset()) == ["failing"]
