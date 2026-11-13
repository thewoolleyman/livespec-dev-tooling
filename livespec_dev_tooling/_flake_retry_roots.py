"""Repository-rooted path-expression bases for the flake-retry closure analysis.

SPECIFICATION non-functional-requirements.md "Untouched-test retry": a path
expression whose base is not repository-rooted -- a function parameter,
`tmp_path`, a directory derived from it, a home or state directory -- names no
repository path, and its segments do not count as literals of the closure
(livespec-dev-tooling-bob7iv).

Each base and each binding becomes a `RootTerm`: rooted on its own, or rooted
through scope-resolved bindings, fixtures or attribute stores that the whole
closure then solves. Anything this module cannot classify is rooted, so a
doubt keeps a test touched.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import partial

from livespec_dev_tooling._flake_retry_scopes import (
    Scope,
    ScopeIndex,
    binding_scope,
    owning_scope,
)
from livespec_dev_tooling.flake_retry_divisions import division_operands

__all__: list[str] = ["Key", "RootTerm", "module_root_terms", "rooted_keys"]

Key = tuple[str, str]

_TEMPORARY_NAMES = frozenset({"tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory"})
_TEMPORARY_CALLS = frozenset(
    (
        "home expanduser mktemp mkdtemp mkstemp gettempdir getbasetemp "
        "TemporaryDirectory NamedTemporaryFile"
    ).split()
)
_WORKING_DIRECTORY_CALLS = frozenset({"cwd", "getcwd"})
_PATH_CONSTRUCTORS = frozenset(
    (
        "Path PurePath PosixPath PurePosixPath str fspath " "abspath realpath normpath dirname join"
    ).split()
)
_ROOT_ATTRIBUTES = frozenset({"__file__", "rootpath", "rootdir"})
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


@dataclass(frozen=True, kw_only=True)
class RootTerm:
    """Rooted on its own, or rooted when any key it goes through is rooted."""

    rooted: bool
    through: frozenset[Key]


_ROOTED = RootTerm(rooted=True, through=frozenset())
_NOT_ROOTED = RootTerm(rooted=False, through=frozenset())

Thunk = Callable[[], RootTerm]


def _rooted() -> RootTerm:
    return _ROOTED


@dataclass(frozen=True, kw_only=True)
class _Context:
    """One module's scope index and the label that keeps its binding keys unique."""

    index: ScopeIndex
    module: str
    numbers: dict[int, int]


def _union(*, terms: Iterable[RootTerm]) -> RootTerm:
    collected = list(terms)
    return RootTerm(
        rooted=any(term.rooted for term in collected),
        through=frozenset(key for term in collected for key in term.through),
    )


def _binding_key(*, name: str, scope: Scope, context: _Context) -> Key:
    return ("binding", f"{context.module}:{context.numbers[id(scope)]}:{name}")


def _name_term(*, name: str, scope: Scope, context: _Context) -> RootTerm:
    """A name is rooted through its binding where it resolves; an unbound name is unknown."""
    if name in _TEMPORARY_NAMES:
        return _NOT_ROOTED
    owner = owning_scope(name=name, scope=scope, index=context.index)
    if name == "__file__" or owner is None:
        return _ROOTED
    return RootTerm(
        rooted=False, through=frozenset({_binding_key(name=name, scope=owner, context=context)})
    )


def _call_term(*, call: ast.Call, context: _Context) -> RootTerm:
    """A call is rooted through its receiver, its path argument or the function it names."""
    func = call.func
    callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    first = call.args[0] if call.args else None
    if callee in _TEMPORARY_CALLS:
        return _NOT_ROOTED
    if callee in _WORKING_DIRECTORY_CALLS:
        return _ROOTED
    if callee == "getfixturevalue":
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return RootTerm(rooted=False, through=frozenset({("fixture", first.value)}))
        return _ROOTED
    if callee in _PATH_CONSTRUCTORS:
        return _ROOTED if first is None else _base_term(expression=first, context=context)
    target = func.value if isinstance(func, ast.Attribute) else func
    return _base_term(expression=target, context=context)


def _attribute_term(*, attribute: ast.Attribute, context: _Context) -> RootTerm:
    """An attribute is rooted when it names a root, or through its object or an attribute store."""
    if attribute.attr in _ROOT_ATTRIBUTES:
        return _ROOTED
    stored = RootTerm(rooted=False, through=frozenset({("attribute", attribute.attr)}))
    return _union(terms=(_base_term(expression=attribute.value, context=context), stored))


def _base_term(*, expression: ast.expr, context: _Context) -> RootTerm:
    """Whether a path expression's base is repository-rooted, and through which keys."""
    if isinstance(expression, ast.Constant):
        term = _ROOTED if isinstance(expression.value, str) else _NOT_ROOTED
    elif isinstance(expression, ast.Name):
        scope = context.index.scope_of[id(expression)]
        term = _name_term(name=expression.id, scope=scope, context=context)
    elif isinstance(expression, ast.Attribute):
        term = _attribute_term(attribute=expression, context=context)
    elif isinstance(expression, ast.Subscript):
        term = _base_term(expression=expression.value, context=context)
    elif isinstance(expression, ast.Call):
        term = _call_term(call=expression, context=context)
    elif isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        term = _base_term(expression=division_operands(expression=expression)[0], context=context)
    else:
        children = [
            child for child in ast.iter_child_nodes(expression) if isinstance(child, ast.expr)
        ]
        term = _union(terms=(_base_term(expression=child, context=context) for child in children))
        term = term if children else _ROOTED
    return term


def _target_sites(
    *, target: ast.expr, value: Thunk, scope: Scope, context: _Context
) -> Iterator[tuple[Key, Thunk]]:
    """Bind a store target: a name, each name it unpacks, a subscript container or attribute."""
    if isinstance(target, ast.Name):
        owner = binding_scope(name=target.id, scope=scope, index=context.index)
        yield _binding_key(name=target.id, scope=owner, context=context), value
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
    *, subscript: ast.expr, value: Thunk, scope: Scope, context: _Context
) -> Iterator[tuple[Key, Thunk]]:
    """A subscript store binds its container: an attribute, or a name where it resolves."""
    container = getattr(subscript, "value", subscript)
    if isinstance(container, ast.Attribute):
        yield ("attribute", container.attr), value
        return
    name = str(getattr(container, "id", ""))
    owner = owning_scope(name=name, scope=scope, index=context.index)
    if owner is not None:
        yield _binding_key(name=name, scope=owner, context=context), value


def _fixture_name(*, function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """The name a fixture is requested by; `*` when it cannot be read; None for a plain function."""
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if getattr(target, "id", getattr(target, "attr", "")) != "fixture":
            continue
        keywords = decorator.keywords if isinstance(decorator, ast.Call) else []
        for keyword in keywords:
            if keyword.arg == "name":
                value = keyword.value
                literal = isinstance(value, ast.Constant) and isinstance(value.value, str)
                return str(getattr(value, "value", "")) if literal else "*"
        return function.name
    return None


def _returned_term(*, scope: Scope, context: _Context) -> RootTerm:
    """What a function returns or yields, read in the function's own scope."""
    return _union(
        terms=(
            _base_term(expression=value, context=context)
            for value in context.index.returns.get(id(scope), [])
        )
    )


def _parameter_term(*, parameter: ast.arg, default: ast.expr | None, context: _Context) -> RootTerm:
    """A parameter is rooted through a fixture of its name, or through a rooted default."""
    requested = RootTerm(
        rooted=False, through=frozenset({("fixture", parameter.arg), ("fixture", "*")})
    )
    if default is None:
        return requested
    return _union(terms=(requested, _base_term(expression=default, context=context)))


def _function_sites(
    *, function: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, context: _Context
) -> Iterator[tuple[Key, Thunk]]:
    """A function binds its name to what it returns or yields, and each parameter it takes."""
    body = function.body if isinstance(function.body, list) else [function.body]
    inner = context.index.scope_of[id(body[0])]
    if not isinstance(function, ast.Lambda):
        outer = context.index.scope_of[id(function)]
        returned = partial(_returned_term, scope=inner, context=context)
        yield _binding_key(name=function.name, scope=outer, context=context), returned
        fixture = _fixture_name(function=function)
        if fixture is not None:
            yield ("fixture", fixture), returned
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults = dict(zip(reversed(positional), reversed(arguments.defaults), strict=False))
    defaults.update(
        (parameter, default)
        for parameter, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
        if default is not None
    )
    for parameter in (*positional, *arguments.kwonlyargs):
        if parameter.arg not in _TEMPORARY_NAMES:
            term = partial(
                _parameter_term,
                parameter=parameter,
                default=defaults.get(parameter),
                context=context,
            )
            yield _binding_key(name=parameter.arg, scope=inner, context=context), term


def _node_sites(*, node: ast.AST, context: _Context) -> Iterator[tuple[Key, Thunk]]:
    """Every binding one syntax node makes, each with its term left unevaluated."""
    scope = context.index.scope_of[id(node)]
    pairs: list[tuple[ast.expr, ast.expr]] = []
    if isinstance(node, ast.Assign):
        pairs = [(target, node.value) for target in node.targets]
    elif isinstance(node, ast.AnnAssign | ast.NamedExpr) and node.value:
        pairs = [(node.target, node.value)]
    elif isinstance(node, ast.For | ast.AsyncFor | ast.comprehension):
        pairs = [(node.target, node.iter)]
    elif isinstance(node, ast.withitem) and node.optional_vars:
        pairs = [(node.optional_vars, node.context_expr)]
    elif isinstance(node, _FUNCTIONS):
        yield from _function_sites(function=node, context=context)
    elif isinstance(node, ast.ClassDef | ast.Import | ast.ImportFrom):
        names = (
            [node.name]
            if isinstance(node, ast.ClassDef)
            else [(alias.asname or alias.name).split(".")[0] for alias in node.names]
        )
        for name in names:
            owner = binding_scope(name=name, scope=scope, index=context.index)
            yield _binding_key(name=name, scope=owner, context=context), _rooted
    for target, value in pairs:
        term = partial(_base_term, expression=value, context=context)
        yield from _target_sites(target=target, value=term, scope=scope, context=context)


def module_root_terms(
    *, index: ScopeIndex, module: str, bases: Iterable[ast.expr]
) -> tuple[tuple[tuple[Key, RootTerm], ...], tuple[RootTerm, ...]]:
    """The term of each given base, and every binding term a closure can need from this module.

    A binding key of this module is read only by this module's own terms, so a
    binding is evaluated only when a base, a fixture or an attribute store
    reaches it. Fixtures and attribute stores can be read across the closure,
    so each of them is evaluated.
    """
    context = _Context(
        index=index,
        module=module,
        numbers={id(scope): number for number, scope in enumerate(index.scopes)},
    )
    sites: dict[Key, list[Thunk]] = {}
    for node in index.nodes:
        for key, thunk in _node_sites(node=node, context=context):
            sites.setdefault(key, []).append(thunk)
    base_terms = tuple(_base_term(expression=base, context=context) for base in bases)
    needed = [key for key in sites if key[0] != "binding"]
    needed.extend(key for term in base_terms for key in term.through)
    evaluated: dict[Key, RootTerm] = {}
    while needed:
        key = needed.pop()
        if key in evaluated or key not in sites:
            continue
        term = _union(terms=(thunk() for thunk in sites[key]))
        evaluated[key] = term
        needed.extend(term.through)
    return tuple(evaluated.items()), base_terms


def rooted_keys(*, terms: Iterable[tuple[Key, RootTerm]]) -> frozenset[Key]:
    """Solve every key that is rooted on its own or through a rooted key."""
    dependents: dict[Key, list[Key]] = {}
    pending: list[Key] = []
    for key, term in terms:
        if term.rooted:
            pending.append(key)
        for through in term.through:
            dependents.setdefault(through, []).append(key)
    rooted: set[Key] = set()
    while pending:
        key = pending.pop()
        rooted.add(key)
        pending.extend(dependents.pop(key, ()))
    return frozenset(rooted)
