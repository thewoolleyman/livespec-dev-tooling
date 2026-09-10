"""§"Testing approach" — the scenario-tier coverage rules, applied to this registry.

The section's H3 "Scenario-tier coverage" is where its testable content is
concentrated, and it makes three claims about `tests/heading-coverage.json`
that no shipped check makes for this repository:

- **Granularity.** "Every `## Scenario:` heading in `SPECIFICATION/
  scenarios.md` MUST have its own entry ... one entry per scenario". The
  shipped `heading_coverage` check diffs SETS of `(spec_root, spec_file,
  heading)` triples, so it convicts a MISSING scenario — but two rows for one
  scenario collapse into one member of the registry set and it sees nothing.
  Duplicate rows are how a heading ends up with two answers, one of which is
  stale.
- **Tier.** Each mapped test must sit "at the integration tier or above",
  compliant when its node-id prefix is in `[tool.livespec_dev_tooling]
  .scenario_tiers`. `heading_coverage` enforces that, and this file asserts
  the OTHER half — that each declared prefix names a test directory that
  actually exists. A typo'd prefix does not fail the tier check; it silently
  stops matching, and then every scenario row under it is judged by the AST
  marker fallback instead, which almost nothing here carries.
- **Resolvability.** A registered node id must name a test that exists. The
  shipped check deliberately does NOT resolve ids, and its docstring is
  emphatic about why: the direction that did was armed AHEAD OF ADOPTION,
  reddened three consumer repos at once, and was reverted
  (`livespec-dev-tooling-jel7`) with an instruction not to bring it back as a
  lever. That is a statement about arming a SHIPPED check on repositories
  that have not adopted it — not a reason for THIS repository, whose ids all
  resolve today, to leave its own registry unchecked. Adopting it here as a
  repo-local test is the "adoption first, then arming" order this repo's
  `CLAUDE.md` records, and it is what keeps an unresolvable id — a typo, a
  renamed test, a deleted module — from reading as coverage.

The TODO / debt-register bullets of the same section are enforced by the
shipped `heading_coverage_debt_register` check (registered separately against
`scenarios.md`), and the `reason` bullet by `heading_coverage`'s reason guard;
neither is restated here.
"""

from __future__ import annotations

import ast
import collections
import json
from pathlib import Path
from typing import cast

from livespec_dev_tooling.config import load_scenario_tiers

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY = _REPO_ROOT / "tests" / "heading-coverage.json"
_SCENARIOS = _REPO_ROOT / "SPECIFICATION" / "scenarios.md"

_SCENARIO_PREFIX = "## Scenario:"
_TODO = "TODO"


def _registry_rows() -> list[dict[str, str]]:
    """Every row of the heading-coverage registry."""
    parsed = cast("list[dict[str, str]]", json.loads(_REGISTRY.read_text(encoding="utf-8")))
    assert parsed, "the heading-coverage registry must not be empty"
    return parsed


def _scenario_headings() -> list[str]:
    """Every `## Scenario:` heading in the scenarios spec file."""
    return [
        line.rstrip()
        for line in _SCENARIOS.read_text(encoding="utf-8").splitlines()
        if line.startswith(_SCENARIO_PREFIX)
    ]


def _declared_scenario_tiers() -> tuple[str, ...]:
    """The integration-tier node-id prefixes this repository declares.

    Read through the shipped loader the check itself uses, so the test and
    the gate cannot disagree about what the repository declared.
    """
    return load_scenario_tiers(repo_root=_REPO_ROOT) or ()


def _resolves(*, node_id: str) -> bool:
    """True when `node_id` names a test function defined in a module on disk.

    Every dotted prefix of the id is tried as a module path; a prefix that
    is a file on disk contributes the names it defines. An id naming no
    module at all contributes nothing and resolves False, which is the
    verdict a typo'd or renamed test earns.
    """
    parts = node_id.split(".")
    modules = [
        _REPO_ROOT.joinpath(*parts[:index]).with_suffix(".py") for index in range(1, len(parts))
    ]
    defined = {
        node.name
        for module_path in modules
        if module_path.is_file()
        for node in ast.walk(ast.parse(module_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    return parts[-1] in defined


def test_each_scenario_heading_has_exactly_one_registry_row() -> None:
    """One row per scenario — the granularity the set-diffing check cannot see."""
    rows = _registry_rows()
    headings = _scenario_headings()
    assert headings, "the scenarios spec file must declare at least one scenario"

    counts = collections.Counter(
        row["heading"] for row in rows if row["spec_file"] == _SCENARIOS.name
    )
    duplicated = sorted(heading for heading, count in counts.items() if count > 1)
    assert not duplicated, (
        f"the section tracks scenarios GRANULARLY — one entry per scenario. `heading_"
        f"coverage` diffs registry triples as a SET, so a second row for one scenario is "
        f"invisible to it while giving the heading two answers, one of them stale; "
        f"duplicated={duplicated}"
    )

    uncovered = sorted(heading for heading in headings if heading not in counts)
    assert not uncovered, f"every scenario needs its own registry entry; uncovered={uncovered}"


def test_every_declared_integration_tier_prefix_names_a_real_test_directory() -> None:
    """A tier prefix that matches nothing silently demotes every row beneath it."""
    tiers = _declared_scenario_tiers()
    assert tiers, (
        "this repository must declare its integration-tier prefixes; with none declared "
        "`heading_coverage` falls back to the shipped default set, which names directory "
        "conventions this repository does not use"
    )

    absent = sorted(tier for tier in tiers if not _REPO_ROOT.joinpath(*tier.split(".")).is_dir())
    assert not absent, (
        f"each `scenario_tiers` prefix must name a directory that exists: a typo'd prefix "
        f"is not a failure, it simply stops matching, and every scenario row beneath it "
        f"then falls through to the AST marker fallback instead of its declared tier; "
        f"absent={absent}"
    )


def test_every_mapped_registry_test_resolves_to_a_test_that_exists() -> None:
    """A node id that names no test is not coverage, whatever tier it claims."""
    mapped = [row for row in _registry_rows() if row["test"] != _TODO]
    assert mapped, "the registry must map at least one heading to a real test"

    unresolvable = sorted(
        f"{row['spec_file']} {row['heading']} -> {row['test']}"
        for row in mapped
        if not _resolves(node_id=row["test"])
    )
    assert not unresolvable, (
        f"a registered node id must name a test function that exists on disk. The shipped "
        f"check deliberately does not resolve ids — that direction was armed ahead of "
        f"adoption and reverted — so this repository, having adopted resolvable ids, "
        f"asserts it locally: an id left behind by a rename reads as coverage while "
        f"exercising nothing; unresolvable={unresolvable}"
    )
