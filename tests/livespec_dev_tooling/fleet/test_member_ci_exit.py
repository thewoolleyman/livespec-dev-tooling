"""Tests for `livespec_dev_tooling/fleet/_member_ci_exit.py`.

The end-to-end behaviour — an unwired member not reddening a sibling's CI, the
fleet-view default, the loud precondition failures — is pinned through `main()` in
`test_fleet_conformance.py`, where the whole sweep runs against canned reads. This
module covers the one branch that end-to-end path cannot reach.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._lanes import MemberVerdict
from livespec_dev_tooling.fleet._member_ci_exit import own_failing_rows

__all__: list[str] = []


def test_own_failing_rows_returns_the_matching_member_rows() -> None:
    verdicts = (
        MemberVerdict(member="widget", failing_rows=()),
        MemberVerdict(member="gadget", failing_rows=("ci-workflow", "bump-pin-shim")),
    )
    assert own_failing_rows(member_verdicts=verdicts, running_as="gadget") == (
        "ci-workflow",
        "bump-pin-shim",
    )
    assert own_failing_rows(member_verdicts=verdicts, running_as="widget") == ()


def test_own_failing_rows_is_empty_for_a_member_with_no_verdict() -> None:
    """The defensive fallback, unreachable through `member_ci_exit_code` by design.

    That caller admits a `running_as` only after checking it against
    `manifest.member_names()`, and the verdict tuple is built from `manifest.members`,
    so a member always has a verdict there. This asserts the fallback directly rather
    than leaving it uncovered, and pins the SAFE direction: an absent verdict yields
    no owned failing rows, so the caller does not fabricate a violation for a member
    the sweep never judged. Returning something non-empty here would invent a failure.
    """
    verdicts = (MemberVerdict(member="widget", failing_rows=("ci-workflow",)),)

    assert own_failing_rows(member_verdicts=verdicts, running_as="absent-from-verdicts") == ()
    assert own_failing_rows(member_verdicts=(), running_as="widget") == ()
