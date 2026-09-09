"""The `SPECIFICATION/spec.md` §"Definition of Done" gates, read off the merge gate itself.

The DoD is the list of conditions a livespec-dev-tooling change MUST satisfy
BEFORE MERGE. Three of its bullets are decidable from the tree, and each one
is a promise about the aggregate the merge gate actually runs rather than
about any single module:

- "Tests for any new check are paired with the implementation per the
  standard 1:1 mirror discipline at `tests/livespec_dev_tooling/checks/
  test_<slug>.py`" — asserted over every SHIPPED check, so a check module
  added without its paired test fails here.
- "`just check` is green: ruff lint and format, pyright strict [...],
  pytest with 100% line + branch coverage" — asserted as the presence of
  those four tool-backed gates in the aggregate's own target list. A DoD
  bullet naming a gate that the aggregate does not run is a DoD nobody
  enforces.
- "plus every structural check this library applies to itself" — asserted
  as canonical-slug containment: every `checks/<slug>.py` the package ships
  is a target of the aggregate, so self-application is total rather than
  sampled.

The remaining two bullets (the propose-change / revise loop, and the doctor
static + LLM phases) are workflow steps outside this repository's test
process, and the contracts.md heading co-edit is carried by the
`heading_coverage` registry the same spec file's other rows cover.

The aggregate is read as TEXT from the `justfile` rather than by invoking
`just check` (which would run the whole suite from inside itself): the
target list IS the wiring under assertion, and reading it keeps this a unit
of the recipe rather than a second execution of it.
"""

from __future__ import annotations

import re
from pathlib import Path

from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_CHECKS_TESTS_DIR = _REPO_ROOT / "tests" / "livespec_dev_tooling" / "checks"

# The `check:` recipe's `targets=( ... )` array — the exact list the merge
# gate hands `scripts/just/check.sh`.
_AGGREGATE_BLOCK = re.compile(r"\ncheck:\n.*?targets=\(\n(?P<targets>.*?)\n    \)\n", re.DOTALL)
_TARGET_LINE = re.compile(r"^\s+(check-[a-z0-9-]+)$", re.MULTILINE)

# The tool-backed gates the DoD names by tool: ruff lint, ruff format,
# pyright strict, and the 100%-coverage pytest run.
_DOD_TOOL_GATES = ("check-lint", "check-format", "check-types", "check-coverage")


def _aggregate_targets() -> set[str]:
    """Every `check-*` target the `just check` aggregate runs."""
    matched = _AGGREGATE_BLOCK.search(_JUSTFILE.read_text(encoding="utf-8"))
    assert matched is not None, "the `just check` aggregate must declare a `targets=( ... )` array"
    return set(_TARGET_LINE.findall(matched.group("targets")))


def _canonical_slugs() -> tuple[str, ...]:
    """The shipped canonical check slugs."""
    resolved = canonical_check_slugs()
    assert isinstance(
        resolved, IOSuccess
    ), f"the shipped checks package must be readable; got {resolved}"
    return unsafe_perform_io(resolved.unwrap())


def test_every_mechanically_decidable_definition_of_done_gate_is_wired() -> None:
    """The DoD's tree-decidable bullets hold against the aggregate the merge gate runs."""
    targets = _aggregate_targets()
    slugs = _canonical_slugs()
    assert slugs, "the library must ship at least one canonical check"

    unwired = sorted(slug for slug in slugs if slug not in targets)
    assert not unwired, (
        f'"every structural check this library applies to itself" must be a target of '
        f"`just check`; unwired={unwired}"
    )

    missing_tool_gates = sorted(gate for gate in _DOD_TOOL_GATES if gate not in targets)
    assert not missing_tool_gates, (
        f"the DoD names ruff lint + format, pyright strict and the 100%-coverage pytest "
        f"run as merge conditions, so each must be a target; missing={missing_tool_gates}"
    )

    paired = {
        slug: (_CHECKS_TESTS_DIR / f"test_{slug.removeprefix('check-').replace('-', '_')}.py")
        for slug in slugs
    }
    unpaired = sorted(slug for slug, test_path in paired.items() if not test_path.is_file())
    assert not unpaired, (
        f"the DoD's 1:1 mirror discipline requires tests/livespec_dev_tooling/checks/"
        f"test_<slug>.py for every shipped check; unpaired={unpaired}"
    )
