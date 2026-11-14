"""Repository-rooted path-expression bases for the flake-retry closure analysis.

SPECIFICATION non-functional-requirements.md "Untouched-test retry": a path
expression whose base is not repository-rooted -- a function parameter,
`tmp_path`, a directory derived from it, a home or state directory -- names no
repository path, and its segments do not count as literals of the closure
(livespec-dev-tooling-bob7iv).

Each base and each binding becomes a `RootTerm`: rooted on its own, or rooted
through scope-resolved bindings, fixtures, attribute stores or imports that the
whole closure then solves. A base this module cannot classify is rooted, so
the literal segments of a `/` chain on it count: a name bound where no value
is recorded, a fixture nothing in the closure defines, and an import the
closure cannot resolve. Only the forms named here are read; a value reached
another way -- `getattr`, an alias, a helper defined in a test module and
imported by another -- is not, and a chain on it counts only as its other
rules allow. A class body binds attributes too, so a root held there is read
through `self` and `cls`, as an attribute, a method or a property.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Iterator, Mapping
from functools import partial

from livespec_dev_tooling._flake_retry_parameters import Thunk, fixture_name, parameter_sites
from livespec_dev_tooling._flake_retry_root_terms import (
    DOUBT,
    Key,
    RootTerm,
    TermContext,
    base_term,
    binding_key,
    through,
    union,
)
from livespec_dev_tooling._flake_retry_scopes import (
    Scope,
    ScopeIndex,
    binding_scope,
    owning_scope,
)
from livespec_dev_tooling._flake_retry_spans import EXACT, Span, crossed

__all__: list[str] = ["module_root_terms", "reached", "solve_keys"]

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _constant(*, term: RootTerm) -> Thunk:
    return lambda: term


def _target_sites(
    *, target: ast.expr, value: Thunk, scope: Scope, context: TermContext
) -> Iterator[tuple[Key, Thunk]]:
    """Bind a store target: a name, each name it unpacks, a subscript container or attribute."""
    if isinstance(target, ast.Name):
        owner = binding_scope(name=target.id, scope=scope, index=context.index)
        yield binding_key(name=target.id, scope=owner, context=context), value
        if owner.is_class:
            yield ("attribute", target.id), value
    elif isinstance(target, ast.Attribute):
        yield ("attribute", target.attr), value
    elif isinstance(target, ast.Starred):
        yield from _target_sites(target=target.value, value=value, scope=scope, context=context)
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _target_sites(target=element, value=value, scope=scope, context=context)
    else:
        yield from _container_sites(subscript=target, value=value, scope=scope, context=context)


def _container_sites(
    *, subscript: ast.expr, value: Thunk, scope: Scope, context: TermContext
) -> Iterator[tuple[Key, Thunk]]:
    """A subscript store binds its container: an attribute, or a name where it resolves."""
    container = getattr(subscript, "value", subscript)
    if isinstance(container, ast.Attribute):
        yield ("attribute", container.attr), value
        return
    name = str(getattr(container, "id", ""))
    owner = owning_scope(name=name, scope=scope, index=context.index)
    if owner is not None:
        yield binding_key(name=name, scope=owner, context=context), value


def _returned_term(*, scope: Scope, context: TermContext) -> RootTerm:
    """What a function returns or yields, read in the function's own scope."""
    return union(
        terms=(
            base_term(expression=value, context=context)
            for value in context.index.returns.get(id(scope), [])
        )
    )


def _function_sites(
    *, function: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, context: TermContext
) -> Iterator[tuple[Key, Thunk]]:
    """A function binds its name to what it returns or yields, and each parameter it takes."""
    body = function.body if isinstance(function.body, list) else [function.body]
    inner = context.index.scope_of[id(body[0])]
    outer = context.index.scope_of[id(function)]
    if not isinstance(function, ast.Lambda):
        returned = partial(_returned_term, scope=inner, context=context)
        yield binding_key(name=function.name, scope=outer, context=context), returned
        if outer.is_class:
            yield ("attribute", function.name), returned
        fixture = fixture_name(function=function)
        if fixture is not None:
            yield ("fixture", fixture), returned
    yield from parameter_sites(
        function=function,
        in_class=outer.is_class,
        key_of=lambda name: binding_key(name=name, scope=inner, context=context),
        context=context,
    )


def _import_term(*, alias: ast.alias, context: TermContext) -> RootTerm:
    """A name imported from a closure module is that module's binding; anything else is a doubt."""
    source = context.import_sources.get(id(alias))
    if source is None:
        return DOUBT
    return through(("export", f"{source}:{alias.name}"))


def _declaration_sites(
    *, node: ast.Import | ast.ImportFrom | ast.ClassDef, scope: Scope, context: TermContext
) -> Iterator[tuple[Key, Thunk]]:
    """An import binds each name it reads; a class binds its name to a doubt."""
    if isinstance(node, ast.ClassDef):
        owner = binding_scope(name=node.name, scope=scope, index=context.index)
        yield binding_key(name=node.name, scope=owner, context=context), _constant(term=DOUBT)
        return
    for alias in node.names:
        name = (alias.asname or alias.name).split(".")[0]
        owner = binding_scope(name=name, scope=scope, index=context.index)
        term = _constant(term=_import_term(alias=alias, context=context))
        yield binding_key(name=name, scope=owner, context=context), term


def _node_sites(*, node: ast.AST, context: TermContext) -> Iterator[tuple[Key, Thunk]]:
    """Every binding one syntax node makes, each with its term left unevaluated.

    An augmented `/=` keeps its target's base, so only another operator binds
    the target to its operand as well.
    """
    scope = context.index.scope_of[id(node)]
    pairs: list[tuple[ast.expr, ast.expr]] = []
    if isinstance(node, ast.Assign):
        pairs = [(target, node.value) for target in node.targets]
    elif isinstance(node, ast.AnnAssign | ast.NamedExpr) and node.value:
        pairs = [(node.target, node.value)]
    elif isinstance(node, ast.AugAssign):
        pairs = [] if isinstance(node.op, ast.Div) else [(node.target, node.value)]
    elif isinstance(node, ast.For | ast.AsyncFor | ast.comprehension):
        pairs = [(node.target, node.iter)]
    elif isinstance(node, ast.withitem) and node.optional_vars:
        pairs = [(node.optional_vars, node.context_expr)]
    elif isinstance(node, _FUNCTIONS):
        yield from _function_sites(function=node, context=context)
    elif isinstance(node, ast.Import | ast.ImportFrom | ast.ClassDef):
        yield from _declaration_sites(node=node, scope=scope, context=context)
    for target, value in pairs:
        term = partial(base_term, expression=value, context=context)
        yield from _target_sites(target=target, value=term, scope=scope, context=context)


def module_root_terms(
    *,
    index: ScopeIndex,
    module: str,
    bases: Iterable[ast.expr],
    import_sources: Mapping[int, str] | None = None,
    places: Mapping[int, str] | None = None,
    request_span: str | None = None,
) -> tuple[tuple[tuple[Key, RootTerm], ...], tuple[RootTerm, ...]]:
    """The term of each given base, and every binding term a closure can need from this module.

    A binding key of this module is read only by this module's own terms, so a
    binding is evaluated only when a base, a fixture, an attribute store or a
    module-level name another module imports reaches it; one this module never
    records a value for is a doubt. Fixtures, attribute stores and module-level
    names (as `export` keys) can be read across the closure, so each of them is
    evaluated.
    """
    context = TermContext(
        index=index,
        module=module,
        numbers={id(scope): number for number, scope in enumerate(index.scopes)},
        import_sources={} if import_sources is None else import_sources,
        places={} if places is None else places,
        request_span=request_span,
    )
    sites: dict[Key, list[Thunk]] = {}
    for node in index.nodes:
        for key, thunk in _node_sites(node=node, context=context):
            sites.setdefault(key, []).append(thunk)
    module_prefix = f"{module}:0:"
    for kind, label in list(sites):
        if kind == "binding" and label.startswith(module_prefix):
            export = ("export", f"{module}:{label.removeprefix(module_prefix)}")
            sites[export] = [_constant(term=through((kind, label)))]
    base_terms = tuple(base_term(expression=base, context=context) for base in bases)
    needed = [key for key in sites if key[0] != "binding"]
    needed.extend(key for term in base_terms for key in term.through)
    evaluated: dict[Key, RootTerm] = {}
    while needed:
        key = needed.pop()
        if key in evaluated or (key not in sites and key[0] != "binding"):
            continue
        thunks = sites.get(key, [_constant(term=DOUBT)])
        term = union(terms=(thunk() for thunk in thunks))
        evaluated[key] = term
        needed.extend(term.through)
    for kind, label in list(evaluated):
        if kind == "export":
            module_name = label.removeprefix(f"{module}:")
            evaluated[kind, label] = evaluated[("binding", f"{module_prefix}{module_name}")]
    return tuple(evaluated.items()), base_terms


def solve_keys(
    *, terms: Iterable[tuple[Key, RootTerm]], queries: Iterable[Key]
) -> tuple[frozenset[Key], dict[Key, frozenset[Span]]]:
    """Solve which queried keys are rooted, and where each lies (see `Span`).

    The walk follows only the keys the queries go through, so a closure's
    many unrelated bindings cost nothing. Rootedness crosses every `through`
    edge unchanged; a location crosses it as `crossed` says, widened by the
    dependent term's upward steps.
    """
    by_key: dict[Key, list[RootTerm]] = {}
    for key, term in terms:
        by_key.setdefault(key, []).append(term)
    walked = _walk(queries=queries, terms=by_key)
    rooted = _spread(
        walked=walked,
        terms=by_key,
        own=lambda term: frozenset({("", 0)} if term.rooted else ()),
        step=lambda _key, _term, values: values,
    )
    located = _spread(
        walked=walked,
        terms=by_key,
        own=lambda term: frozenset({*((place, EXACT) for place in term.places), *term.spans}),
        step=lambda key, term, values: crossed(
            values=values, ascent=term.ascent, exact_passes=key in term.evidence
        ),
    )
    return frozenset(rooted), located


def reached(*, term: RootTerm, located: dict[Key, frozenset[Span]]) -> frozenset[Span]:
    """Where the keys a term goes through place it, once its own upward steps are taken."""
    return frozenset(
        span
        for key in term.through
        for span in crossed(
            values=located.get(key, ()), ascent=term.ascent, exact_passes=key in term.evidence
        )
    )


_Step = Callable[[Key, RootTerm, frozenset[Span]], frozenset[Span]]


def _spread(
    *,
    walked: tuple[list[Key], dict[Key, list[tuple[Key, RootTerm]]]],
    terms: dict[Key, list[RootTerm]],
    own: Callable[[RootTerm], frozenset[Span]],
    step: _Step,
) -> dict[Key, frozenset[Span]]:
    """Carry each walked key's own values to every key that goes through it.

    A key passes on only what it newly gained, so a cycle of bindings ends
    once no key on it gains anything.
    """
    seeds, dependents = walked
    pending = [(key, own(term)) for key in seeds for term in terms[key]]
    found: dict[Key, set[Span]] = {}
    while pending:
        key, carried = pending.pop()
        known = found.setdefault(key, set())
        added = frozenset(carried - known)
        if not added:
            continue
        known.update(added)
        pending.extend(
            (dependent, step(key, term, added)) for dependent, term in dependents.get(key, ())
        )
    return {key: frozenset(values) for key, values in found.items() if values}


def _walk(
    *, queries: Iterable[Key], terms: dict[Key, list[RootTerm]]
) -> tuple[list[Key], dict[Key, list[tuple[Key, RootTerm]]]]:
    """Every key the queries reach through `through`, and each edge back to its dependent."""
    dependents: dict[Key, list[tuple[Key, RootTerm]]] = {}
    visited: list[Key] = []
    seen: set[Key] = set()
    pending = list(queries)
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        visited.extend([key] if key in terms else [])
        for term in terms.get(key, ()):
            pending.extend(term.through)
            for gone_through in term.through:
                dependents.setdefault(gone_through, []).append((key, term))
    return visited, dependents
