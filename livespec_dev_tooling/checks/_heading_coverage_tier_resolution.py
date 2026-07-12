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
`SPECIFICATION/constraints.md` §"Heading taxonomy". A `scenarios.md` entry is
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
"""

from __future__ import annotations

import ast
from pathlib import Path

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `heading_coverage.py`, so pyright's per-file analysis does not flag
# them unused across the package boundary.
__all__: list[str] = [
    "DEFAULT_SCENARIO_TIERS",
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


def _node_id_resolves_with_marker(*, repo_root: Path, test_id: str) -> bool:
    """Resolve a dotted node id to a file + function and AST-scan for the marker.

    `tests.e2e.test_happy_path.test_happy_path_minimal` →
    `tests/e2e/test_happy_path.py`, function `test_happy_path_minimal`. If the
    node id cannot be resolved to a file/function (no dot, missing file, parse
    error), returns `False` ("no marker found") so the prefix path governs.
    """
    split = _split_node_id(test_id=test_id)
    if split is None:
        return False
    module_parts, func_name = split
    candidate = repo_root / Path(*module_parts).with_suffix(".py")
    if not candidate.is_file():
        return False
    try:
        tree = ast.parse(candidate.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    return _function_has_integration_marker(tree=tree, func_name=func_name)


def scenario_tier_violations(
    *, repo_root: Path, entries: list[dict[str, object]], tiers: tuple[str, ...]
) -> list[dict[str, object]]:
    """Registry entries for `scenarios.md` mapped to a unit-tier test (direction 4)."""
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
        if _node_id_resolves_with_marker(repo_root=repo_root, test_id=test_id):
            continue
        out.append(entry)
    return out
