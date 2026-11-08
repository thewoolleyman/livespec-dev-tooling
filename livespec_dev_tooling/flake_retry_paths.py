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


def _path_names(*, operands: tuple[ast.expr, ...], repo_root: Path | None) -> tuple[set[str], bool]:
    """Collect names for one division expression, conservatively on dynamic segments."""
    has_literal = any(
        isinstance(operand, ast.Constant) and isinstance(operand.value, str) and operand.value
        for operand in operands
    )
    if not has_literal:
        return set(), False
    segments: list[str] = []
    undeterminable = False
    for position, operand in enumerate(operands):
        if isinstance(operand, ast.Constant) and isinstance(operand.value, str) and operand.value:
            segments.append(operand.value)
        elif position > 0:
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


def path_literals(*, tree: ast.AST, repo_root: Path | None = None) -> tuple[set[str], bool]:
    """Return named literal paths and whether a path segment cannot be resolved."""
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
            operands=_division_operands(expression=node), repo_root=repo_root
        )
        paths.update(names)
        undeterminable = undeterminable or is_undeterminable
    return paths, undeterminable
