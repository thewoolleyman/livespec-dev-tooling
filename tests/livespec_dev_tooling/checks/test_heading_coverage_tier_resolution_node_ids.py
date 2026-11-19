"""Acceptance coverage for pytest-style node IDs in scenario-tier resolution."""

from __future__ import annotations

from pathlib import Path

from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._heading_coverage_tier_resolution import (
    DEFAULT_SCENARIO_TIERS,
    scenario_tier_violations,
)

__all__: list[str] = []


def test_path_node_id_with_integration_marked_function_is_compliant(*, tmp_path: Path) -> None:
    """A pytest ``path/to/test.py::test_name`` node ID resolves its function marker."""
    test_file = tmp_path / "tests" / "other" / "test_x.py"
    test_file.parent.mkdir(parents=True)
    _ = test_file.write_text(
        "import pytest\n\n\n@pytest.mark.integration\ndef test_y() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    entry: dict[str, object] = {
        "spec_file": "scenarios.md",
        "test": "tests/other/test_x.py::test_y",
    }

    resolved = scenario_tier_violations(
        repo_root=tmp_path, entries=[entry], tiers=DEFAULT_SCENARIO_TIERS
    )

    assert isinstance(resolved, IOSuccess), f"expected a resolvable scan; got {resolved!r}"
    assert unsafe_perform_io(resolved.unwrap()) == []
