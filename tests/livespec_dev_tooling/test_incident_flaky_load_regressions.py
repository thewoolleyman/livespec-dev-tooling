"""Regression guards for incident tests that must remain reliable under CPU pressure."""

from __future__ import annotations

import inspect

from tests.livespec_dev_tooling import test_incident_focused_evidence as focused_evidence


def test_escaped_descendant_drain_case_does_not_depend_on_nested_pytest_startup() -> None:
    source = inspect.getsource(
        focused_evidence.test_a_descendant_holding_the_output_open_cannot_outlast_the_bound
    )
    assert "measurement._run(" in source
    assert "_collect(" not in source
