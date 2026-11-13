"""Python binding scopes for the flake-retry path analyzer.

One walk of a module records the scope every node is evaluated in and what
each scope binds, so a name read anywhere resolves through the scope chain
(including `global` and `nonlocal` declarations) to the scope that owns it.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from livespec_dev_tooling.flake_retry_bindings import bound_by, parameter_names

__all__: list[str] = [
    "Scope",
    "ScopeIndex",
    "binding_scope",
    "index_scopes",
    "is_root_name",
    "owning_scope",
]


@dataclass(kw_only=True, eq=False)
class Scope:
    """One Python binding scope: the names it binds and those bound to the repository root."""

    parent: Scope | None
    is_class: bool
    bound: set[str] = field(default_factory=set)
    roots: set[str] = field(default_factory=set)
    outer: dict[str, bool] = field(default_factory=dict)


@dataclass(kw_only=True)
class ScopeIndex:
    """Every binding scope of one module and the scope each node is evaluated in."""

    scope_of: dict[int, Scope]
    scopes: list[Scope]
    assignments: list[tuple[list[ast.expr], ast.expr, Scope]]
    nodes: list[ast.AST] = field(default_factory=list)
    returns: dict[int, list[ast.expr]] = field(default_factory=dict)


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _open_scope(*, node: ast.AST, scope: Scope) -> tuple[Scope, frozenset[int]] | None:
    """Open the scope a function, class or comprehension node introduces, if it does."""
    if isinstance(node, _FUNCTIONS):
        inner = Scope(parent=scope, is_class=False)
        inner.bound.update(parameter_names(arguments=node.args))
        body = node.body if isinstance(node.body, list) else [node.body]
        return inner, frozenset(id(child) for child in body)
    if isinstance(node, ast.ClassDef):
        return Scope(parent=scope, is_class=True), frozenset(id(child) for child in node.body)
    if isinstance(node, _COMPREHENSIONS):
        return Scope(parent=scope, is_class=False), frozenset(
            id(child) for child in ast.iter_child_nodes(node)
        )
    return None


def index_scopes(*, tree: ast.AST) -> ScopeIndex:
    """Walk the module once, recording each node's scope and what every scope binds."""
    module = Scope(parent=None, is_class=False)
    index = ScopeIndex(scope_of={}, scopes=[module], assignments=[])
    pending: list[tuple[ast.AST, Scope]] = [(tree, module)]
    while pending:
        node, scope = pending.pop()
        index.scope_of[id(node)] = scope
        index.nodes.append(node)
        scope.bound.update(bound_by(node=node))
        if isinstance(node, ast.Return | ast.Yield | ast.YieldFrom) and node.value:
            index.returns.setdefault(id(scope), []).append(node.value)
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.value:
            targets: list[ast.expr] = (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            index.assignments.append((targets, node.value, scope))
        if isinstance(node, ast.Global | ast.Nonlocal):
            scope.outer.update((name, isinstance(node, ast.Global)) for name in node.names)
        opened = _open_scope(node=node, scope=scope)
        for child in ast.iter_child_nodes(node):
            inside = opened is not None and id(child) in opened[1]
            pending.append((child, opened[0] if opened is not None and inside else scope))
        if opened is not None:
            index.scopes.append(opened[0])
    return index


def binding_scope(*, name: str, scope: Scope, index: ScopeIndex) -> Scope:
    """Return the scope that owns ``name`` when this scope declares it outer."""
    declaration = scope.outer.get(name)
    if declaration is not False:
        return index.scopes[0] if declaration else scope
    current = scope.parent
    while current is not None and (current.is_class or name not in current.bound):
        current = current.parent
    return current or scope


def owning_scope(*, name: str, scope: Scope, index: ScopeIndex) -> Scope | None:
    """Return the scope where `name`, read in `scope`, resolves, or None when nothing binds it."""
    current: Scope | None = scope
    while current is not None:
        resolved = binding_scope(name=name, scope=current, index=index)
        if resolved is not current:
            return resolved
        if name in current.bound and (current is scope or not current.is_class):
            return current
        current = current.parent
    return None


def is_root_name(*, name: str, scope: Scope, index: ScopeIndex) -> bool:
    """Say whether `name`, read in `scope`, is bound to the repository root where it resolves."""
    owner = owning_scope(name=name, scope=scope, index=index)
    return owner is not None and name in owner.roots
