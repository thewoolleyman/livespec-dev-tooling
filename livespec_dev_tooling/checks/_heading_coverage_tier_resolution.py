"""_heading_coverage_tier_resolution — scenarios.md integration-tier resolution.

Extracted from `heading_coverage.py` so the parent check's LLOC stays under
the 250-line hard ceiling — the same LLOC-reduction split as `_ci_matrix_parse`
and `_red_green_replay_modes`. The leading underscore marks this a private
sibling module: entry-point check scripts under `livespec_dev_tooling/checks/`
carry no underscore prefix, so this file is neither a canonical slug
(`canonical_check_slugs` skips `_`-prefixed modules) nor a mirror-paired module
(`tests_mirror_pairing` exempts `_`-prefixed files; its behavior is covered
through the parent's subprocess tests, exactly as `_ci_matrix_parse` is covered
through `test_ci_matrix_completeness`).

This module owns direction 4 of `heading_coverage` — "a `scenarios.md` heading
must map to an integration-tier-or-above test, never a unit-tier one" per
`SPECIFICATION/constraints.md` section "Heading taxonomy". A `scenarios.md` entry is
compliant when one of the following holds:

  - `test == "TODO"` and its (non-empty) `reason` explicitly acknowledges the
    tier requirement (case-insensitive match on one of the tier keywords:
    `tier`, `integration`, `e2e`, `consumer`, `pyramid`); OR
  - the dotted `test` node id begins with one of the allowlisted
    integration-tier prefixes (`test_id == prefix` or
    `test_id.startswith(prefix + ".")`); OR
  - the resolved test function carries an explicit `pytest.mark.integration`
    (or a stronger tier marker such as `e2e`/`consumer`) — detected STATICALLY
    via AST (function-, class-, or module-level `pytestmark`), never by
    executing pytest.

`scenario_tier_violations` returns the registry entries that fail direction 4;
the parent `main()` owns every structured diagnostic. `DEFAULT_SCENARIO_TIERS`
is the documented allowlist default the parent falls back to when a consumer
repo declares no `[tool.livespec_dev_tooling].scenario_tiers` array.

## ON THE `IOResult` RAILWAY — `livespec-dev-tooling-8o8e.9`

`_node_id_resolves_with_marker` reads the mapped test file DIRECTLY rather
than through an injected seam, so this module is the I/O boundary and
`IOResult` rather than `Result` is the honest container (the same reading that
put `_docs_only_change` and `_primary_checkout_git_probes` there).

WHAT THE OLD `list[dict[str, object]]` COULD NOT SAY. The resolver caught
`(OSError, SyntaxError)` and returned `False` — documented as "no marker found
so the prefix path governs" — which fused **"this test carries no
integration-tier marker"** with **"I could not read the file to find out"**.
The entry then fell through to the violation list, and the parent reported
*"scenario heading mapped to unit-tier test"*: a definitive verdict about a
test the check never read. `qndn-75-triage.md` pairs this row with
`is_docs_only_change` under ONE question — *is a deliberate fail-closed
collapse of an inhabited failure track a violation, or a sanctioned design?* —
and the answer is a violation: section "ROP composition" declares its exemption set
exhaustive, and an intent stated in a docstring is not a ratified exemption.

WHAT IS AND IS NOT A FAILURE HERE, and it is the same split the carve-out took.
**A NODE ID THAT NAMES NO FILE IS AN ANSWER.** The read HAPPENED and there is
no such module, so there is no marker — `False` is a verdict rather than a
placeholder, and the entry is correctly a direction-4 violation. Likewise a
node id with no dot at all: it resolves to no module by inspection, with no I/O
involved. A FAILURE is a file that EXISTS and cannot be turned into a tree: an
`OSError` that is not `FileNotFoundError`, or a source that does not parse.

That split also removed an `is_file()`-then-`read_text()` pre-check pair, which
fused absent with unreadable AND left a TOCTOU second arm no test could reach.
One `try` splits them on `FileNotFoundError` for free.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Carried rather than inherited from an importer: without it the vendored
# `returns` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this
# file. The module that broke the fleet's release fan-out for seven hours on
# 2026-07-30 was in exactly that state until it became a process entry point.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `heading_coverage.py`, so pyright's per-file analysis does not flag
# them unused across the package boundary.
__all__: list[str] = [
    "DEFAULT_SCENARIO_TIERS",
    "TierUnresolvable",
    "scenario_tier_violations",
]


# The documented default integration-tier node-id prefix allowlist, used by the
# parent when a consumer repo declares no `[tool.livespec_dev_tooling]
# .scenario_tiers` array. A `scenarios.md` heading's mapped test node id is
# integration-tier-or-above when its leading dotted path component matches one
# of these prefixes.
DEFAULT_SCENARIO_TIERS: tuple[str, ...] = (
    "tests.e2e",
    "tests.integration",
    "tests.consumer",
    "tests.prompts",
)

# The `scenarios.md` spec-file name direction 4 governs.
_SCENARIOS_FILE = "scenarios.md"

# Tier-acknowledgment keywords (case-insensitive) a `scenarios.md` TODO's
# `reason` MUST contain to satisfy the integration-tier requirement during
# transition. The non-empty-`reason` TODO check still applies independently.
_TIER_REASON_KEYWORDS: tuple[str, ...] = (
    "tier",
    "integration",
    "e2e",
    "consumer",
    "pyramid",
)

# pytest marker names that satisfy the integration-tier-or-above requirement
# when found (statically) as a decorator / class marker / module `pytestmark`.
_INTEGRATION_TIER_MARKERS: frozenset[str] = frozenset({"integration", "e2e", "consumer", "prompts"})

# A resolvable dotted node id needs at least a module component and a function
# component (`module.func`); `pytest.mark.<name>` likewise needs `mark.<name>`.
_MIN_DOTTED_PARTS = 2

# The two ANSWERS the resolver gives without reading a tree, named rather than
# written inline because `flake8-boolean-trap` (FBT003) refuses a bare boolean
# literal at a call site — the spelling
# `_primary_checkout_git_probes._UNSET_KEY_RESOLVES_TO` uses — and because each
# name carries the RULING that makes it an answer rather than a placeholder.
_UNDOTTED_NODE_ID_RESOLVES_TO_NO_MODULE: bool = False
_ABSENT_TEST_FILE_CARRIES_NO_MARKER: bool = False


@dataclass(frozen=True, kw_only=True)
class TierUnresolvable:
    """A mapped test EXISTS and could not be read, so its tier is UNKNOWN.

    ⛔ "COULD NOT RESOLVE THE TIER" IS NOT "THE TIER IS UNIT", and keeping them
    apart is the whole point: the old shape reported the second when it meant
    the first, so a test file the check could not open was reported to its
    author as a scenarios.md heading mapped to a unit-tier test.

    `reason` is the discriminator a caller branches on; `detail` is the
    operator-facing evidence, and the two are deliberately separate so a
    diagnostic can name the cause without the caller parsing prose. The two
    want different responses: `test-file-unreadable` is a broken checkout (a
    directory where a module belongs, a permission or I/O error), while
    `test-file-unparseable` is a test file that does not compile.
    """

    reason: Literal["test-file-unreadable", "test-file-unparseable"]
    detail: str


def _node_id_has_allowlisted_prefix(*, test_id: str, tiers: tuple[str, ...]) -> bool:
    return any(test_id == prefix or test_id.startswith(prefix + ".") for prefix in tiers)


def _reason_acknowledges_tier(*, reason: str) -> bool:
    lowered = reason.lower()
    return any(keyword in lowered for keyword in _TIER_REASON_KEYWORDS)


def _split_node_id(*, test_id: str) -> tuple[list[str], str] | None:
    """Split a dotted node id into (module-path components, function name).

    `tests.e2e.test_happy_path.test_happy_path_minimal` →
    `(["tests", "e2e", "test_happy_path"], "test_happy_path_minimal")`.
    Returns `None` when the node id has no dot (cannot resolve to a
    file/function) so the caller treats it as "no marker found".
    """
    parts = test_id.split(".")
    if len(parts) < _MIN_DOTTED_PARTS:
        return None
    return parts[:-1], parts[-1]


def _decorator_marker_names(*, decorators: list[ast.expr]) -> set[str]:
    """The set of `pytest.mark.<name>` (or `mark.<name>`) names among decorators."""
    out: set[str] = set()
    for decorator in decorators:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        # `pytest.mark.integration` unparses to that dotted string; the marker
        # name is the terminal attribute, with `mark` as its immediate parent.
        rendered = ast.unparse(target)
        components = rendered.split(".")
        if len(components) >= _MIN_DOTTED_PARTS and components[-2] == "mark":
            out.add(components[-1])
    return out


def _module_pytestmark_names(*, tree: ast.Module) -> set[str]:
    """Marker names declared via a module-level `pytestmark = ...` assignment."""
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = node.targets
            value: ast.expr | None = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if value is None:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            continue
        expressions = value.elts if isinstance(value, ast.List | ast.Tuple) else [value]
        out |= _decorator_marker_names(decorators=list(expressions))
    return out


def _function_has_integration_marker(*, tree: ast.Module, func_name: str) -> bool:
    """Statically decide whether `func_name` carries an integration-tier marker.

    Accepts a function-level decorator, a class-level marker on the enclosing
    class, or a module-level `pytestmark`. Never executes pytest.
    """
    module_markers = _module_pytestmark_names(tree=tree)
    if module_markers & _INTEGRATION_TIER_MARKERS:
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_markers = _decorator_marker_names(decorators=list(node.decorator_list))
            class_carries = bool(class_markers & _INTEGRATION_TIER_MARKERS)
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                    and child.name == func_name
                ):
                    func_markers = _decorator_marker_names(decorators=list(child.decorator_list))
                    if class_carries or (func_markers & _INTEGRATION_TIER_MARKERS):
                        return True
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == func_name:
            func_markers = _decorator_marker_names(decorators=list(node.decorator_list))
            if func_markers & _INTEGRATION_TIER_MARKERS:
                return True
    return False


def _node_id_resolves_with_marker(
    *, repo_root: Path, test_id: str
) -> IOResult[bool, TierUnresolvable]:
    """Resolve a dotted node id to a file + function and AST-scan for the marker.

    `tests.e2e.test_happy_path.test_happy_path_minimal` →
    `tests/e2e/test_happy_path.py`, function `test_happy_path_minimal`.

    TWO of the old `False` returns are ANSWERS and stay on the success track: a
    node id with no dot resolves to no module by inspection, and a node id
    whose module file is ABSENT has no marker because there is no test. Both
    are verdicts a completed read produced, so the prefix path governs exactly
    as it did.

    The other two are FAILURES. The catch is NARROW and ENUMERATED: an `OSError`
    that is not `FileNotFoundError` (a directory where a module belongs, a
    permission or I/O error), and a source that does not parse. `ValueError`
    rides with `SyntaxError` because `ast.parse` raises it for an embedded NUL.
    A bug raised inside `_function_has_integration_marker` still propagates.
    """
    split = _split_node_id(test_id=test_id)
    if split is None:
        return IOSuccess(_UNDOTTED_NODE_ID_RESOLVES_TO_NO_MODULE)
    module_parts, func_name = split
    candidate = repo_root / Path(*module_parts).with_suffix(".py")
    # ONE `try` rather than `is_file()` then `read_text()`: the pre-check pair
    # fused absent with unreadable AND left a TOCTOU second arm no test could
    # reach. Splitting on `FileNotFoundError` separates them for free and makes
    # every arm here naturally reachable without monkeypatching.
    try:
        source = candidate.read_text(encoding="utf-8")
    except FileNotFoundError:
        return IOSuccess(_ABSENT_TEST_FILE_CARRIES_NO_MARKER)
    except OSError as unreadable:
        return IOFailure(
            TierUnresolvable(
                reason="test-file-unreadable", detail=f"{test_id} -> {candidate}: {unreadable}"
            )
        )
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as unparseable:
        return IOFailure(
            TierUnresolvable(
                reason="test-file-unparseable", detail=f"{test_id} -> {candidate}: {unparseable}"
            )
        )
    return IOSuccess(_function_has_integration_marker(tree=tree, func_name=func_name))


def scenario_tier_violations(
    *, repo_root: Path, entries: list[dict[str, object]], tiers: tuple[str, ...]
) -> IOResult[list[dict[str, object]], TierUnresolvable]:
    """Registry entries for `scenarios.md` mapped to a unit-tier test (direction 4).

    ⛔ AN EMPTY LIST NOW MEANS "RESOLVED, AND NO ENTRY IS UNIT-TIER" — nothing
    else. A single entry the resolver could not decide takes the whole scan to
    the failure track rather than letting a partial verdict be read as a
    complete one; the parent's other three directions are computed
    independently and still report in the same run.
    """
    out: list[dict[str, object]] = []
    for entry in entries:
        if entry.get("spec_file") != _SCENARIOS_FILE:
            continue
        test_id = entry.get("test")
        if not isinstance(test_id, str):
            continue
        if test_id == "TODO":
            reason = entry.get("reason")
            # An empty/absent reason is already reported by direction 3; only
            # fire direction 4 for a non-empty reason that omits tier wording.
            if (
                isinstance(reason, str)
                and reason.strip()
                and not _reason_acknowledges_tier(reason=reason)
            ):
                out.append(entry)
            continue
        if _node_id_has_allowlisted_prefix(test_id=test_id, tiers=tiers):
            continue
        resolved = _node_id_resolves_with_marker(repo_root=repo_root, test_id=test_id)
        if isinstance(resolved, IOFailure):
            return resolved
        if unsafe_perform_io(resolved.unwrap()):
            continue
        out.append(entry)
    return IOSuccess(out)
