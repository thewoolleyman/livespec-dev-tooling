"""Lift the suite's canned `GhResult` fakes onto the seam's railway.

Imported by bare name, per this directory's `conftest.py` (which puts the
fleet test dir on `sys.path` under `--import-mode=importlib`), the same
way `_protection_fixtures` is.

WHY A LIFT RATHER THAN A REWRITE OF EVERY FAKE. `GhRunner` returns
`IOResult[GhResult, InvocationNotPerformed]` since
`livespec-dev-tooling-8o8e` row 30. Every canned fake in this suite
answers as a `gh` that RAN — which is exactly what the rows under test are
about — so lifting them wholesale onto the SUCCESS track preserves each
existing assertion byte for byte, and keeps the twenty-odd canned tables
readable in the vocabulary their tests actually reason about.

⛔ The failure track is NOT reachable through this helper, deliberately.
"The invocation never happened" is exercised at the seam and at the rows
that used to misread it, in `test_context_invocation_railway*.py`, rather
than by threading an `IOSuccess` through a hundred table entries and
hoping one of them was set to fail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from returns.io import IOSuccess

if TYPE_CHECKING:
    from collections.abc import Callable

    from livespec_dev_tooling.fleet._context import GhOutcome, GhResult, GhRunner

__all__: list[str] = ["lift_gh"]


def lift_gh(inner: Callable[..., GhResult]) -> GhRunner:
    """Wrap a `GhResult`-returning canned fake as a `GhRunner`."""

    def run(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        return IOSuccess(inner(args=args, stdin=stdin))

    return run
