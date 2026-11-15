"""Recognize request aliases that make a closure path impossible to locate exactly."""

from __future__ import annotations

import ast

__all__: list[str] = ["request_indirection"]


def request_indirection(*, tree: ast.AST) -> bool:
    """Whether an alias or helper hides pytest's request object from path analysis."""
    aliases = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Name)
        and node.value.id == "request"
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    passed = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in functions
        and any(getattr(argument, "id", "") == "request" for argument in node.args)
        for node in ast.walk(tree)
    )
    return bool(aliases) or passed
