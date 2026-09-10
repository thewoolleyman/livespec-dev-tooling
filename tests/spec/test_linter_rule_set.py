"""§"Linter rule set" — the categories the section enumerates, read FROM the section.

The section is a CONFIGURATION CONTRACT: it names the ruff categories that
must be selected, the one rule that may be ignored, the four pylint
thresholds, the relative-import ban, and the six banned APIs. Every one of
those is a line in `pyproject.toml`, and every one of them can be deleted
without any other signal changing — an unselected category simply stops
producing findings, and a lint run with a category missing is
indistinguishable from a lint run with nothing to report.

The expected set is READ FROM THE SPEC rather than restated here, the same
way `tests.consumer.test_exit_code_table` reads the exit-code table: a test
carrying its own copy of the list is a second source of truth, and it passes
happily while the spec it claims to enforce says something else. Reading the
spec also puts the section's own arithmetic under test — the "(11 categories)"
and "(16 categories)" counts are checked against the lists they label.

**The selection direction is a SUPERSET, deliberately.** The section says the
27 categories "are wired"; it does not forbid wiring more, and `pyproject.toml`
wires a 28th (`BLE`) with its reason recorded at the array: it polices catch
BREADTH at the construct level, the half that makes the sanctioned
`# noqa: BLE001` boundary markers live directives rather than RUF100-flagged
dead ones. Asserting equality would convict that deliberate addition, so the
assertion is containment — every enumerated category is selected — plus
exactness everywhere the section IS exact ("`ISC001` is the only ignored
rule", the thresholds that "match livespec exactly", the banned-API list).
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_SPEC = _REPO_ROOT / "SPECIFICATION" / "non-functional-requirements.md"

# The spec's two enumerating bullets: "- v011 baseline (11 categories): `E`, ...".
_CATEGORY_BULLET = re.compile(
    r"^- v\d+ [a-z]+ \((?P<count>\d+) categories\): (?P<body>.*)$",
    re.MULTILINE,
)
_BACKTICKED = re.compile(r"`([^`]+)`")

# The section's exact clauses, quoted so a spec reword surfaces here.
_SOLE_IGNORED_RULE = "ISC001"
_THRESHOLD_CLAUSE = re.compile(
    r"`max-args = (?P<args>\d+)`, `max-positional-args = (?P<positional>\d+)`, "
    r"`max-branches = (?P<branches>\d+)`, `max-statements = (?P<statements>\d+)`"
)
_RELATIVE_IMPORT_CLAUSE = re.compile(
    r'`flake8-tidy-imports\.ban-relative-imports = "(?P<mode>\w+)"`'
)
_BANNED_API_SENTENCE = re.compile(
    r"(?P<names>(?:`[\w.]+`(?:,? and |, )?)+) are banned via `flake8-tidy-imports\.banned-api`"
)

_TOML_HEADER = re.compile(r"^\[(?P<name>[^\]]+)\]$")
_ARRAY = re.compile(r"^(?P<key>[a-z_-]+) = \[\n(?P<body>.*?)^\]$", re.MULTILINE | re.DOTALL)
_QUOTED = re.compile(r'"([^"]+)"')
_INT_ASSIGNMENT = re.compile(r"^(?P<key>[a-z-]+) = (?P<value>\d+)$", re.MULTILINE)
_STR_ASSIGNMENT = re.compile(r'^(?P<key>[a-z-]+) = "(?P<value>[^"]+)"$', re.MULTILINE)
_BANNED_KEY = re.compile(r'^"(?P<name>[^"]+)" = \{', re.MULTILINE)


def _toml_sections() -> dict[str, str]:
    """Each `[section]` of `pyproject.toml` mapped to its raw body text.

    Text rather than a parse: stdlib `tomllib` lands in 3.11 and this
    repository's floor is 3.10, the convention `tests.consumer
    .test_two_consumption_surfaces` already follows.
    """
    bodies: dict[str, list[str]] = {}
    current = ""
    for line in _PYPROJECT.read_text(encoding="utf-8").splitlines():
        header = _TOML_HEADER.match(line)
        current = header.group("name") if header else current
        bodies.setdefault(current, []).append(line)
    return {name: "\n".join(lines) for name, lines in bodies.items()}


def _array_values(*, section: str, key: str) -> list[str]:
    """The quoted elements of one array-valued key in one section."""
    body = _toml_sections()[section]
    matched = [match for match in _ARRAY.finditer(body) if match.group("key") == key]
    assert len(matched) == 1, f"`[{section}]` must declare exactly one `{key}` array"
    return _QUOTED.findall(matched[0].group("body"))


def _spec_categories() -> dict[str, list[str]]:
    """Each enumerating bullet's declared count mapped to its category list."""
    return {
        matched.group("count"): _BACKTICKED.findall(matched.group("body"))
        for matched in _CATEGORY_BULLET.finditer(_SPEC.read_text(encoding="utf-8"))
    }


def test_the_spec_enumerates_the_category_counts_it_claims() -> None:
    """The section's own arithmetic holds — a count is a claim like any other."""
    enumerated = _spec_categories()
    assert len(enumerated) == 2, (
        f'§"Linter rule set" enumerates its categories in two labelled bullets (the v011 '
        f"baseline and the v012 additions); found {len(enumerated)}"
    )
    miscounted = sorted(
        f"{declared} claimed, {len(categories)} listed"
        for declared, categories in enumerated.items()
        if int(declared) != len(categories)
    )
    assert not miscounted, (
        f"each bullet's parenthesised count must match the list it labels, or the "
        f"section's headline total describes a set it does not enumerate; "
        f"miscounted={miscounted}"
    )


def test_every_category_the_section_enumerates_is_selected() -> None:
    """No enumerated ruff category is missing from the lint selection."""
    expected = sorted(
        category for categories in _spec_categories().values() for category in categories
    )
    assert expected, "the section must enumerate at least one category"

    selected = set(_array_values(section="tool.ruff.lint", key="select"))
    unwired = sorted(category for category in expected if category not in selected)
    assert not unwired, (
        f"an enumerated category that is not selected produces no findings, and a lint "
        f"run missing a whole category is indistinguishable from a clean one; "
        f"unwired={unwired} selected={sorted(selected)}"
    )

    ignored = _array_values(section="tool.ruff.lint", key="ignore")
    assert ignored == [_SOLE_IGNORED_RULE], (
        f"the section states that `{_SOLE_IGNORED_RULE}` is the ONLY ignored rule (it "
        f"conflicts with the formatter); every other suppression must be argued at its "
        f"site, not blanket-listed here; ignored={ignored}"
    )


def test_the_pylint_thresholds_and_import_bans_match_the_section_exactly() -> None:
    """The four thresholds, the relative-import ban and the six banned APIs."""
    spec_text = _SPEC.read_text(encoding="utf-8")
    thresholds = _THRESHOLD_CLAUSE.search(spec_text)
    assert thresholds is not None, (
        'the section must state the pylint sub-rule thresholds that "match livespec '
        'exactly"; without them there is nothing to hold the config to'
    )

    configured = {
        matched.group("key"): matched.group("value")
        for matched in _INT_ASSIGNMENT.finditer(_toml_sections()["tool.ruff.lint.pylint"])
    }
    expected_thresholds = {
        "max-args": thresholds.group("args"),
        "max-positional-args": thresholds.group("positional"),
        "max-branches": thresholds.group("branches"),
        "max-statements": thresholds.group("statements"),
    }
    assert configured == expected_thresholds, (
        f"the pylint thresholds must match the section exactly — a raised ceiling is a "
        f"silent relaxation, since the rule keeps firing, just later; "
        f"configured={configured} spec={expected_thresholds}"
    )

    relative = _RELATIVE_IMPORT_CLAUSE.search(spec_text)
    assert relative is not None, "the section must state the relative-import ban mode"
    tidy = {
        matched.group("key"): matched.group("value")
        for matched in _STR_ASSIGNMENT.finditer(
            _toml_sections()["tool.ruff.lint.flake8-tidy-imports"]
        )
    }
    assert tidy.get("ban-relative-imports") == relative.group("mode"), (
        f"relative imports must stay banned at the section's declared mode "
        f'({relative.group("mode")!r}); configured={tidy.get("ban-relative-imports")!r}'
    )

    sentence = _BANNED_API_SENTENCE.search(spec_text)
    assert sentence is not None, "the section must enumerate the banned APIs"
    expected_banned = sorted(_BACKTICKED.findall(sentence.group("names")))
    banned = sorted(
        _BANNED_KEY.findall(_toml_sections()["tool.ruff.lint.flake8-tidy-imports.banned-api"])
    )
    assert banned == expected_banned, (
        f"the banned-API list must match the section exactly: each entry is banned for a "
        f"reason documented in livespec (a `typing.Protocol` alternative, or an "
        f"arbitrary-code-execution surface on load), and a dropped entry re-opens it "
        f"silently; configured={banned} spec={expected_banned}"
    )
