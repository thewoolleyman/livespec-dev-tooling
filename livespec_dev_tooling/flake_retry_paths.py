from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

__all__: list[str] = ["path_literals"]


def _division_operands(*, expression: ast.expr) -> tuple[ast.expr, ...]:
    """Flatten one left-associative path-expression division chain."""
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        return (
            *_division_operands(expression=expression.left),
            *_division_operands(expression=expression.right),
        )
    return (expression,)


@dataclass(kw_only=True, eq=False)
class _Scope:
    """One Python binding scope: the names it binds and those bound to the repository root."""

    parent: _Scope | None
    is_class: bool
    bound: set[str] = field(default_factory=set)
    roots: set[str] = field(default_factory=set)


@dataclass(kw_only=True)
class _ScopeIndex:
    """Every binding scope of one module and the scope each node is evaluated in."""

    scope_of: dict[int, _Scope]
    scopes: list[_Scope]
    assignments: list[tuple[ast.Assign, _Scope]]
    declared_outer: set[str]


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _parameter_names(*, arguments: ast.arguments) -> list[str]:
    """Name every parameter a function signature binds in the function's own scope."""
    parameters = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    variadic = [parameter for parameter in (arguments.vararg, arguments.kwarg) if parameter]
    return [parameter.arg for parameter in (*parameters, *variadic)]


def _bound_by(*, node: ast.AST) -> list[str]:
    """Name what this node binds in the scope the node itself is evaluated in."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
        return [node.id]
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return [node.name]
    if isinstance(node, ast.Import | ast.ImportFrom):
        return [(alias.asname or alias.name).split(".")[0] for alias in node.names]
    if isinstance(node, ast.ExceptHandler) and node.name is not None:
        return [node.name]
    return []


def _open_scope(*, node: ast.AST, scope: _Scope) -> tuple[_Scope, frozenset[int]] | None:
    """Open the scope a function, class or comprehension node introduces, if it does."""
    if isinstance(node, _FUNCTIONS):
        inner = _Scope(parent=scope, is_class=False)
        inner.bound.update(_parameter_names(arguments=node.args))
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
    index = _ScopeIndex(scope_of={}, scopes=[module], assignments=[], declared_outer=set())
    pending: list[tuple[ast.AST, _Scope]] = [(tree, module)]
    while pending:
        node, scope = pending.pop()
        index.scope_of[id(node)] = scope
        scope.bound.update(_bound_by(node=node))
        if isinstance(node, ast.Assign):
            index.assignments.append((node, scope))
        if isinstance(node, ast.Global | ast.Nonlocal):
            index.declared_outer.update(node.names)
        opened = _open_scope(node=node, scope=scope)
        for child in ast.iter_child_nodes(node):
            inside = opened is not None and id(child) in opened[1]
            pending.append((child, opened[0] if opened is not None and inside else scope))
        if opened is not None:
            index.scopes.append(opened[0])
    return index


def _is_root_name(*, name: str, scope: _Scope, index: _ScopeIndex) -> bool:
    """Say whether `name`, read in `scope`, is bound to the repository root where it resolves."""
    if name in index.declared_outer:
        return any(name in each.roots for each in index.scopes)
    current: _Scope | None = scope
    while current is not None:
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
        base = _path_from_file_expression(
            expression=expression.func.value,
            scope=scope,
            index=index,
            source_path=source_path,
            repo_root=repo_root,
        )
        return None if base is None else base.resolve()
    if isinstance(expression, ast.Attribute) and expression.attr == "parent":
        base = _path_from_file_expression(
            expression=expression.value,
            scope=scope,
            index=index,
            source_path=source_path,
            repo_root=repo_root,
        )
        return None if base is None else base.parent
    if (
        isinstance(expression, ast.Subscript)
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == "parents"
        and isinstance(expression.slice, ast.Constant)
        and isinstance(expression.slice.value, int)
        and not isinstance(expression.slice.value, bool)
    ):
        base = _path_from_file_expression(
            expression=expression.value.value,
            scope=scope,
            index=index,
            source_path=source_path,
            repo_root=repo_root,
        )
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
        for assignment, scope in index.assignments:
            resolved = _path_from_file_expression(
                expression=assignment.value,
                scope=scope,
                index=index,
                source_path=source_path,
                repo_root=resolved_root,
            )
            if resolved != resolved_root:
                continue
            for target in assignment.targets:
                if isinstance(target, ast.Name) and target.id not in scope.roots:
                    scope.roots.add(target.id)
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
    first = operands[0]
    dynamic_segments_are_undeterminable = (
        repository_root_expression_ids is None
        or (isinstance(first, ast.Constant) and isinstance(first.value, str) and bool(first.value))
        or (id(first) in repository_root_expression_ids)
    )
    for position, operand in enumerate(operands):
        if isinstance(operand, ast.Constant) and isinstance(operand.value, str) and operand.value:
            segments.append(operand.value)
        elif position > 0 and dynamic_segments_are_undeterminable:
            undeterminable = True
    named_path = "/".join(segments)
    paths = {named_path}
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
            operands=_division_operands(expression=node),
            repo_root=repo_root,
            repository_root_expression_ids=root_expression_ids,
        )
        paths.update(names)
        undeterminable = undeterminable or is_undeterminable
    return paths, undeterminable
