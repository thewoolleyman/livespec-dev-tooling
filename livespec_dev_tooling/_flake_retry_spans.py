"""Where a path base lies: an exact repository directory, or somewhere under one.

SPECIFICATION non-functional-requirements.md "Untouched-test retry"
(livespec-dev-tooling-4ai5ao): for the `/` chains this analysis reads, a
doubt about where a base lies must not narrow what it names. A `Span` is a
repository-relative directory, `""` for the root, with a slack: `EXACT` when
the base is that directory, or the number of levels the base is known to lie
below it. An upward step -- `.parent`, `dirname`, a `..` segment,
`parents[n]` -- first spends the slack and then widens the directory, so a
span never claims less than the base can reach. An exact directory stepped
above the repository root names no repository path; a span widened past the
root is the root itself, which is undeterminable.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__: list[str] = ["EXACT", "UNBOUNDED", "Span", "climbed", "crossed"]

Span = tuple[str, int]

EXACT = -1
UNBOUNDED = 1 << 16


def _ancestor(*, directory: str, levels: int) -> str | None:
    """The directory `levels` above this one, or None above the repository root."""
    parts = [part for part in directory.split("/") if part]
    return "/".join(parts[: len(parts) - levels]) if levels <= len(parts) else None


def climbed(*, span: Span, steps: int) -> Span | None:
    """Where a base lies after `steps` upward steps; None when it leaves the repository.

    An exact directory stepped an unbounded number of times may land on any
    ancestor, so it widens to the root unless it is the root already.
    """
    directory, slack = span
    if slack == EXACT:
        exact = _ancestor(directory=directory, levels=steps)
        unbounded = ("", 0) if steps >= UNBOUNDED and directory else None
        return (exact, 0) if exact is not None else unbounded
    widened = _ancestor(directory=directory, levels=steps - slack)
    return (directory, slack - steps) if steps <= slack else ("" if widened is None else widened, 0)


def crossed(*, values: Iterable[Span], ascent: int, exact_passes: bool) -> frozenset[Span]:
    """What a key's spans become in a term that goes through it with `ascent` upward steps.

    With no upward step an exact directory passes only along an evidence edge,
    where nothing between them changed the path; any upward step turns it into
    a span.
    """
    kept = [value for value in values if ascent or exact_passes or value[1] != EXACT]
    moved = (climbed(span=value, steps=ascent) if ascent else value for value in kept)
    return frozenset(value for value in moved if value is not None)
