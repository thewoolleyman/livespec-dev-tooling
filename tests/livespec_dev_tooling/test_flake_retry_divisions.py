"""The flake-retry division helper is shipped with its analyzer."""

from __future__ import annotations

import ast

from livespec_dev_tooling.flake_retry_divisions import division_operands


def test_division_operands_flattens_a_path_expression() -> None:
    """Nested path divisions preserve the operands' left-to-right order."""
    expression = ast.parse("root / 'ci-runner' / name").body[0]

    assert isinstance(expression, ast.Expr)
    assert [ast.unparse(operand) for operand in division_operands(expression=expression.value)] == [
        "root",
        "'ci-runner'",
        "name",
    ]
