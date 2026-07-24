"""_tool_backed_surfaces — justfile + CI-matrix parsers for `tool_backed_check_completeness`.

Extracted from `tool_backed_check_completeness.py` so the parent check's LLOC
stays under the 250-line hard ceiling — the same LLOC-reduction split as
`_ci_matrix_parse` and `_red_green_replay_modes`. The leading underscore marks
this a private sibling module: entry-point check scripts under
`livespec_dev_tooling/checks/` carry no underscore prefix, so this file is
neither a canonical slug (`canonical_check_slugs` skips `_`-prefixed modules)
nor a mirror-paired module (`tests_mirror_pairing` exempts `_`-prefixed files;
its behavior is covered through the parent's subprocess tests, exactly as
`_ci_matrix_parse` is covered through `test_ci_matrix_completeness`).

The parsers are regex-based per the package's BOUNDED parser-duplication
convention (canonical statement in `_ci_matrix_parse.py`'s docstring, which
names this module's `_parse_ci_matrix_targets` as a PERMITTED mechanical
duplicate) and are PURE — no logging — so the parent `main()` owns every
diagnostic. The `justfile`
`check:` recipe / `targets=(...)` anchors mirror `aggregate_completeness`; the
`matrix.target` anchors mirror `branch_protection_alignment`. "Literal"
membership on BOTH surfaces is the invariant the parent enforces
(epic li-pyright-gate): a slug must appear as a literal token in the targets
array AND in at least one CI matrix.
"""

from __future__ import annotations

import re
from pathlib import Path

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `tool_backed_check_completeness.py`, so pyright's per-file analysis
# does not flag them unused across the package boundary.
__all__: list[str] = [
    "collect_ci_matrix_targets",
    "extract_check_recipe_body",
    "extract_targets_array_tokens",
]


# justfile `check:` recipe + `targets=(...)` array anchors (mirrors
# aggregate_completeness's parser so the two checks agree on what
# "literal targets-array membership" means).
_CHECK_RECIPE_HEADER = re.compile(r"^check:\s*$", re.MULTILINE)
_TARGETS_ARRAY_START = re.compile(r"^\s*targets=\(\s*$", re.MULTILINE)
_TARGETS_ARRAY_END = re.compile(r"^\s*\)\s*$")

# CI matrix anchors (mirrors branch_protection_alignment's parser).
_MATRIX_HEADER = re.compile(r"^\s*matrix:\s*$")
_MATRIX_TARGET_KEY = re.compile(r"^\s*target:\s*$")
_MATRIX_TARGET_LINE = re.compile(r"^\s*-\s*([\w-]+)\s*$")


def extract_check_recipe_body(*, justfile_text: str) -> str | None:
    """Return the text body of the `check:` recipe, or None when absent.

    A just recipe body extends from the recipe header to the next
    recipe header (a non-indented line ending in `:`) or to EOF.
    """
    header_match = _CHECK_RECIPE_HEADER.search(justfile_text)
    if header_match is None:
        return None
    body_start = header_match.end()
    lines = justfile_text[body_start:].splitlines()
    body_lines: list[str] = []
    for raw in lines:
        if raw and not raw.startswith((" ", "\t")) and ":" in raw:
            break
        body_lines.append(raw)
    return "\n".join(body_lines)


def extract_targets_array_tokens(*, recipe_body: str) -> list[str] | None:
    """Return the `check-*` slugs inside `targets=(...)`, or None when absent.

    Blank lines, full-line comments, inline trailing comments, and any
    token that does not start with `check-` are dropped — matching
    aggregate_completeness's filtering so the two checks agree on what
    counts as a literal targets-array slug.
    """
    start_match = _TARGETS_ARRAY_START.search(recipe_body)
    if start_match is None:
        return None
    after_start = recipe_body[start_match.end() :]
    collected: list[str] = []
    closed = False
    for raw in after_start.splitlines():
        if _TARGETS_ARRAY_END.match(raw):
            closed = True
            break
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split("#", 1)[0].strip()
        if token.startswith("check-"):
            collected.append(token)
    if not closed:
        return None
    return collected


def _parse_ci_matrix_targets(*, source: str) -> set[str]:
    """Extract every `matrix.target` job slug from one workflow file's text.

    Walks the file line-by-line: enters the `matrix:` table, then the
    `target:` key, then collects `- check-foo` bullet entries until a
    non-bullet line ends the list.
    """
    targets: set[str] = set()
    in_matrix = False
    in_target_list = False
    for raw in source.splitlines():
        if _MATRIX_HEADER.match(raw):
            in_matrix = True
            in_target_list = False
            continue
        if not in_matrix:
            continue
        if _MATRIX_TARGET_KEY.match(raw):
            in_target_list = True
            continue
        if in_target_list:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _MATRIX_TARGET_LINE.match(raw)
            if match is None:
                in_target_list = False
                continue
            targets.add(match.group(1))
    return targets


def collect_ci_matrix_targets(*, workflows_dir: Path) -> set[str]:
    """Union the `matrix.target` slugs across every workflow file in the dir."""
    targets: set[str] = set()
    for path in sorted(workflows_dir.glob("*.yml")):
        targets |= _parse_ci_matrix_targets(source=path.read_text(encoding="utf-8"))
    for path in sorted(workflows_dir.glob("*.yaml")):
        targets |= _parse_ci_matrix_targets(source=path.read_text(encoding="utf-8"))
    return targets
