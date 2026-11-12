"""Path-division helpers for the flake-retry path analyzer."""

from __future__ import annotations

import ast

__all__: list[str] = ["division_operands"]


def division_operands(*, expression: ast.expr) -> tuple[ast.expr, ...]:
    """Flatten one left-associative path-expression division chain."""
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        return (
            *division_operands(expression=expression.left),
            *division_operands(expression=expression.right),
        )
    return (expression,)
