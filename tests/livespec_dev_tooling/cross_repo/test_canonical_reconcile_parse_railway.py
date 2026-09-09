"""`_canonical_reconcile_parse.check_recipe_bounds` puts its failure on the railway.

qndn cluster 10, following the ruled-CONVERT `extract_check_recipe_body`
precedent (`plan/rop-railway-enforcement/research/qndn-75-triage.md` §4d-BIS).
The reader returned `tuple[int, int] | None`, and the `None` was the ONE
condition "this justfile carries no `check` aggregate recipe at all" —
reported by every caller as its OWN inability (`no_check_header`, "skipping
canonical check wiring reconcile"), which is §4d-BIS's caller test for CONVERT.

Asserted at the reader's own seam AND at the two caller seams, because
`_reconcile` short-circuits on `no_aggregate` before it ever reaches the
bounds read, so the caller tests alone cannot pin the reader's return shape.
"""

from __future__ import annotations

from returns.result import Failure, Success

from livespec_dev_tooling.checks._check_aggregate_failures import CheckRecipeAbsent
from livespec_dev_tooling.cross_repo._canonical_reconcile_parse import check_recipe_bounds
from livespec_dev_tooling.cross_repo.justfile_canonical_reconcile import reconcile_sources

_JUSTFILE_WITH_AGGREGATE = """check:
    targets=(
        check-aggregate-completeness
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness
"""

# Wires the aggregate SLUG but declares no `check` aggregate recipe, so the
# reader is reached and finds nothing — the condition the `None` used to carry.
_JUSTFILE_WITHOUT_AGGREGATE_RECIPE = """check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness
"""

_INVENTORY = """check-aggregate-completeness
"""


def test_check_recipe_bounds_reaches_the_caller() -> None:
    """The bounds of a present aggregate ride the SUCCESS track."""
    lines = _JUSTFILE_WITH_AGGREGATE.splitlines(keepends=True)
    assert check_recipe_bounds(lines=lines) == Success((0, 5))


def test_parameterized_aggregate_header_still_reaches_the_caller() -> None:
    """`check *skip_targets:` is an aggregate header, not an absent one."""
    lines = "check *skip_targets:\n    echo hi\n".splitlines(keepends=True)
    assert check_recipe_bounds(lines=lines) == Success((0, 2))


def test_absent_check_aggregate_is_a_typed_failure() -> None:
    """No `check` aggregate recipe is a FAILURE, not a tuple-shaped absence."""
    lines = "build:\n    echo build\n".splitlines(keepends=True)
    assert check_recipe_bounds(lines=lines) == Failure(CheckRecipeAbsent())


def test_justfile_only_caller_reports_the_failure_as_its_own_skip() -> None:
    """`_reconcile` consumes the failure track and names `no_check_header`."""
    result = reconcile_sources(
        justfile_text=_JUSTFILE_WITHOUT_AGGREGATE_RECIPE,
        inventory_text=None,
        canonical_slugs=["check-aggregate-completeness", "check-new-thing"],
    )
    assert result.skipped_reason == "no_check_header"
    assert result.justfile_text == _JUSTFILE_WITHOUT_AGGREGATE_RECIPE


def test_inventory_caller_reconciles_despite_the_failure_track() -> None:
    """The both-sources caller treats an absent aggregate recipe as array-not-reconciled.

    The inventory is what `aggregate_completeness` actually reads, so the
    failure track suppresses only the array insertion — never the file.
    """
    result = reconcile_sources(
        justfile_text=_JUSTFILE_WITHOUT_AGGREGATE_RECIPE,
        inventory_text=_INVENTORY,
        canonical_slugs=["check-aggregate-completeness", "check-new-thing"],
    )
    assert result.skipped_reason is None
    assert result.inventory_text is not None
    assert "check-new-thing" in result.inventory_text
