"""AST binding-name helpers for the flake-retry path analyzer."""

from __future__ import annotations

import ast

__all__: list[str] = ["bound_by", "parameter_names"]


def parameter_names(*, arguments: ast.arguments) -> list[str]:
    """Name every parameter a function signature binds in its own scope."""
    parameters = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    variadic = [parameter for parameter in (arguments.vararg, arguments.kwarg) if parameter]
    return [parameter.arg for parameter in (*parameters, *variadic)]


def bound_by(*, node: ast.AST) -> list[str]:
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
