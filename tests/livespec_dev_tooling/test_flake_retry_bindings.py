"""The flake-retry binding helpers are shipped with their analyzer."""

from __future__ import annotations

import ast

from livespec_dev_tooling.flake_retry_bindings import bound_by, parameter_names


def test_binding_helpers_name_function_parameters_and_bindings() -> None:
    """Scope analysis receives names from public AST binding helpers."""
    tree = ast.parse("def task(first, /, second, *rest, named, **options):\n    return first")
    function = tree.body[0]

    assert isinstance(function, ast.FunctionDef)
    assert parameter_names(arguments=function.args) == [
        "first",
        "second",
        "named",
        "rest",
        "options",
    ]
    assert bound_by(node=function) == ["task"]
