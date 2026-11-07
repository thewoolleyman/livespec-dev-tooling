"""Static repository-path literals collected from test path expressions."""

from __future__ import annotations

import ast
from pathlib import Path

__all__: list[str] = ["path_literals"]


def _division_operands(*, expression: ast.expr) -> tuple[ast.expr, ...]:
    """Flatten one left-associative path-expression division chain."""
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        return (
            *_division_operands(expression=expression.left),
            *_division_operands(expression=expression.right),
        )
    return (expression,)


def path_literals(*, tree: ast.AST) -> tuple[set[str], bool]:
    """Return named literal paths and whether a path segment cannot be resolved.

    A dynamic root before literal components is normal (for example, ``_ROOT /
    "ci-runner"``). A dynamic component after one of those components leaves
    the repository path uncertain, so callers must treat that closure as
    touched.
    """
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
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
            continue
        if id(node) in nested_divisions:
            continue
        segments: list[str] = []
        saw_literal = False
        for operand in _division_operands(expression=node):
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                saw_literal = True
                segments.append(operand.value)
            elif saw_literal:
                undeterminable = True
        for named_path in filter(None, ("/".join(segments),)):
            paths.add(named_path)
            if Path(named_path).suffix and "/" in named_path:
                paths.add(named_path.rsplit("/", maxsplit=1)[0])
    return paths, undeterminable
