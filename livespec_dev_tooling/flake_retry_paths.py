"""Static repository-path literals collected from test path expressions."""

from __future__ import annotations

import ast
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


def _path_from_file_expression(
    *,
    expression: ast.expr,
    repository_root_names: frozenset[str],
    source_path: Path,
    repo_root: Path,
) -> Path | None:
    """Resolve the limited ``Path(__file__)`` forms that can bind the repository root."""
    if isinstance(expression, ast.Name):
        return repo_root if expression.id in repository_root_names else None
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
            repository_root_names=repository_root_names,
            source_path=source_path,
            repo_root=repo_root,
        )
        return None if base is None else base.resolve()
    if isinstance(expression, ast.Attribute) and expression.attr == "parent":
        base = _path_from_file_expression(
            expression=expression.value,
            repository_root_names=repository_root_names,
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
            repository_root_names=repository_root_names,
            source_path=source_path,
            repo_root=repo_root,
        )
        index = expression.slice.value
        if base is not None and 0 <= index < len(base.parents):
            return base.parents[index]
    return None


def _repository_root_context(
    *, tree: ast.AST, source_path: Path | None, repo_root: Path | None
) -> tuple[frozenset[str], frozenset[int]]:
    """Find names and expressions statically bound to this module's repository root."""
    if source_path is None or repo_root is None:
        return frozenset(), frozenset()
    resolved_root = repo_root.resolve()
    names: set[str] = set()
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    changed = True
    while changed:
        changed = False
        for assignment in assignments:
            resolved = _path_from_file_expression(
                expression=assignment.value,
                repository_root_names=frozenset(names),
                source_path=source_path,
                repo_root=resolved_root,
            )
            if resolved != resolved_root:
                continue
            for target in assignment.targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.add(target.id)
                    changed = True
    expression_ids = {
        id(expression)
        for expression in ast.walk(tree)
        if isinstance(expression, ast.expr)
        and _path_from_file_expression(
            expression=expression,
            repository_root_names=frozenset(names),
            source_path=source_path,
            repo_root=resolved_root,
        )
        == resolved_root
    }
    return frozenset(names), frozenset(expression_ids)


def _path_names(
    *,
    operands: tuple[ast.expr, ...],
    repo_root: Path | None,
    repository_root_names: frozenset[str] | None,
    repository_root_expression_ids: frozenset[int],
) -> tuple[set[str], bool]:
    """Collect names for one division expression, conservatively on dynamic segments."""
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
        repository_root_names is None
        or (isinstance(first, ast.Constant) and isinstance(first.value, str) and bool(first.value))
        or (isinstance(first, ast.Name) and first.id in repository_root_names)
        or (id(first) in repository_root_expression_ids)
    )
    for position, operand in enumerate(operands):
        if isinstance(operand, ast.Constant) and isinstance(operand.value, str) and operand.value:
            segments.append(operand.value)
        elif position > 0 and dynamic_segments_are_undeterminable:
            undeterminable = True
    named_path = "/".join(segments)
    paths = {named_path}
    resolved = None if repo_root is None else repo_root / named_path
    if resolved is not None and resolved.is_dir():
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
    root_names, root_expression_ids = _repository_root_context(
        tree=tree, source_path=source_path, repo_root=repo_root
    )
    effective_root_names = root_names if source_path is not None and repo_root is not None else None
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
            repository_root_names=effective_root_names,
            repository_root_expression_ids=root_expression_ids,
        )
        paths.update(names)
        undeterminable = undeterminable or is_undeterminable
    return paths, undeterminable
