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
import sys
from pathlib import Path

# `returns` is VENDORED, not installed, so this module puts `_vendor/` on the
# path ITSELF rather than relying on its importer having done so — a property
# of the callers, not of this file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware.

from livespec_dev_tooling.checks._check_aggregate_failures import (  # noqa: E402
    CheckRecipeAbsent,
    TargetsArrayAbsent,
    TargetsArrayFailure,
    TargetsArrayUnterminated,
    WorkflowFileUnreadable,
)

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


def extract_check_recipe_body(*, justfile_text: str) -> Result[str, CheckRecipeAbsent]:
    """The text body of the `check:` recipe.

    A just recipe body extends from the recipe header to the next
    recipe header (a non-indented line ending in `:`) or to EOF.

    The DELIBERATE DUPLICATE of `_ci_matrix_parse`'s reader — permitted under
    the bounded parser-duplication convention stated in that module's
    docstring, because this is a mechanical extractor carrying no spec
    citation. It fails with the SAME shared type, so the two copies agree
    about what a failure IS even while their bodies stay independent.
    """
    header_match = _CHECK_RECIPE_HEADER.search(justfile_text)
    if header_match is None:
        return Failure(CheckRecipeAbsent())
    body_start = header_match.end()
    lines = justfile_text[body_start:].splitlines()
    body_lines: list[str] = []
    for raw in lines:
        if raw and not raw.startswith((" ", "\t")) and ":" in raw:
            break
        body_lines.append(raw)
    return Success("\n".join(body_lines))


def extract_targets_array_tokens(*, recipe_body: str) -> Result[list[str], TargetsArrayFailure]:
    """The `check-*` slugs inside `targets=(...)`.

    Blank lines, full-line comments, inline trailing comments, and any
    token that does not start with `check-` are dropped — matching
    aggregate_completeness's filtering so the two checks agree on what
    counts as a literal targets-array slug.

    TWO failure types, the same split `_ci_matrix_parse`'s twin took: an
    absent array and an UNTERMINATED one shared one `None`, and the caller
    reported only the absent case, so an unclosed array sent the operator to
    add an array already present.
    """
    start_match = _TARGETS_ARRAY_START.search(recipe_body)
    if start_match is None:
        return Failure(TargetsArrayAbsent())
    after_start = recipe_body[start_match.end() :]
    collected: list[str] = []
    for raw in after_start.splitlines():
        if _TARGETS_ARRAY_END.match(raw):
            return Success(collected)
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split("#", 1)[0].strip()
        if token.startswith("check-"):
            collected.append(token)
    return Failure(TargetsArrayUnterminated())


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


def collect_ci_matrix_targets(
    *,
    workflows_dir: Path,
) -> IOResult[set[str], WorkflowFileUnreadable]:
    """Union the `matrix.target` slugs across every workflow file in the dir.

    An ABSENT or EMPTY directory ANSWERS with an empty set — the ratified
    missing-file tolerance. Only failing to obtain bytes from a file the glob
    just listed is a failure, and it is a failure rather than a skipped
    contribution ON PURPOSE: the parent asserts CI RUNS what the justfile
    WIRES, so a silently skipped workflow makes a slug that IS run look unrun
    and manufactures a gap. `read_text` was unguarded before this, so an
    undecodable workflow raised out of the check.

    The two globs are unioned before the walk rather than walked separately;
    the result is a set union, so ordering carries no meaning.
    """
    targets: set[str] = set()
    for path in sorted([*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml")]):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as unreadable:
            return IOFailure(WorkflowFileUnreadable(path=str(path), detail=str(unreadable)))
        targets |= _parse_ci_matrix_targets(source=source)
    return IOSuccess(targets)
