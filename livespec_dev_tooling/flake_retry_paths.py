from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path, PurePosixPath

from livespec_dev_tooling.flake_retry_bindings import bound_by, parameter_names
from livespec_dev_tooling.flake_retry_divisions import division_operands

__all__: list[str] = ["path_literals"]


@dataclass(kw_only=True, eq=False)
class _Scope:
    """One Python binding scope: the names it binds and those bound to the repository root."""

    parent: _Scope | None
    is_class: bool
    bound: set[str] = field(default_factory=set)
    roots: set[str] = field(default_factory=set)
    outer: dict[str, bool] = field(default_factory=dict)


@dataclass(kw_only=True)
class _ScopeIndex:
    """Every binding scope of one module and the scope each node is evaluated in."""

    scope_of: dict[int, _Scope]
    scopes: list[_Scope]
    assignments: list[tuple[list[ast.expr], ast.expr, _Scope]]


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _open_scope(*, node: ast.AST, scope: _Scope) -> tuple[_Scope, frozenset[int]] | None:
    """Open the scope a function, class or comprehension node introduces, if it does."""
    if isinstance(node, _FUNCTIONS):
        inner = _Scope(parent=scope, is_class=False)
        inner.bound.update(parameter_names(arguments=node.args))
        body = node.body if isinstance(node.body, list) else [node.body]
        return inner, frozenset(id(child) for child in body)
    if isinstance(node, ast.ClassDef):
        return _Scope(parent=scope, is_class=True), frozenset(id(child) for child in node.body)
    if isinstance(node, _COMPREHENSIONS):
        return _Scope(parent=scope, is_class=False), frozenset(
            id(child) for child in ast.iter_child_nodes(node)
        )
    return None


def _index_scopes(*, tree: ast.AST) -> _ScopeIndex:
    """Walk the module once, recording each node's scope and what every scope binds."""
    module = _Scope(parent=None, is_class=False)
    index = _ScopeIndex(scope_of={}, scopes=[module], assignments=[])
    pending: list[tuple[ast.AST, _Scope]] = [(tree, module)]
    while pending:
        node, scope = pending.pop()
        index.scope_of[id(node)] = scope
        scope.bound.update(bound_by(node=node))
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


def _binding_scope(*, name: str, scope: _Scope, index: _ScopeIndex) -> _Scope:
    """Return the scope that owns ``name`` when this scope declares it outer."""
    declaration = scope.outer.get(name)
    if declaration is not False:
        return index.scopes[0] if declaration else scope
    current = scope.parent
    while current is not None and (current.is_class or name not in current.bound):
        current = current.parent
    return current or scope


def _is_root_name(*, name: str, scope: _Scope, index: _ScopeIndex) -> bool:
    """Say whether `name`, read in `scope`, is bound to the repository root where it resolves."""
    current: _Scope | None = scope
    while current is not None:
        resolved = _binding_scope(name=name, scope=current, index=index)
        if resolved is not current:
            return name in resolved.roots
        if name in current.bound and (current is scope or not current.is_class):
            return name in current.roots
        current = current.parent
    return False


def _path_from_file_expression(
    *,
    expression: ast.expr,
    scope: _Scope,
    index: _ScopeIndex,
    source_path: Path,
    repo_root: Path,
) -> Path | None:
    """Resolve the limited ``Path(__file__)`` forms that can bind the repository root."""
    again = partial(
        _path_from_file_expression,
        scope=scope,
        index=index,
        source_path=source_path,
        repo_root=repo_root,
    )
    if isinstance(expression, ast.Name):
        return repo_root if _is_root_name(name=expression.id, scope=scope, index=index) else None
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "Path"
        and len(expression.args) == 1
        and isinstance(expression.args[0], ast.Name)
        and expression.args[0].id == "__file__"
    ):
        return source_path
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and expression.func.attr == "resolve"
    ):
        base = again(expression=expression.func.value)
        return None if base is None else base.resolve()
    if isinstance(expression, ast.Attribute) and expression.attr == "parent":
        base = again(expression=expression.value)
        return None if base is None else base.parent
    if (
        isinstance(expression, ast.Subscript)
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == "parents"
        and isinstance(expression.slice, ast.Constant)
        and isinstance(expression.slice.value, int)
        and not isinstance(expression.slice.value, bool)
    ):
        base = again(expression=expression.value.value)
        position = expression.slice.value
        if base is not None and 0 <= position < len(base.parents):
            return base.parents[position]
    return None


def _repository_root_context(
    *, tree: ast.AST, source_path: Path | None, repo_root: Path | None
) -> frozenset[int] | None:
    """Find expressions statically bound to this module's repository root.

    Returns None when the module's location is unknown, so no expression can be
    shown to be anything other than a repository path.
    """
    if source_path is None or repo_root is None:
        return None
    resolved_root = repo_root.resolve()
    index = _index_scopes(tree=tree)
    changed = True
    while changed:
        changed = False
        for targets, value, scope in index.assignments:
            resolved = _path_from_file_expression(
                expression=value,
                scope=scope,
                index=index,
                source_path=source_path,
                repo_root=resolved_root,
            )
            if resolved != resolved_root:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                target_scope = _binding_scope(name=target.id, scope=scope, index=index)
                target_scope.bound.add(target.id)
                if target.id not in target_scope.roots:
                    target_scope.roots.add(target.id)
                    changed = True
    return frozenset(
        id(expression)
        for expression in ast.walk(tree)
        if isinstance(expression, ast.expr)
        and _path_from_file_expression(
            expression=expression,
            scope=index.scope_of[id(expression)],
            index=index,
            source_path=source_path,
            repo_root=resolved_root,
        )
        == resolved_root
    )


def _path_names(
    *,
    operands: tuple[ast.expr, ...],
    repo_root: Path | None,
    repository_root_expression_ids: frozenset[int] | None,
) -> tuple[set[str], bool]:
    has_literal = any(
        isinstance(operand, ast.Constant) and isinstance(operand.value, str) and operand.value
        for operand in operands
    )
    if not has_literal:
        return set(), False
    segments: list[str] = []
    undeterminable = False
    dynamic_segments_are_undeterminable = (
        repository_root_expression_ids is None
        or (
            isinstance(operands[0], ast.Constant)
            and bool(operands[0].value)
            and isinstance(operands[0].value, str)
        )
        or (id(operands[0]) in repository_root_expression_ids)
    )
    for position, operand in enumerate(operands):
        if isinstance(operand, ast.Constant) and isinstance(operand.value, str) and operand.value:
            segments.append(operand.value)
        elif position > 0 and dynamic_segments_are_undeterminable:
            undeterminable = True
    paths = {named_path := "/".join(segments)}
    if repo_root is not None and (repo_root / named_path).is_dir():
        return paths, undeterminable
    if "/" in named_path:
        paths.add(named_path.rsplit("/", maxsplit=1)[0])
    final = operands[-1]
    if (
        isinstance(final, ast.Constant)
        and isinstance(final.value, str)
        and not PurePosixPath(final.value).suffix
    ):
        paths.add(final.value)
    return paths, undeterminable


def path_literals(
    *,
    tree: ast.AST,
    repo_root: Path | None = None,
    source_path: Path | None = None,
) -> tuple[set[str], bool]:
    """Return named literal paths and whether a path segment cannot be resolved."""
    root_expression_ids = _repository_root_context(
        tree=tree, source_path=source_path, repo_root=repo_root
    )
    nested_divisions = {
        id(child)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
        for child in (node.left, node.right)
        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Div)
    }
    paths: set[str] = set()
    undeterminable = False
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.BinOp)
            or not isinstance(node.op, ast.Div)
            or id(node) in nested_divisions
        ):
            continue
        names, is_undeterminable = _path_names(
            operands=division_operands(expression=node),
            repo_root=repo_root,
            repository_root_expression_ids=root_expression_ids,
        )
        paths.update(names)
        undeterminable = undeterminable or is_undeterminable
    return paths, undeterminable
