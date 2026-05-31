"""heading_coverage — every spec-tree-root NLSpec heading has a coverage entry.

Per `SPECIFICATION/constraints.md` §"Heading taxonomy" (post-v004),
the registry at `tests/heading-coverage.json` maps `(spec_root,
spec_file, heading)` triples to pytest test identifiers. The check
walks ONLY the template-declared NLSpec files at each spec-tree
root — for the `livespec` template, the four files `spec.md`,
`contracts.md`, `constraints.md`, and `scenarios.md`. It does NOT
recurse into `proposed_changes/`, `history/`,
`templates/<name>/history/`, or any other subdirectory; it does NOT
include the skill-owned `README.md`.

The check fails on four directions:

1. Uncovered heading — a `(spec_root, spec_file, heading)` triple
   appears in some spec file but no matching registry entry exists.
2. Orphan registry entry — a registry entry's triple does not match
   any heading in any template-declared spec file.
3. Missing `reason` on a TODO entry — entry carries `test: "TODO"`
   but no non-empty `reason` field.
4. Scenario heading mapped to a unit-tier test — for a registry
   entry whose `spec_file` is `scenarios.md`, the mapped `test`
   node id MUST resolve to a test at the integration tier or above
   (never a unit-tier test), per `SPECIFICATION/constraints.md`
   §"Heading taxonomy". A scenario describes user-observable
   behavior, which a unit test does not exercise. This direction
   applies ONLY to `scenarios.md`; headings in `spec.md`,
   `contracts.md`, and `constraints.md` MAY be exercised by
   unit-tier tests. A `scenarios.md` entry is compliant when one of
   the following holds:
     - `test == "TODO"` and its (non-empty) `reason` explicitly
       acknowledges the tier requirement (case-insensitive match on
       one of the tier keywords: `tier`, `integration`, `e2e`,
       `consumer`, `pyramid`); OR
     - the dotted `test` node id begins with one of the allowlisted
       integration-tier prefixes (`test_id == prefix` or
       `test_id.startswith(prefix + ".")`); OR
     - the resolved test function carries an explicit
       `pytest.mark.integration` (or a stronger tier marker such as
       `e2e`/`consumer`) — detected STATICALLY via AST (function-,
       class-, or module-level `pytestmark`), never by executing
       pytest.
   Otherwise the distinct diagnostic
   `scenario heading mapped to unit-tier test` fires.

The allowlist of integration-tier node-id prefixes is read per
consumer repo from the `[tool.livespec_dev_tooling]` block's
`scenario_tiers` array in the consuming repo's root `pyproject.toml`
(via `livespec_dev_tooling.config.load_scenario_tiers`). When the
table/key is absent, the module-level documented default
`_DEFAULT_SCENARIO_TIERS` is used:
`("tests.e2e", "tests.integration", "tests.consumer",
"tests.prompts")`. Each consumer thus declares its own
integration-test directory convention without amending this check.

The check SKIPS `##` headings whose text begins with the literal
`Scenario:` prefix in every spec file EXCEPT `scenarios.md`. In
`scenarios.md` each `## Scenario:` heading is tracked granularly and
REQUIRES its own registry entry — the uncovered, orphan, and
integration-tier directions above all govern it (many entries MAY map
to one consumer-tier test). `Scenario:`-prefixed headings in other
spec files (`spec.md`, `contracts.md`, etc.) remain out of registry
scope and are still skipped.

Pre-Phase-6 the check tolerates an empty `[]` array; from the
Phase 6 seed forward, emptiness is a failure if any spec tree
exists.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import load_scenario_tiers  # noqa: E402

__all__: list[str] = []


_MAIN_SPEC_ROOT = Path("SPECIFICATION")
_SUB_SPEC_PARENT = Path("SPECIFICATION") / "templates"
_COVERAGE_PATH = Path("tests") / "heading-coverage.json"
_TREE_ROOT_NLSPEC_FILES = (
    "spec.md",
    "contracts.md",
    "constraints.md",
    "non-functional-requirements.md",
    "scenarios.md",
)
_SCENARIO_PREFIX = "Scenario:"
_SCENARIOS_FILE = "scenarios.md"

# The documented default integration-tier node-id prefix allowlist, used when a
# consumer repo declares no `[tool.livespec_dev_tooling].scenario_tiers` array.
# A `scenarios.md` heading's mapped test node id is integration-tier-or-above
# when its leading dotted path component matches one of these prefixes.
_DEFAULT_SCENARIO_TIERS: tuple[str, ...] = (
    "tests.e2e",
    "tests.integration",
    "tests.consumer",
    "tests.prompts",
)

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


def _enumerate_tree_roots(*, repo_root: Path) -> list[Path]:
    main = repo_root / _MAIN_SPEC_ROOT
    if not main.is_dir():
        return []
    out = [main]
    sub_parent = repo_root / _SUB_SPEC_PARENT
    if sub_parent.is_dir():
        for child in sorted(sub_parent.iterdir()):
            if child.is_dir():
                out.append(child)
    return out


def _enumerate_tree_root_spec_files(*, tree_root: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for name in _TREE_ROOT_NLSPEC_FILES:
        candidate = tree_root / name
        if candidate.is_file():
            out.append((name, candidate))
    return out


def _extract_h2_headings(*, source: str) -> list[str]:
    out: list[str] = []
    for raw in source.splitlines():
        stripped = raw.rstrip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            out.append(stripped)
    return out


def _is_scenario_heading(*, heading: str) -> bool:
    return heading.removeprefix("## ").startswith(_SCENARIO_PREFIX)


def _spec_triples(*, repo_root: Path) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for tree_root in _enumerate_tree_roots(repo_root=repo_root):
        spec_root_str = str(tree_root.relative_to(repo_root))
        for spec_file_name, spec_file_path in _enumerate_tree_root_spec_files(tree_root=tree_root):
            source = spec_file_path.read_text(encoding="utf-8")
            for heading in _extract_h2_headings(source=source):
                # `## Scenario:`-prefixed headings are skipped in every spec
                # file EXCEPT `scenarios.md`. In `scenarios.md` each scenario
                # heading is tracked granularly and REQUIRES its own registry
                # entry, so the uncovered/orphan/tier directions govern it.
                if _is_scenario_heading(heading=heading) and spec_file_name != _SCENARIOS_FILE:
                    continue
                out.add((spec_root_str, spec_file_name, heading))
    return out


def _registry_triples_and_todo_violations(
    *, entries: list[dict[str, object]]
) -> tuple[set[tuple[str, str, str]], list[dict[str, object]]]:
    triples: set[tuple[str, str, str]] = set()
    todo_missing_reason: list[dict[str, object]] = []
    for entry in entries:
        spec_root = entry.get("spec_root")
        spec_file = entry.get("spec_file")
        heading = entry.get("heading")
        test_id = entry.get("test")
        if not (
            isinstance(spec_root, str) and isinstance(spec_file, str) and isinstance(heading, str)
        ):
            continue
        triples.add((spec_root, spec_file, heading))
        if test_id == "TODO":
            reason = entry.get("reason")
            if not (isinstance(reason, str) and reason.strip()):
                todo_missing_reason.append(entry)
    return triples, todo_missing_reason


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


def _scenario_tier_violations(
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


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("heading_coverage")
    cwd = Path.cwd()
    coverage_path = cwd / _COVERAGE_PATH
    coverage_entries: list[dict[str, object]] = []
    if coverage_path.is_file():
        text = coverage_path.read_text(encoding="utf-8")
        parsed = json.loads(text)
        if isinstance(parsed, list):
            # The `cast` is the single typed parse boundary: `json.loads`
            # yields `Any`, the `isinstance` guard narrows to `list`, and the
            # cast gives the elements a typed `object` shape so the per-element
            # `isinstance(e, dict)` filter stays a load-bearing runtime guard;
            # the inner cast then types each kept entry.
            raw_entries = cast("list[object]", parsed)
            coverage_entries = [
                cast("dict[str, object]", e) for e in raw_entries if isinstance(e, dict)
            ]
    spec_set = _spec_triples(repo_root=cwd)
    registry_set, todo_missing_reason = _registry_triples_and_todo_violations(
        entries=coverage_entries
    )
    tiers = load_scenario_tiers(repo_root=cwd) or _DEFAULT_SCENARIO_TIERS
    scenario_tier_violations = _scenario_tier_violations(
        repo_root=cwd, entries=coverage_entries, tiers=tiers
    )
    uncovered = sorted(spec_set - registry_set)
    orphan = sorted(registry_set - spec_set)
    if not uncovered and not orphan and not todo_missing_reason and not scenario_tier_violations:
        return 0
    for spec_root, spec_file, heading in uncovered:
        log.error(
            "spec heading missing coverage entry",
            spec_root=spec_root,
            spec_file=spec_file,
            heading=heading,
        )
    for spec_root, spec_file, heading in orphan:
        log.error(
            "registry entry orphaned — no matching spec heading",
            spec_root=spec_root,
            spec_file=spec_file,
            heading=heading,
        )
    for entry in todo_missing_reason:
        log.error("TODO registry entry missing reason", entry=entry)
    for entry in scenario_tier_violations:
        log.error(
            "scenario heading mapped to unit-tier test",
            spec_root=entry.get("spec_root"),
            spec_file=entry.get("spec_file"),
            heading=entry.get("heading"),
            test=entry.get("test"),
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
