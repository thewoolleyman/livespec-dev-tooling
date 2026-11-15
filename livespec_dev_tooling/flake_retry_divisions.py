"""Path-division helpers for the flake-retry path analyzer."""

from __future__ import annotations

import ast

__all__: list[str] = ["division_operands", "path_operands"]


def division_operands(*, expression: ast.expr) -> tuple[ast.expr, ...]:
    """Flatten one left-associative path-expression division chain."""
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        return (
            *division_operands(expression=expression.left),
            *division_operands(expression=expression.right),
        )
    return (expression,)


def path_operands(*, expression: ast.expr) -> tuple[ast.expr, ...] | None:
    """Return the ordered operands of one supported path construction."""
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        return division_operands(expression=expression)
    return _call_path_operands(call=expression) if isinstance(expression, ast.Call) else None


def _call_path_operands(*, call: ast.Call) -> tuple[ast.expr, ...] | None:
    """Return operands from a path-construction call, when its shape is known."""
    callee = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
    if callee == "join" and len(call.args) > 1:
        return tuple(call.args)
    if callee == "with_name" and isinstance(call.func, ast.Attribute) and call.args:
        return (call.func.value, call.args[0])
    if callee in {"Path", "PurePath", "PosixPath", "PurePosixPath"}:
        if len(call.args) > 1:
            return tuple(call.args)
        if len(call.args) == 1 and isinstance(call.args[0], ast.JoinedStr):
            literal_prefix = next(
                (
                    value.value
                    for value in call.args[0].values
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                ),
                "",
            )
            if literal_prefix.startswith("/"):
                return None
            formatted = [
                value.value
                for value in call.args[0].values
                if isinstance(value, ast.FormattedValue)
            ]
            if len(formatted) == 1:
                return (formatted[0],)
    return None
