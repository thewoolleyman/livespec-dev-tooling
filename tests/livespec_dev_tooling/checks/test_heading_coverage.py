"""Outside-in test for `dev-tooling/checks/heading_coverage.py` — every spec-tree-root NLSpec heading has a coverage entry.

Per `SPECIFICATION/constraints.md` section "Heading taxonomy" (post-v004),
the registry maps `(spec_root, spec_file, heading)` triples and the
check walks ONLY the five template-declared NLSpec files at each
spec-tree root (`spec.md`, `contracts.md`, `constraints.md`,
`non-functional-requirements.md`, `scenarios.md`) — never
recursing into `proposed_changes/`,
`history/`, `templates/<name>/history/`, or any other subdirectory;
never including the skill-owned `README.md` at the tree root.

Failure modes covered: uncovered heading, orphan registry entry,
missing `reason` on a TODO entry, and a `scenarios.md` heading mapped
to a unit-tier test (the integration-tier sub-rule). Skip rule
covered: `Scenario:` prefix.

The scenario integration-tier sub-rule (per
`SPECIFICATION/constraints.md` section "Heading taxonomy"): a registry entry
whose `spec_file` is `scenarios.md` MUST map to a test at the
integration tier or above — satisfied by an allowlisted node-id
prefix (read from `[tool.livespec_dev_tooling].scenario_tiers`, or a
documented default), by a static `pytest.mark.integration`/stronger
marker, or (for a TODO) by a `reason` that acknowledges the tier
requirement. Otherwise the distinct diagnostic `scenario heading
mapped to unit-tier test` fires.

Since `livespec-dev-tooling-8o8e.9` the direction has a THIRD outcome:
UNRESOLVED, when the mapped test file exists and cannot be read or does
not parse. An ABSENT file stays the ordinary violation — there is no
test, so there is no marker — and the two sit side by side here as
`test_scenario_tier_node_id_missing_file_fires` and
`test_scenario_tier_unparseable_test_file_is_unresolved`, which
asserted the SAME diagnostic until the resolver went on the railway.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_HEADING_COVERAGE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "heading_coverage.py"


def _run_check(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_HEADING_COVERAGE)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write_registry(*, tmp_path: Path, entries: list[dict[str, object]]) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "heading-coverage.json").write_text(
        json.dumps(entries) if entries else "[]",
        encoding="utf-8",
    )


def _write_spec_file(*, tmp_path: Path, rel_path: str, body: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body, encoding="utf-8")


def _write_file(*, tmp_path: Path, rel_path: str, body: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body, encoding="utf-8")


def _scenarios_body() -> str:
    """A `scenarios.md` whose single non-`Scenario:` heading needs coverage."""
    return "# Scenarios\n\n## Observable outcomes\n\nbody\n"


def test_heading_coverage_rejects_uncovered_heading(*, tmp_path: Path) -> None:
    """A spec heading without a matching registry entry fails."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n\nbody\n"
    )
    _write_registry(tmp_path=tmp_path, entries=[])
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "spec heading missing coverage entry" in combined
    assert "Foo" in combined


def test_heading_coverage_accepts_covered_heading(*, tmp_path: Path) -> None:
    """A spec heading with a matching (spec_root, spec_file, heading) triple passes."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n\nbody\n"
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/foo.py::test_foo",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_rejects_orphan_registry_entry(*, tmp_path: Path) -> None:
    """A registry entry whose triple does not match any spec heading fails."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n\nbody\n"
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/foo.py::test_foo",
            },
            {
                "heading": "## OldName",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/old.py::test_old",
            },
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "registry entry orphaned" in combined
    assert "OldName" in combined


def test_heading_coverage_rejects_todo_without_reason(*, tmp_path: Path) -> None:
    """A `test: TODO` entry without a non-empty `reason` field fails."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n\nbody\n"
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "TODO",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "TODO registry entry missing reason" in combined


def test_heading_coverage_accepts_todo_with_reason(*, tmp_path: Path) -> None:
    """A `test: TODO` entry WITH a non-empty `reason` field passes."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n\nbody\n"
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "TODO",
                "reason": "test pending",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_skips_scenario_prefix(*, tmp_path: Path) -> None:
    """Headings beginning with `Scenario:` are skipped — no entry needed."""
    body = "# Title\n\n## Foo\n\n## Scenario: happy path\n"
    _write_spec_file(tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body=body)
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/foo.py::test_foo",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_does_not_recurse_into_proposed_changes(*, tmp_path: Path) -> None:
    """A `## Proposal:` heading under proposed_changes/ does NOT require a registry entry."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n"
    )
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/proposed_changes/whatever.md",
        body="## Proposal: should be ignored\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/foo.py::test_foo",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_does_not_recurse_into_history(*, tmp_path: Path) -> None:
    """Headings under `history/v*/` are NOT counted by the check."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n"
    )
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/history/v001/spec.md",
        body="# Title\n\n## Snapshot heading\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/foo.py::test_foo",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_does_not_count_readme(*, tmp_path: Path) -> None:
    """The skill-owned `README.md` at the tree root is not walked."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n"
    )
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/README.md",
        body="# Orientation\n\n## Some Section\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/foo.py::test_foo",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_skips_non_directory_under_templates(*, tmp_path: Path) -> None:
    """A non-directory entry under `templates/` is ignored (e.g., a stray file)."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n"
    )
    # Stray file under templates/ — must be skipped, not treated as sub-spec root.
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/templates/stray.txt",
        body="not a sub-spec directory\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/foo.py::test_foo",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_walks_sub_spec_trees(*, tmp_path: Path) -> None:
    """Sub-spec roots under `SPECIFICATION/templates/<name>/` are walked too."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Main\n"
    )
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/templates/livespec/spec.md",
        body="# Title\n\n## Sub-spec heading\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Main",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/main.py::test_main",
            },
            {
                "heading": "## Sub-spec heading",
                "spec_root": "SPECIFICATION/templates/livespec",
                "spec_file": "spec.md",
                "test": "tests/sub.py::test_sub",
            },
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_disambiguates_same_heading_across_files(*, tmp_path: Path) -> None:
    """Two files with the same heading text need TWO registry entries (different spec_file)."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Summary\n"
    )
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/contracts.md", body="# Title\n\n## Summary\n"
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Summary",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/spec.py::test_summary",
            },
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "spec heading missing coverage entry" in combined
    assert "contracts.md" in combined


def test_heading_coverage_tolerates_malformed_registry_entries(*, tmp_path: Path) -> None:
    """Entries with non-string fields are skipped silently."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n"
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "heading-coverage.json").write_text(
        json.dumps(
            [
                {
                    "heading": "## Foo",
                    "spec_root": "SPECIFICATION",
                    "spec_file": "spec.md",
                    "test": "tests/foo.py::test_foo",
                },
                {"heading": 42, "spec_root": "SPECIFICATION", "spec_file": "spec.md", "test": "x"},
            ]
        ),
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_tolerates_object_top_level_registry(*, tmp_path: Path) -> None:
    """Non-list top-level coverage JSON is treated as no entries."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "heading-coverage.json").write_text("{}", encoding="utf-8")
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_accepts_pre_phase_6_empty(*, tmp_path: Path) -> None:
    """An empty `[]` registry with NO spec tree passes (exit 0)."""
    _write_registry(tmp_path=tmp_path, entries=[])
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_accepts_no_coverage_file(*, tmp_path: Path) -> None:
    """Repo without `tests/heading-coverage.json` passes (exit 0)."""
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_heading_coverage_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking `main()`."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "heading_coverage_for_import_test",
        str(_HEADING_COVERAGE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


# ---------------------------------------------------------------------------
# Direction 4 — scenarios.md headings require integration-tier-or-above tests.
# ---------------------------------------------------------------------------


def test_scenario_tier_compliant_via_default_prefix(*, tmp_path: Path) -> None:
    """A scenarios.md entry with a default-allowlist prefix node id passes (no pyproject)."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.e2e.test_happy_path.test_happy_path_minimal",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_compliant_via_marker_ast(*, tmp_path: Path) -> None:
    """A non-allowlisted node id passes when the test fn carries an integration marker."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    # Node id under a NON-allowlisted directory (`tests.behavior.*`), so path
    # (a) cannot save it — only the static `pytest.mark.integration` marker can.
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/behavior/test_observable.py",
        body=(
            "import pytest\n\n\n"
            "@pytest.mark.integration\n"
            "def test_observable_flow() -> None:\n"
            "    assert True\n"
        ),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_observable.test_observable_flow",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_unit_tier_node_id_fires(*, tmp_path: Path) -> None:
    """A scenarios.md entry mapped to a unit-tier node id fires the new diagnostic."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    # `tests.unit.*` is neither allowlisted nor markered → unit-tier violation.
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/unit/test_pure.py",
        body="def test_pure_thing() -> None:\n    assert True\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.unit.test_pure.test_pure_thing",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" in combined
    assert "Observable outcomes" in combined


def test_scenario_tier_unit_tier_does_not_fire_for_non_scenarios_file(*, tmp_path: Path) -> None:
    """A unit-tier node id under spec.md (not scenarios.md) does NOT fire direction 4."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/spec.md", body="# Title\n\n## Foo\n\nbody\n"
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests.unit.test_pure.test_pure_thing",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_todo_with_tier_acknowledging_reason_passes(*, tmp_path: Path) -> None:
    """A scenarios.md TODO whose reason acknowledges the tier requirement passes."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "TODO",
                "reason": "integration-tier harness pending; will map to tests.e2e once ready",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_todo_without_tier_acknowledgment_fires(*, tmp_path: Path) -> None:
    """A scenarios.md TODO with a non-empty but tier-silent reason fires direction 4."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "TODO",
                "reason": "test pending",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" in combined


def test_scenario_tier_allowlist_read_from_pyproject(*, tmp_path: Path) -> None:
    """A consumer-declared `scenario_tiers` prefix is honored from pyproject.toml."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    # `tests.acceptance.*` is NOT in the documented default; declaring it in
    # pyproject makes the otherwise-unit-tier node id compliant.
    _write_file(
        tmp_path=tmp_path,
        rel_path="pyproject.toml",
        body=("[tool.livespec_dev_tooling]\n" 'scenario_tiers = ["tests.acceptance"]\n'),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.acceptance.test_flow.test_acceptance",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_pyproject_allowlist_excludes_default_prefix(*, tmp_path: Path) -> None:
    """A declared allowlist REPLACES the default — a default-only prefix then fires."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    # Allowlist declares only `tests.acceptance`; the node id under the
    # default-but-not-declared `tests.e2e` is no longer covered by path (a).
    _write_file(
        tmp_path=tmp_path,
        rel_path="pyproject.toml",
        body=("[tool.livespec_dev_tooling]\n" 'scenario_tiers = ["tests.acceptance"]\n'),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.e2e.test_happy_path.test_happy_path_minimal",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" in combined


def test_scenario_tier_default_used_when_table_absent(*, tmp_path: Path) -> None:
    """With a pyproject that has no livespec_dev_tooling table, the default allowlist applies."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_file(
        tmp_path=tmp_path,
        rel_path="pyproject.toml",
        body='[project]\nname = "x"\nversion = "0"\n',
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.integration.test_x.test_y",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_unresolvable_node_id_governed_by_prefix(*, tmp_path: Path) -> None:
    """An allowlisted prefix passes even when the node-id file does not exist (no crash)."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    # No file at tests/e2e/test_missing.py — marker path (b) finds nothing, but
    # the allowlisted `tests.e2e` prefix (path a) governs and the check passes.
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.e2e.test_missing.test_absent",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_compliant_via_module_pytestmark(*, tmp_path: Path) -> None:
    """A module-level `pytestmark` integration marker satisfies path (b)."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/behavior/test_mod.py",
        body=(
            "import pytest\n\n"
            "pytestmark = pytest.mark.integration\n\n\n"
            "def test_mod_flow() -> None:\n"
            "    assert True\n"
        ),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_mod.test_mod_flow",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_compliant_via_class_marker(*, tmp_path: Path) -> None:
    """A class-level integration marker on the enclosing class satisfies path (b)."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/behavior/test_cls.py",
        body=(
            "import pytest\n\n\n"
            "@pytest.mark.integration\n"
            "class TestObservable:\n"
            "    def test_method(self) -> None:\n"
            "        assert True\n"
        ),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_cls.test_method",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_node_id_without_dot_fires(*, tmp_path: Path) -> None:
    """A single-token (no-dot) node id cannot resolve to a file → unit-tier fires."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "weirdsingletoken",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" in combined


def test_scenario_tier_node_id_missing_file_fires(*, tmp_path: Path) -> None:
    """A non-allowlisted node id whose file does NOT exist → unit-tier fires (no crash).

    The ANSWER half of the pair `livespec-dev-tooling-8o8e.9` split: there is no
    test, so there is no marker, and the tier verdict is one the read produced.
    Contrast `test_scenario_tier_unparseable_test_file_is_unresolved` below,
    which asserted this SAME diagnostic until the resolver went on the railway.
    """
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_absent.test_gone",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" in combined


def test_scenario_tier_unparseable_test_file_is_unresolved(*, tmp_path: Path) -> None:
    """A node-id file with invalid Python is UNRESOLVED, never a unit-tier verdict.

    ⛔ THIS TEST PINNED THE COLLAPSE. Until `livespec-dev-tooling-8o8e.9` it
    asserted `scenario heading mapped to unit-tier test` and its own docstring
    said why — "parse error swallowed → unit-tier fires" — so the fused
    behavior was not merely implicit, it was LOCKED IN by a passing test that
    read as correct. A test can pin a defect as firmly as it pins a contract.

    The exit code is unchanged (non-zero); what changed is what the author is
    told. Both directions are asserted, because "the new diagnostic appears" is
    only half the claim — the tier verdict must be GONE.
    """
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    # Syntactically invalid module: the AST scan must NOT crash, and must not
    # answer either — it cannot tell whether the file carries a tier marker.
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/behavior/test_broken.py",
        body="def test_broken(:\n    this is not valid python\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_broken.test_broken",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert (
        "heading-coverage-scenario-tier-unresolved" in combined
    ), f"an unparseable mapped test must be reported as unresolved; got {combined!r}"
    assert (
        "test-file-unparseable" in combined
    ), f"the diagnostic must name WHICH read failed; got {combined!r}"
    assert (
        "scenario heading mapped to unit-tier test" not in combined
    ), f"a non-read must not be reported as a tier verdict; got {combined!r}"


def test_scenario_tier_compliant_via_annotated_module_pytestmark(*, tmp_path: Path) -> None:
    """An ANNOTATED module-level `pytestmark: ... = pytest.mark.integration` satisfies (b)."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/behavior/test_ann.py",
        body=(
            "import pytest\n\n"
            "pytestmark: pytest.MarkDecorator = pytest.mark.integration\n\n\n"
            "def test_ann_flow() -> None:\n"
            "    assert True\n"
        ),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_ann.test_ann_flow",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_pytestmark_list_with_unrelated_assigns(*, tmp_path: Path) -> None:
    """A `pytestmark = [...]` list amid unrelated top-level assigns is honored."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    # An annotated assignment with NO value (`X: int`), an unrelated assignment,
    # and the real `pytestmark` as a LIST — exercises the None-value skip, the
    # non-pytestmark-target skip, and the list-unpacking marker path.
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/behavior/test_list.py",
        body=(
            "import pytest\n\n"
            "UNRELATED: int\n"
            "OTHER = 1\n"
            "pytestmark = [pytest.mark.integration]\n\n\n"
            "def test_list_flow() -> None:\n"
            "    assert True\n"
        ),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_list.test_list_flow",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_tier_class_without_target_function_fires(*, tmp_path: Path) -> None:
    """An unmarked class lacking the target fn, plus a bare decorator, → unit-tier fires."""
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    # A class WITHOUT an integration marker and WITHOUT the target function, and
    # a module-level target function carrying only a non-`mark` bare decorator
    # (`@staticmethod`-style name) — neither path (b) source yields the marker.
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/behavior/test_nomatch.py",
        body=(
            "def deco(fn):\n"
            "    return fn\n\n\n"
            "class TestOther:\n"
            "    def test_unrelated(self) -> None:\n"
            "        assert True\n\n\n"
            "@deco\n"
            "def test_target_flow() -> None:\n"
            "    assert True\n"
        ),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_nomatch.test_target_flow",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" in combined


def test_scenario_tier_unmarked_method_in_unmarked_class_fires(*, tmp_path: Path) -> None:
    """The target method exists in an UNMARKED class with NO marker → unit-tier fires.

    Exercises the class-walk continuing past a found-but-unmarked method (the
    `if class_carries or func_markers` guard evaluating False), then falling
    through to the unit-tier diagnostic.
    """
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/behavior/test_plainmethod.py",
        body=(
            "class TestPlain:\n"
            "    def test_plain_method(self) -> None:\n"
            "        assert True\n"
        ),
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Observable outcomes",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.behavior.test_plainmethod.test_plain_method",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" in combined


def test_scenario_tier_non_string_test_is_skipped(*, tmp_path: Path) -> None:
    """A scenarios.md entry whose `test` is non-string short-circuits direction 4.

    The (spec_root, spec_file, heading) triple is still valid (all strings), so
    the heading is covered (no direction-1 fire) and the non-string `test` guard
    means direction 4 does not fire either — the check passes (exit 0).
    """
    _write_spec_file(
        tmp_path=tmp_path, rel_path="SPECIFICATION/scenarios.md", body=_scenarios_body()
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "heading-coverage.json").write_text(
        json.dumps(
            [
                {
                    "heading": "## Observable outcomes",
                    "spec_root": "SPECIFICATION",
                    "spec_file": "scenarios.md",
                    "test": 42,
                }
            ]
        ),
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" not in combined


# ---------------------------------------------------------------------------
# Granular scenario registration — a `## Scenario:` heading in `scenarios.md`
# now REQUIRES its own registry entry (the skip applies ONLY in other files).
# ---------------------------------------------------------------------------


def test_scenario_heading_in_scenarios_md_requires_entry(*, tmp_path: Path) -> None:
    """A `## Scenario:` heading in `scenarios.md` with NO entry fires the uncovered diagnostic."""
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/scenarios.md",
        body="# Scenarios\n\n## Scenario: happy path\n\nbody\n",
    )
    _write_registry(tmp_path=tmp_path, entries=[])
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "spec heading missing coverage entry" in combined
    assert "Scenario: happy path" in combined


def test_scenario_heading_in_scenarios_md_accepts_todo_with_tier_reason(*, tmp_path: Path) -> None:
    """A `## Scenario:` heading in `scenarios.md` covered by a TODO+tier-reason entry passes."""
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/scenarios.md",
        body="# Scenarios\n\n## Scenario: happy path\n\nbody\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Scenario: happy path",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "TODO",
                "reason": "integration-tier consumer harness pending (epic li-scetdt / Wave 6)",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0


def test_scenario_heading_in_scenarios_md_unit_tier_fires(*, tmp_path: Path) -> None:
    """A `## Scenario:` heading mapped to a unit-tier real test fires the tier diagnostic."""
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/scenarios.md",
        body="# Scenarios\n\n## Scenario: happy path\n\nbody\n",
    )
    _write_file(
        tmp_path=tmp_path,
        rel_path="tests/unit/test_pure.py",
        body="def test_pure_thing() -> None:\n    assert True\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Scenario: happy path",
                "spec_root": "SPECIFICATION",
                "spec_file": "scenarios.md",
                "test": "tests.unit.test_pure.test_pure_thing",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "scenario heading mapped to unit-tier test" in combined
    assert "Scenario: happy path" in combined


def test_scenario_heading_in_non_scenarios_file_still_skipped(*, tmp_path: Path) -> None:
    """A `## Scenario:` heading in spec.md (not scenarios.md) needs NO entry — still skipped."""
    _write_spec_file(
        tmp_path=tmp_path,
        rel_path="SPECIFICATION/spec.md",
        body="# Title\n\n## Foo\n\n## Scenario: belongs to prose, not registry\n",
    )
    _write_registry(
        tmp_path=tmp_path,
        entries=[
            {
                "heading": "## Foo",
                "spec_root": "SPECIFICATION",
                "spec_file": "spec.md",
                "test": "tests/foo.py::test_foo",
            }
        ],
    )
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0
