"""The `non-functional-requirements.md` §"Boundary" routing table, read off the spec tree.

The section is a ROUTING TABLE: five bullets, each naming a class of content
and the ONE file it must live in. A routing table is only worth its ink where
a misroute is otherwise silent, and here it is — nothing in the toolchain
objects to a section written into the wrong spec file. Two consequences make
the silence expensive rather than cosmetic:

- `heading_coverage` SKIPS `## Scenario:`-prefixed headings in every file
  EXCEPT `scenarios.md` (its own docstring says so). So an acceptance scenario
  parked in `spec.md` or in this file is not merely misfiled — it is exempt
  from the coverage registry entirely, and its absence from the registry is
  indistinguishable from a scenario that never existed.
- Every consumer of the spec tree — the revise flow, the heading-coverage
  co-edit, a reader asking "where is the CLI contract?" — resolves by FILE.
  A contract that moved out from under `contracts.md` is not found by the
  reader who looks where the boundary says to look.

So each bullet is asserted in the direction it constrains: the named content
is IN the file the bullet names, and (for this file, which is the one the
section governs from) the content the boundary routes AWAY is NOT here.

The last bullet's "everything else ... lives in THIS file" is asserted by
naming its six enumerated topics and requiring a heading for each.

**Duplication is permitted only as a CROSS-REFERENCE.** `## Self-application`
is an H2 in both `constraints.md` and this file, which the routing table
allows only because this file's copy CITES the other rather than restating
it ("The library MUST apply its own checks to itself per `constraints.md`
§"Self-application""). A duplicated heading whose body does NOT name the
file it duplicates is a second definition, and two definitions of one rule
drift. That is asserted generally, over whatever headings this file happens
to share with a sibling, so a future duplicate inherits the requirement
without an edit here.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_ROOT = _REPO_ROOT / "SPECIFICATION"

_THIS_FILE = "non-functional-requirements.md"
_SCENARIOS_FILE = "scenarios.md"
_SPEC_FILES = (
    "spec.md",
    "contracts.md",
    "constraints.md",
    _THIS_FILE,
    _SCENARIOS_FILE,
)

# Each boundary bullet, as (destination file, the headings that carry the
# content the bullet routes there). The headings are the spec's own, so a
# rename that moves content across the boundary convicts here.
_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("spec.md", ("## Project intent", "## Architecture")),
    (
        "contracts.md",
        (
            "## CLI surface",
            "## Composite Actions wire contract",
            "## Reusable workflows wire contract",
        ),
    ),
    (
        "constraints.md",
        ("## Runtime", "## No network I/O", "## Semver discipline", "## CLI shape"),
    ),
    (
        _THIS_FILE,
        (
            "## Test-Driven Development discipline",
            "## Linter rule set",
            "## Typechecker rule set",
            "## Code coverage thresholds",
            "## Hooks and CI",
            "## Commit and merge discipline",
        ),
    ),
)

_SCENARIO_PREFIX = "## Scenario:"


def _h2_headings(*, spec_file: str) -> list[str]:
    """Every `## ` heading in one spec file, in source order."""
    source = (_SPEC_ROOT / spec_file).read_text(encoding="utf-8")
    return [
        line.rstrip()
        for line in source.splitlines()
        if line.startswith("## ") and not line.startswith("### ")
    ]


def _headings_by_file() -> dict[str, list[str]]:
    """The H2 set of every template-declared spec file."""
    return {spec_file: _h2_headings(spec_file=spec_file) for spec_file in _SPEC_FILES}


def _section_body(*, spec_file: str, heading: str) -> str:
    """The text under `heading`, up to the next H2 or end of file."""
    source = (_SPEC_ROOT / spec_file).read_text(encoding="utf-8")
    after = source.split(f"\n{heading}\n", maxsplit=1)[-1]
    return re.split(r"\n## ", after, maxsplit=1)[0]


def test_every_boundary_route_lands_in_the_file_the_boundary_names() -> None:
    """Each routed class of content sits in its named file, and not in this one."""
    headings = _headings_by_file()

    misrouted = sorted(
        f"{heading} -> expected in {destination}"
        for destination, expected in _ROUTES
        for heading in expected
        if heading not in headings[destination]
    )
    assert not misrouted, (
        f'`non-functional-requirements.md` §"Boundary" routes each class of content to '
        f"ONE file, and nothing objects when a section is written into another — the "
        f"reader who looks where the boundary says to look simply does not find it; "
        f"misrouted={misrouted}"
    )

    routed_away = sorted(
        heading
        for destination, expected in _ROUTES
        if destination != _THIS_FILE
        for heading in expected
        if heading in headings[_THIS_FILE]
    )
    assert not routed_away, (
        f"the boundary routes user-facing intent, the wire contracts and the "
        f"consumer-observable constraints OUT of `{_THIS_FILE}`, so a copy of one here "
        f"is a second definition of a rule that already has one; here={routed_away}"
    )


def test_acceptance_scenarios_live_only_where_the_coverage_gate_reads_them() -> None:
    """`## Scenario:` headings are in `scenarios.md` alone, which holds nothing else."""
    headings = _headings_by_file()

    stray = sorted(
        f"{spec_file}: {heading}"
        for spec_file, file_headings in headings.items()
        if spec_file != _SCENARIOS_FILE
        for heading in file_headings
        if heading.startswith(_SCENARIO_PREFIX)
    )
    assert not stray, (
        f"the boundary keeps acceptance scenarios in `{_SCENARIOS_FILE}`, and `heading_"
        f"coverage` SKIPS `{_SCENARIO_PREFIX}` headings in every other file — so a "
        f"misfiled scenario is not merely misplaced, it is exempt from the coverage "
        f"registry and reads exactly like a scenario nobody ever wrote; stray={stray}"
    )

    non_scenarios = sorted(
        heading for heading in headings[_SCENARIOS_FILE] if not heading.startswith(_SCENARIO_PREFIX)
    )
    assert not non_scenarios, (
        f"`{_SCENARIOS_FILE}` carries acceptance scenarios and nothing else; a non-scenario "
        f"H2 there inherits the integration-tier coverage requirement that only a scenario "
        f"earns; found={non_scenarios}"
    )


def test_a_heading_this_file_shares_with_a_sibling_cross_references_it() -> None:
    """A duplicated H2 here cites the sibling that owns it, rather than restating it."""
    headings = _headings_by_file()
    shared = [
        (heading, spec_file)
        for heading in headings[_THIS_FILE]
        for spec_file in _SPEC_FILES
        if spec_file != _THIS_FILE and heading in headings[spec_file]
    ]
    assert shared, (
        "this assertion is only meaningful while at least one heading is shared — if the "
        "spec tree ever has none, delete it rather than letting it pass vacuously"
    )

    uncited = sorted(
        f"{heading} (also in {spec_file})"
        for heading, spec_file in shared
        if spec_file not in _section_body(spec_file=_THIS_FILE, heading=heading)
    )
    assert not uncited, (
        f"a heading this file shares with a sibling is legitimate ONLY as a "
        f"cross-reference: its body must name the file that owns the rule, or the spec "
        f"tree carries two definitions of one rule and they drift apart silently; "
        f"uncited={uncited}"
    )
