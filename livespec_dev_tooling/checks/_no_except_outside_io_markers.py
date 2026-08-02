"""Marker recognition and boundary accounting for no_except_outside_io.

The `# noqa: BLE001 — …` marker lives on the `except …:` clause itself,
which `ast` discards along with every other comment, so recognizing one
means tokenizing the module and locating the clause's own line span.
That token work, the closed marker set, and the per-artifact boundary
tally are one cohesive unit and live here.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize

__all__: list[str] = [
    "BOUNDARY_FLAVOR",
    "CARDINALITY_REASON",
    "cardinality_offenses",
    "comment_lines",
    "sanctioned_marker_flavor",
    "statement_colons",
]

# The closed set of BLE001 suppression reasons, quoted from
# `livespec/SPECIFICATION/non-functional-requirements.md` section "Linter rule set".
# Any other reason wording marks a violation rather than an escape, so a
# conforming comment must BE the directive plus one sanctioned wording —
# equality, not containment: text before, around, or after a wording
# (which can invert its meaning outright) disqualifies the comment. The
# foreign-code isolation entry is a template matched by an anchored shape
# instead of equality: `<surface>` is per-site free text (non-empty, no
# angle brackets — so the literal unfilled placeholder can never conform),
# `<ErrorType>` names the captured exception type (a possibly-dotted
# identifier, never prose), and the wording ends at the literal
# `, reported`.
#
# The set is split by ACCOUNTING UNIT, not merely listed, because the word
# `sole` scopes differently per flavor. The three BOUNDARY wordings are
# "at most one per process entry artifact", so they share ONE slot and are
# counted against it. The foreign-code template is accounted per extension
# invocation surface, so it does not consume the artifact's boundary slot and
# may not be tallied with them.
#
# A fourth wording — the loop-iteration bug-catcher, accounted per supervision
# loop — was RETIRED by the maintainer ruling of 2026-07-26: a daemon does not
# get a per-iteration broad catch ("let it crash, systemd restarts"; exactly one
# broad catch per program, in `main()`). Two accounting units remain, not three;
# there is no per-supervision-loop unit left for `sole` to scope to. Do NOT
# reintroduce the wording — `test_no_except_outside_io_rejects_the_retired_loop_
# iteration_marker` pins its rejection.
_BOUNDARY_WORDINGS = frozenset(
    {
        "— sole supervisor bug-catcher: log traceback, exit 1",
        "— sole fail-open hook boundary: silent pass-through, exit 0",
        "— sole fail-closed guard boundary: deny per policy, exit 0",
    }
)
_FOREIGN_CODE_WORDING_SHAPE = re.compile(
    r"\A— foreign-code isolation: [^<>\s][^<>]* crash captured as "
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*, reported\Z"
)
# Built by concatenation so this source line never itself contains the live
# directive text (kept from the containment-era implementation's rationale).
_MARKER_COMMENT_PREFIX = "# " + "noqa: BLE001 "

# Flavor labels, distinguished ONLY by accounting unit. `_SEPARATE_FLAVOR`
# means sanctioned-but-not-against-the-artifact-slot. Since the retirement of
# the loop-iteration wording it has exactly one member, foreign-code isolation;
# the label is kept rather than collapsed into a foreign-code-specific name
# because the distinction it draws is the ACCOUNTING UNIT, which is what every
# caller cares about, and a future separately-accounted flavor would belong here.
BOUNDARY_FLAVOR = "boundary"
_SEPARATE_FLAVOR = "accounted-separately"

CARDINALITY_REASON = (
    "second broad catch carrying a boundary marker in this process entry "
    "artifact is banned; at most one is permitted (foreign-code catches are "
    "accounted separately, per extension invocation surface)"
)


# The two token scans below deliberately return plain builtins rather than
# sharing one dataclass container. Under `from __future__ import annotations`
# a dataclass resolves its string annotations through
# `sys.modules[cls.__module__]`, which is `None` for a module loaded by path
# via `importlib.util.spec_from_file_location` without being registered — the
# exact shape of this check's standalone-import test, which would fail with
# `AttributeError: 'NoneType' object has no attribute '__dict__'`. Do not
# reintroduce a dataclass here.
def comment_lines(*, source: str) -> dict[int, tuple[str, ...]]:
    """Map each line number to the comment token texts starting on it.

    Comments are read as TOKENS rather than by scanning raw source lines,
    so marker text inside a string literal cannot be mistaken for a
    marker.
    """
    comments: dict[int, list[str]] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            comments.setdefault(token.start[0], []).append(token.string)
    return {line: tuple(texts) for line, texts in comments.items()}


def statement_colons(*, source: str) -> tuple[tuple[int, int], ...]:
    """Positions of every `:` operator at bracket depth zero, in source order.

    Depth is tracked so that colons inside a dict display, a slice, or a
    parenthesized exception tuple are skipped; what remains includes the
    `:` that terminates an `except …:` clause.
    """
    colons: list[tuple[int, int]] = []
    depth = 0
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.OP:
            continue
        if token.string in {"(", "[", "{"}:
            depth += 1
        elif token.string in {")", "]", "}"}:
            depth -= 1
        elif token.string == ":" and depth == 0:
            colons.append(token.start)
    return tuple(colons)


def _clause_colon_line(
    *, node: ast.ExceptHandler | ast.With | ast.AsyncWith, colons: tuple[tuple[int, int], ...]
) -> int:
    """Line of the `:` that closes this catch clause.

    The first statement-level colon at or after the node's own start
    position is that clause's colon; anything later belongs to the body.
    Every accepted catch clause is closed by such a colon, so the node's
    own line is a floor that only a malformed parse could reach.
    """
    start = (node.lineno, node.col_offset)
    return min((position[0] for position in colons if position >= start), default=node.lineno)


def _marker_comment_flavor(*, text: str) -> str | None:
    """Return the flavor of a comment that IS the directive plus a sanctioned wording.

    A comment that merely contains a wording is prose, not a marker, and
    yields `None`.
    """
    if not text.startswith(_MARKER_COMMENT_PREFIX):
        return None
    wording = text[len(_MARKER_COMMENT_PREFIX) :]
    if wording in _BOUNDARY_WORDINGS:
        return BOUNDARY_FLAVOR
    if _FOREIGN_CODE_WORDING_SHAPE.fullmatch(wording) is not None:
        return _SEPARATE_FLAVOR
    return None


def sanctioned_marker_flavor(
    *,
    node: ast.ExceptHandler | ast.With | ast.AsyncWith,
    comments: dict[int, tuple[str, ...]],
    colons: tuple[tuple[int, int], ...],
) -> str | None:
    """Return the flavor of the clause-line sanctioned marker, else `None`.

    The span ends at the clause's closing colon, so a comment BELOW it —
    inside the handler body — is inert. Ending the span at the first body
    STATEMENT instead would admit a body comment sitting above that
    statement, since such a comment is not itself a statement.
    """
    last = _clause_colon_line(node=node, colons=colons)
    for line in range(node.lineno, last + 1):
        for text in comments.get(line, ()):
            flavor = _marker_comment_flavor(text=text)
            if flavor is not None:
                return flavor
    return None


def cardinality_offenses(*, boundary_lines: list[int]) -> list[tuple[int, str]]:
    """Flag every boundary-marked catch after the first, in source order.

    The first is reported clean and the EXCESS is named, so the message
    points at what to remove rather than at the whole set. Sorting is
    what makes "first" mean first-in-file: `ast.walk` yields breadth-first,
    not in source order.
    """
    ordered = sorted(boundary_lines)
    return [(line, CARDINALITY_REASON) for line in ordered[1:]]
