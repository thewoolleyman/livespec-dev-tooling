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

   Since `livespec-dev-tooling-8o8e.9` the resolver returns an
   `IOResult`, so this direction has a THIRD outcome beside compliant
   and violating: UNRESOLVED. A mapped test file that exists and
   cannot be read, or does not parse, used to arrive here as the
   violation above — a unit-tier verdict about a test the check never
   read. It now fires
   `scenario tier direction UNRESOLVED — this is not a tier verdict`
   and still exits non-zero. An ABSENT test file remains the ordinary
   violation: there is no test, so there is no marker, and that is a
   verdict the read produced.

The allowlist of integration-tier node-id prefixes is read per
consumer repo from the `[tool.livespec_dev_tooling]` block's
`scenario_tiers` array in the consuming repo's root `pyproject.toml`
(via `livespec_dev_tooling.config.load_scenario_tiers`). When the
table/key is absent, the documented default `DEFAULT_SCENARIO_TIERS`
(defined in the `_heading_coverage_tier_resolution` sibling module) is
used: `("tests.e2e", "tests.integration", "tests.consumer",
"tests.prompts")`. Each consumer thus declares its own
integration-test directory convention without amending this check.

Direction 4's tier-resolution logic — the allowlist-prefix test and the
static AST marker scan — lives in the private sibling module
`_heading_coverage_tier_resolution.py` (an LLOC-reduction split); this
file keeps the spec-heading walk, the registry diff, and the
diagnostics.

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

import json
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

# Direction-4 scenario integration-tier resolution (the allowlist-prefix and
# AST-marker logic) extracted to a private sibling module — the LLOC-reduction
# split mirroring `_ci_matrix_parse`. The parent keeps the spec-heading walk,
# the registry diff, and every structured diagnostic.
from livespec_dev_tooling.checks._heading_coverage_tier_resolution import (  # noqa: E402
    DEFAULT_SCENARIO_TIERS,
    scenario_tier_violations,
)
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
    tiers = load_scenario_tiers(repo_root=cwd) or DEFAULT_SCENARIO_TIERS
    tier_scan = scenario_tier_violations(repo_root=cwd, entries=coverage_entries, tiers=tiers)
    tier_violations: list[dict[str, object]] = []
    if isinstance(tier_scan, IOFailure):
        # Reported HERE rather than folded into the violation loop below,
        # because it is not a violation: the check could not decide the
        # direction at all. Exiting 0 on it would be the vacuous pass this
        # conversion exists to remove.
        unresolvable = unsafe_perform_io(tier_scan.failure())
        log.error(
            "scenario tier direction UNRESOLVED — this is not a tier verdict",
            check_id="heading-coverage-scenario-tier-unresolved",
            reason=unresolvable.reason,
            detail=unresolvable.detail,
        )
    else:
        tier_violations = unsafe_perform_io(tier_scan.unwrap())
    uncovered = sorted(spec_set - registry_set)
    orphan = sorted(registry_set - spec_set)
    if (
        not uncovered
        and not orphan
        and not todo_missing_reason
        and not tier_violations
        and not isinstance(tier_scan, IOFailure)
    ):
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
    for entry in tier_violations:
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
