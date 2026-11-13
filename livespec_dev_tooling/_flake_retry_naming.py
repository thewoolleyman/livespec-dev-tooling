"""The repository paths a path expression names from where its base lies.

SPECIFICATION non-functional-requirements.md "Untouched-test retry"
(livespec-dev-tooling-4ai5ao). For a `/` chain whose base lies at an exact
repository directory, the chain names its literal segments under that
directory, or the directory itself when it has no literal segment; at the
root, a chain with no literal segment names a path no literal spells, so it is
undeterminable. A base that lies somewhere under a directory (a span) names
the directory whole, whatever follows, and a span at the root is
undeterminable. Only `/` chains are read this way; a path built by other means
(`os.path.join`, an f-string, `with_name`) is not.
"""

from __future__ import annotations

from collections.abc import Iterable

from livespec_dev_tooling._flake_retry_root_terms import RootTerm
from livespec_dev_tooling._flake_retry_spans import EXACT, Span

__all__: list[str] = ["named", "own_spans"]

_ITSELF = frozenset({""})


def _under(*, places: Iterable[str], names: Iterable[str]) -> set[str]:
    """Each name spelled under each non-root directory; `_ITSELF` names the directory."""
    spelled = list(names)
    return {"/".join(filter(None, (place, name))) for place in places if place for name in spelled}


def own_spans(*, term: RootTerm) -> frozenset[Span]:
    """Where a base lies on its own: each exact place, and each span."""
    return frozenset({*((place, EXACT) for place in term.places), *term.spans})


def named(*, spans: Iterable[Span], names: frozenset[str]) -> tuple[set[str], bool]:
    """What a chain spelling `names` names from these locations; True when undeterminable."""
    located = list(spans)
    places = {directory for directory, slack in located if slack == EXACT}
    widened = {directory for directory, slack in located if slack != EXACT}
    literals = _under(places=places, names=names or _ITSELF) | _under(places=widened, names=_ITSELF)
    return literals, "" in widened or (not names and "" in places)
