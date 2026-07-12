"""Mirror-paired test for `livespec_dev_tooling/checks/_heading_coverage_tier_resolution.py`.

The private sibling module carries direction 4 of `heading_coverage` — the
`scenarios.md` integration-tier resolution (allowlist-prefix test + static AST
marker scan) extracted at the LLOC-reduction split. The direction's end-to-end
coverage lives in `test_heading_coverage.py` (exercised outside-in through the
parent check's subprocess contract); THIS file unit-tests `scenario_tier_violations`
directly, pinning the public surface and each compliance path at the module
boundary.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks._heading_coverage_tier_resolution import (
    DEFAULT_SCENARIO_TIERS,
    scenario_tier_violations,
)

__all__: list[str] = []


def test_default_scenario_tiers_surface() -> None:
    """`DEFAULT_SCENARIO_TIERS` is the documented allowlist-prefix default."""
    assert DEFAULT_SCENARIO_TIERS == (
        "tests.e2e",
        "tests.integration",
        "tests.consumer",
        "tests.prompts",
    )


def test_allowlisted_prefix_node_id_is_compliant(*, tmp_path: Path) -> None:
    """A scenarios.md entry whose node id sits under a default tier prefix passes."""
    entries: list[dict[str, object]] = [
        {"spec_file": "scenarios.md", "test": "tests.integration.test_flow.test_observable"}
    ]
    assert (
        scenario_tier_violations(repo_root=tmp_path, entries=entries, tiers=DEFAULT_SCENARIO_TIERS)
        == []
    )


def test_unit_tier_node_id_fires(*, tmp_path: Path) -> None:
    """A unit-tier node id (no allowlist prefix, no marker file) is a violation."""
    entries: list[dict[str, object]] = [
        {"spec_file": "scenarios.md", "test": "tests.unit.test_pure.test_thing"}
    ]
    violations = scenario_tier_violations(
        repo_root=tmp_path, entries=entries, tiers=DEFAULT_SCENARIO_TIERS
    )
    assert violations == entries


def test_todo_with_tier_acknowledging_reason_is_compliant(*, tmp_path: Path) -> None:
    """A TODO whose reason names the tier requirement passes direction 4."""
    entries: list[dict[str, object]] = [
        {"spec_file": "scenarios.md", "test": "TODO", "reason": "pending integration-tier test"}
    ]
    assert (
        scenario_tier_violations(repo_root=tmp_path, entries=entries, tiers=DEFAULT_SCENARIO_TIERS)
        == []
    )


def test_todo_without_tier_acknowledgment_fires(*, tmp_path: Path) -> None:
    """A TODO with a non-empty reason that omits tier wording is a violation."""
    entries: list[dict[str, object]] = [
        {"spec_file": "scenarios.md", "test": "TODO", "reason": "will write later"}
    ]
    violations = scenario_tier_violations(
        repo_root=tmp_path, entries=entries, tiers=DEFAULT_SCENARIO_TIERS
    )
    assert violations == entries


def test_non_scenarios_file_never_fires(*, tmp_path: Path) -> None:
    """Direction 4 governs `scenarios.md` only — a spec.md unit-tier entry passes."""
    entries: list[dict[str, object]] = [
        {"spec_file": "spec.md", "test": "tests.unit.test_pure.test_thing"}
    ]
    assert (
        scenario_tier_violations(repo_root=tmp_path, entries=entries, tiers=DEFAULT_SCENARIO_TIERS)
        == []
    )


def test_integration_marker_resolved_via_ast_is_compliant(*, tmp_path: Path) -> None:
    """A non-prefix node id whose resolved test carries pytest.mark.integration passes."""
    test_file = tmp_path / "tests" / "custom" / "test_flow.py"
    test_file.parent.mkdir(parents=True)
    _ = test_file.write_text(
        "import pytest\n\n\n@pytest.mark.integration\ndef test_observable() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    entries: list[dict[str, object]] = [
        {"spec_file": "scenarios.md", "test": "tests.custom.test_flow.test_observable"}
    ]
    assert (
        scenario_tier_violations(repo_root=tmp_path, entries=entries, tiers=DEFAULT_SCENARIO_TIERS)
        == []
    )


def test_non_string_test_field_is_skipped(*, tmp_path: Path) -> None:
    """A malformed entry whose `test` is not a string is skipped, not a violation."""
    entries: list[dict[str, object]] = [{"spec_file": "scenarios.md", "test": 123}]
    assert (
        scenario_tier_violations(repo_root=tmp_path, entries=entries, tiers=DEFAULT_SCENARIO_TIERS)
        == []
    )
