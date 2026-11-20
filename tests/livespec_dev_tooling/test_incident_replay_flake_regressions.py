"""Regression guards for replay-suite tests that previously raced under gate load."""

from __future__ import annotations

import ast
from pathlib import Path


_FOCUSED_EVIDENCE_TEST = Path(__file__).with_name("test_incident_focused_evidence.py")
_ESCAPED_DESCENDANT_CASE = "test_a_descendant_holding_the_output_open_cannot_outlast_the_bound"


def _calls_in(*, function: ast.FunctionDef) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_the_escaped_descendant_regression_does_not_reenter_pytest_under_its_deadline() -> None:
    """The nested pytest startup raced the deadline before its child existed."""
    module = ast.parse(_FOCUSED_EVIDENCE_TEST.read_text())
    case = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == _ESCAPED_DESCENDANT_CASE
    )
    assert "_collect" not in _calls_in(function=case)
