"""§"Code coverage thresholds" — the floor, and the exclusion list read off the spec.

Two claims, and the second is the one with teeth.

**`fail_under = 100` line + branch.** A floor below 100, or `branch` turned
off, does not fail anything — the suite reports a smaller number and passes.
Branch coverage in particular is the half that catches an `if` whose other
arm nobody ever took, which is where the unexercised error paths live.

**The exclusion list is EXACT.** "`exclude_also` MUST be minimal and limited
to structurally-unreachable patterns matching livespec's exact list ... No
other exclusions are permitted without a propose-change cycle." An exclusion
is the one coverage knob that makes the 100% floor cheaper to satisfy WITHOUT
writing a test: every line matching an `exclude_also` pattern is removed from
both the numerator and the denominator, so adding a pattern raises the
reported percentage while lowering the tested fraction, and the gate reports
the same green 100% either way. That is why the section spells the list out
and requires a propose-change to change it, and why the assertion here is set
EQUALITY in both directions rather than containment: an extra pattern is
exactly the defect, and a missing one silently reddens work the spec
sanctions.

The expected patterns are READ FROM THE SPEC sentence that enumerates them —
the test carries no second copy of a list whose whole purpose is to be the
single copy.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_SPEC = _REPO_ROOT / "SPECIFICATION" / "non-functional-requirements.md"

# The enumerating sentence: "... matching livespec's exact list: `a`, `b`. No
# other exclusions are permitted ...". Bounded on both sides so the
# surrounding prose's other backticked spans stay out of the list.
_EXCLUSION_SENTENCE = re.compile(
    r"matching livespec's exact list: (?P<names>.*?)\. No other exclusions",
    re.DOTALL,
)
_BACKTICKED = re.compile(r"`([^`]+)`")
_FAIL_UNDER_CLAUSE = re.compile(r"`fail_under = (?P<floor>\d+)` line \+ branch")

_TOML_HEADER = re.compile(r"^\[(?P<name>[^\]]+)\]$")
_INT_ASSIGNMENT = re.compile(r"^(?P<key>[a-z_]+) = (?P<value>\d+)$", re.MULTILINE)
_BOOL_ASSIGNMENT = re.compile(r"^(?P<key>[a-z_]+) = (?P<value>true|false)$", re.MULTILINE)
_ARRAY = re.compile(r"^(?P<key>[a-z_]+) = \[\n(?P<body>.*?)^\]$", re.MULTILINE | re.DOTALL)
_QUOTED = re.compile(r'"([^"]+)"')

_RUN_SECTION = "tool.coverage.run"
_REPORT_SECTION = "tool.coverage.report"


def _toml_sections() -> dict[str, str]:
    """Each `[section]` of `pyproject.toml` mapped to its raw body text.

    Text rather than a parse: stdlib `tomllib` lands in 3.11 and this
    repository's floor is 3.10.
    """
    bodies: dict[str, list[str]] = {}
    current = ""
    for line in _PYPROJECT.read_text(encoding="utf-8").splitlines():
        header = _TOML_HEADER.match(line)
        current = header.group("name") if header else current
        bodies.setdefault(current, []).append(line)
    return {name: "\n".join(lines) for name, lines in bodies.items()}


def _spec_exclusions() -> list[str]:
    """The exclusion patterns the section enumerates."""
    sentence = _EXCLUSION_SENTENCE.search(_SPEC.read_text(encoding="utf-8"))
    assert sentence is not None, (
        "the section must enumerate the permitted `exclude_also` patterns; with no list "
        "in the spec there is no exact list to hold the config to"
    )
    return _BACKTICKED.findall(sentence.group("names"))


def test_the_coverage_floor_is_the_full_line_and_branch_gate() -> None:
    """100% line coverage, with branch measurement actually on."""
    spec_text = _SPEC.read_text(encoding="utf-8")
    clause = _FAIL_UNDER_CLAUSE.search(spec_text)
    assert clause is not None, "the section must state the `fail_under` floor it requires"

    report = {
        matched.group("key"): matched.group("value")
        for matched in _INT_ASSIGNMENT.finditer(_toml_sections()[_REPORT_SECTION])
    }
    assert report.get("fail_under") == clause.group("floor"), (
        f"the coverage floor must be the section's; a lowered floor fails nothing — the "
        f"suite simply reports a smaller number and passes; "
        f'configured={report.get("fail_under")!r} spec={clause.group("floor")!r}'
    )

    run = {
        matched.group("key"): matched.group("value")
        for matched in _BOOL_ASSIGNMENT.finditer(_toml_sections()[_RUN_SECTION])
    }
    assert run.get("branch") == "true", (
        f"the floor is line AND branch; with `branch` off the same 100% is reported "
        f"while every untaken `else` — where the unexercised error paths live — counts "
        f'as covered; configured={run.get("branch")!r}'
    )


def test_the_exclusion_list_is_exactly_the_one_the_section_enumerates() -> None:
    """No pattern the spec does not name, and none it does that is missing."""
    expected = _spec_exclusions()
    assert expected, "the section's exclusion list must not read back empty"

    body = _toml_sections()[_REPORT_SECTION]
    matched = [match for match in _ARRAY.finditer(body) if match.group("key") == "exclude_also"]
    assert len(matched) == 1, f"`[{_REPORT_SECTION}]` must declare exactly one `exclude_also`"
    configured = _QUOTED.findall(matched[0].group("body"))

    assert sorted(configured) == sorted(expected), (
        f"`exclude_also` must match the section's exact list. An exclusion removes its "
        f"lines from BOTH the numerator and the denominator, so an extra pattern raises "
        f"the reported percentage while lowering the tested fraction — the 100% gate "
        f"reports green either way, which is why the section requires a propose-change "
        f"cycle to add one; configured={configured} spec={expected}"
    )
