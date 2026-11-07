"""Static repository-path literals collected from test path expressions."""

from __future__ import annotations

import ast
from pathlib import PurePosixPath

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

    A dynamic first operand is a root (for example, ``_ROOT / "ci-runner"``).
    A dynamic operand at any later position may be a repository path component,
    so callers must treat that closure as touched. A terminal component may be
    a file even without a suffix, so every multi-segment path also names its
    own parent directory, and a suffixless literal terminal is also a file-name
    literal (suffixed ones are already kept by the closure's literal scan).
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
        operands = _division_operands(expression=node)
        for position, operand in enumerate(operands):
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                segments.append(operand.value)
            elif position > 0:
                undeterminable = True
        for named_path in filter(None, ("/".join(segments),)):
            paths.add(named_path)
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
