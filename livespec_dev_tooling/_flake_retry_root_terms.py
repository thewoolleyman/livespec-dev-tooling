"""The root term of one path-expression base for the flake-retry closure analysis.

SPECIFICATION non-functional-requirements.md "Untouched-test retry": a path
expression counts only when its base is repository-rooted
(livespec-dev-tooling-bob7iv). A `RootTerm` says whether a base may be the
repository -- `rooted`, where a base this analysis cannot classify counts, so
the literal segments of a `/` chain on it count -- and which repository
directories it
positively is -- `places`, repository-relative with `""` for the root, which
only an expression the module resolves from `__file__`, a request's test path,
`rootpath`, `rootdir` or `invocation_params.dir` proves, extended by literal
`/` segments (livespec-dev-tooling-4ai5ao). Either holds on its own or through
bindings, fixtures, attribute stores and imports that the whole closure then
solves; any other derived path, such as `ROOT.parent`, keeps the doubt of its
object but not its places, so only `through` carries it, never `evidence`.

`spans` are directories a path lies somewhere under (see `Span`): a request's
test path read outside a test module (see `request_span`). They travel through
`through`, so the closure names each span directory whole, and a span at the
root is undeterminable. An upward step (`ascended`) widens the term's own spans
and turns its own places into spans, and its `ascent` widens, the same way,
whatever spans and places its `through` keys bring when the closure solves.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from livespec_dev_tooling._flake_retry_places import is_request_path
from livespec_dev_tooling._flake_retry_scopes import Scope, ScopeIndex, owning_scope
from livespec_dev_tooling._flake_retry_spans import EXACT, UNBOUNDED, Span, climbed
from livespec_dev_tooling.flake_retry_divisions import division_operands

__all__: list[str] = [
    "DOUBT",
    "NOT_ROOTED",
    "ROOTED",
    "Key",
    "RootTerm",
    "TermContext",
    "ascended",
    "base_term",
    "binding_key",
    "through",
    "union",
]

Key = tuple[str, str]

_TEMPORARY_NAMES = frozenset({"tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory"})
_TEMPORARY_CALLS = frozenset(
    (
        "home expanduser mktemp mkdtemp mkstemp gettempdir getbasetemp "
        "TemporaryDirectory NamedTemporaryFile"
    ).split()
)
_WORKING_DIRECTORY_CALLS = frozenset({"cwd", "getcwd"})
_SAME_PATH_CALLS = frozenset(
    "Path PurePath PosixPath PurePosixPath str fspath abspath realpath normpath".split()
)
_PATH_CONSTRUCTORS = _SAME_PATH_CALLS | {"dirname", "join"}
_SAME_PATH_METHODS = frozenset({"resolve", "absolute"})
_SAME_PATH_EXPRESSIONS = (ast.IfExp, ast.BoolOp, ast.NamedExpr)
_ROOT_ATTRIBUTES = frozenset({"__file__", "rootpath", "rootdir"})


@dataclass(frozen=True, kw_only=True)
class RootTerm:
    """Rooted when any key it goes through is; placed wherever a key of its evidence is."""

    rooted: bool
    places: frozenset[str]
    through: frozenset[Key]
    evidence: frozenset[Key] = frozenset()
    spans: frozenset[Span] = frozenset()
    ascent: int = 0


ROOTED = RootTerm(rooted=True, places=frozenset({""}), through=frozenset())
DOUBT = RootTerm(rooted=True, places=frozenset(), through=frozenset())
NOT_ROOTED = RootTerm(rooted=False, places=frozenset(), through=frozenset())


@dataclass(frozen=True, kw_only=True)
class TermContext:
    """One module's scope index, its label, and where each `from` import resolves."""

    index: ScopeIndex
    module: str
    numbers: dict[int, int]
    import_sources: Mapping[int, str]
    places: Mapping[int, str]
    request_span: str | None


def union(*, terms: Iterable[RootTerm]) -> RootTerm:
    """Combine terms: rooted when any of them is, placed wherever any of them is."""
    collected = list(terms)
    return RootTerm(
        rooted=any(term.rooted for term in collected),
        places=frozenset(place for term in collected for place in term.places),
        spans=frozenset(span for term in collected for span in term.spans),
        through=frozenset(key for term in collected for key in term.through),
        evidence=frozenset(key for term in collected for key in term.evidence),
        ascent=max((term.ascent for term in collected), default=0),
    )


def through(*keys: Key) -> RootTerm:
    """A term rooted, and placed, exactly when one of these keys is."""
    return RootTerm(
        rooted=False, places=frozenset(), through=frozenset(keys), evidence=frozenset(keys)
    )


def _derived(*, term: RootTerm) -> RootTerm:
    """A path derived from a base keeps the base's doubt but not its places."""
    return RootTerm(
        rooted=term.rooted,
        places=frozenset(),
        through=term.through,
        spans=term.spans,
        ascent=term.ascent,
    )


def ascended(*, term: RootTerm, steps: int) -> RootTerm:
    """A base after `steps` upward steps: its places become spans and its spans widen."""
    own = [*((place, EXACT) for place in term.places), *term.spans]
    spans = (climbed(span=span, steps=steps) for span in own)
    return RootTerm(
        rooted=term.rooted,
        places=frozenset(),
        through=term.through,
        spans=frozenset(span for span in spans if span is not None),
        ascent=min(term.ascent + steps, UNBOUNDED),
    )


def _divided(*, term: RootTerm, segments: tuple[ast.expr, ...]) -> RootTerm:
    """A base divided by plain literal segments is placed at those segments under each place."""
    texts = [str(getattr(segment, "value", "")) for segment in segments]
    plain = all(
        isinstance(segment, ast.Constant) and isinstance(segment.value, str) for segment in segments
    ) and all(text and not text.startswith("/") and ".." not in text.split("/") for text in texts)
    places = frozenset("/".join(part for part in (place, *texts) if part) for place in term.places)
    ups = sum(text.split("/").count("..") for text in texts)
    kept = RootTerm(
        rooted=term.rooted,
        places=places if plain else frozenset(),
        through=term.through,
        spans=term.spans,
        ascent=term.ascent,
    )
    return ascended(term=term, steps=ups) if ups else kept


def binding_key(*, name: str, scope: Scope, context: TermContext) -> Key:
    """The key of a name bound in one scope of this module."""
    return ("binding", f"{context.module}:{context.numbers[id(scope)]}:{name}")


def _name_term(*, name: str, scope: Scope, context: TermContext) -> RootTerm:
    """A name is rooted through its binding where it resolves; an unbound name is a doubt.

    `__file__` reaches here only when it resolves outside the repository, and as
    an unbound name it stays a doubt.
    """
    if name in _TEMPORARY_NAMES:
        return NOT_ROOTED
    owner = owning_scope(name=name, scope=scope, index=context.index)
    if owner is None:
        return DOUBT
    return through(binding_key(name=name, scope=owner, context=context))


def _call_term(*, call: ast.Call, context: TermContext) -> RootTerm:
    """A call is rooted through its receiver and method, its path argument or its function."""
    func = call.func
    callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    first = call.args[0] if call.args else None
    fixture = first.value if isinstance(first, ast.Constant) else None
    if callee in _TEMPORARY_CALLS:
        return NOT_ROOTED
    if (
        callee in _WORKING_DIRECTORY_CALLS
        or (callee == "getfixturevalue" and not isinstance(fixture, str))
        or (callee in _PATH_CONSTRUCTORS and first is None)
    ):
        return DOUBT
    if isinstance(fixture, str) and callee == "getfixturevalue":
        return through(("fixture", fixture), ("request", fixture))
    if callee in _PATH_CONSTRUCTORS and first is not None:
        argument = base_term(expression=first, context=context)
        derived = (
            ascended(term=argument, steps=1) if callee == "dirname" else _derived(term=argument)
        )
        return argument if callee in _SAME_PATH_CALLS else derived
    if isinstance(func, ast.Attribute):
        receiver = base_term(expression=func.value, context=context)
        receiver = receiver if callee in _SAME_PATH_METHODS else _derived(term=receiver)
        return union(terms=(receiver, through(("attribute", func.attr))))
    return base_term(expression=func, context=context)


def _attribute_term(*, attribute: ast.Attribute, context: TermContext) -> RootTerm:
    """An attribute is rooted when it names a root, or through its object or an attribute store."""
    if attribute.attr in _ROOT_ATTRIBUTES:
        return DOUBT if attribute.attr == "__file__" else ROOTED
    if context.request_span is not None and is_request_path(attribute=attribute):
        spans = frozenset({(context.request_span, 1)})
        return RootTerm(rooted=True, places=frozenset(), through=frozenset(), spans=spans)
    stored = through(("attribute", attribute.attr))
    owner = base_term(expression=attribute.value, context=context)
    steps = {"parent": 1, "parents": UNBOUNDED}.get(attribute.attr, 0)
    owner = ascended(term=owner, steps=steps) if steps else _derived(term=owner)
    return union(terms=(owner, stored))


def _is_parents(*, expression: ast.expr) -> bool:
    return isinstance(expression, ast.Attribute) and expression.attr == "parents"


def base_term(*, expression: ast.expr, context: TermContext) -> RootTerm:
    """Whether a path expression's base is, or may be, repository-rooted, and through what."""
    if id(expression) in context.places:
        place = frozenset({context.places[id(expression)]})
        term = RootTerm(rooted=True, places=place, through=frozenset())
    elif isinstance(expression, ast.Constant):
        term = DOUBT if isinstance(expression.value, str) else NOT_ROOTED
    elif isinstance(expression, ast.Name):
        scope = context.index.scope_of[id(expression)]
        term = _name_term(name=expression.id, scope=scope, context=context)
    elif isinstance(expression, ast.Attribute):
        term = _attribute_term(attribute=expression, context=context)
    elif isinstance(expression, ast.Subscript) and _is_parents(expression=expression.value):
        index = expression.slice
        constant = isinstance(index, ast.Constant) and type(index.value) is int
        steps = int(getattr(index, "value", 0)) + 1 if constant else UNBOUNDED
        owner = base_term(
            expression=getattr(expression.value, "value", expression), context=context
        )
        term = ascended(term=owner, steps=steps)
    elif isinstance(expression, ast.Subscript):
        term = base_term(expression=expression.value, context=context)
    elif isinstance(expression, ast.Call):
        term = _call_term(call=expression, context=context)
    elif isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        base, *segments = division_operands(expression=expression)
        term = _divided(term=base_term(expression=base, context=context), segments=tuple(segments))
    else:
        children = [
            child for child in ast.iter_child_nodes(expression) if isinstance(child, ast.expr)
        ]
        term = union(terms=(base_term(expression=child, context=context) for child in children))
        term = term if isinstance(expression, _SAME_PATH_EXPRESSIONS) else _derived(term=term)
        term = term if children else DOUBT
    return term
