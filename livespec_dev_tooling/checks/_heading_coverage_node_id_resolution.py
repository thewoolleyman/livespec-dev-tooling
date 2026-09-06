"""_heading_coverage_node_id_resolution — a mapped node id must name a REAL test.

Direction 5 of `heading_coverage`, extracted to a private sibling module for
the same reason `_heading_coverage_tier_resolution` was: the parent keeps the
spec-heading walk, the registry diff, and every structured diagnostic, while
each resolution concern owns its own file. The leading underscore marks this a
private sibling — `canonical_check_slugs` skips `_`-prefixed modules, so it is
not a check slug, and `tests_mirror_pairing` exempts it.

## WHAT THIS DIRECTION EXISTS TO CATCH — `livespec-dev-tooling-8t0i`

Until this module landed, `heading_coverage` NEVER RESOLVED THE NODE IDS IT WAS
GIVEN. A registry row could name a test function that does not exist, or a
module that does not exist, and the check exited 0. Measured with two sabotage
controls in `livespec-overseer` at release 1.24.1 (an existing module with a
nonexistent function; a wholly nonexistent module) — both silent, both exit 0 —
while the four directions the check DOES implement all fired correctly. So the
check worked; existence simply was not among the things it verified.

⛔ THE ASYMMETRY IS WHAT MAKES THIS A CHECKER DEFECT RATHER THAN AN AUTHORING
ONE. The check ALREADY fails when a heading has no row, so an author who has
not yet written the test is pushed toward supplying a row, and the cheapest row
that satisfies the check is a mapped one naming a plausible test path. The
check pushed toward the one failure mode it could not see.

AND THE ROWS THAT DEMONSTRATED IT WERE NOT CARELESS. In `livespec-overseer`, 12
of 146 non-TODO rows named two integration modules that never existed in that
repository's history. All twelve carried a `work_item`, and all twelve carried
a `reason` opening "NOT YET WRITTEN — owned by <id>", so a human reading the
JSON saw a careful entry naming its own debt. The registry signals a
placeholder machine-readably through ONE field — `test == "TODO"` — and every
coverage and tier branch reads exactly that field. Those rows told the truth in
prose and lied in the one field that is read: AN HONEST `reason` BESIDE A
MAPPED `test` IS INDISTINGUISHABLE FROM REAL COVERAGE. That is why the remedy
is resolving the id against the tree, and why teaching the checker to sniff
debt-like prose would not have worked — prose is not a contract, and the
authors WERE careful.

## WHAT RESOLVES, AND THE TWO BOUNDS THAT ARE DELIBERATE

A non-TODO row's `test` is resolved in two spellings, because both occur in
governed registries: a DOTTED node id (`tests.integration.test_flow.test_case`)
and a pytest-native `path::name` id (`tests/foo.py::test_foo`). A trailing
`[param]` is stripped — a parametrised id names the same function.

  1. THE MODULE HALF SEARCHES LONGEST-PREFIX-FIRST rather than assuming the
     module is everything-but-the-last-segment. `tests.x.TestCase.test_m` names
     `tests/x.py`, not `tests/x/TestCase.py`, and a class-qualified id must not
     be convicted for a class the author spelled correctly.
  2. THE FUNCTION HALF ASKS WHETHER THE MODULE DEFINES A `def` OF THAT NAME AT
     ANY NESTING — module level or inside a class — and deliberately does NOT
     verify the intermediate class segment. This is the SAME lookup
     `_heading_coverage_tier_resolution._function_has_integration_marker`
     performs, and the alignment is the point: two directions resolving one
     node id must not give two different answers about it.

## ON THE `IOResult` RAILWAY — the same split the tier resolver took

⛔ "THIS ID DOES NOT RESOLVE" IS NOT "I COULD NOT READ THE FILE TO FIND OUT",
and fusing them would rebuild, in a check written to remove one false verdict,
exactly the collapse `livespec-dev-tooling-8o8e.9` removed from its sibling.

AN ANSWER (success track, and a direction-5 VIOLATION): the id names no module
file anywhere along its prefix chain; the module parses and defines no `def` of
that name; the id is neither dotted nor a `path::name` id, so it resolves to no
module by inspection with no I/O at all.

A FAILURE (failure track, NOT a violation): the module file EXISTS and cannot
be turned into a tree — an `OSError` that is not `FileNotFoundError` (a
directory where a module belongs, a permission or I/O error), or a source that
does not parse. `ValueError` rides with `SyntaxError` because `ast.parse`
raises it for an embedded NUL. The parent reports this as UNRESOLVED and still
exits non-zero: a check that cannot decide has not passed.
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
# file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `heading_coverage.py`, so pyright's per-file analysis does not flag
# them unused across the package boundary.
__all__: list[str] = [
    "NodeIdUnreadable",
    "UnresolvedNodeId",
    "unresolvable_node_ids",
]


# The registry's machine-readable placeholder. A TODO row is not a claim of
# coverage at all, so it has no node id to resolve; direction 3 governs it.
_TODO = "TODO"

# A resolvable dotted node id needs at least a module component and a function
# component (`module.func`).
_MIN_DOTTED_PARTS = 2

# pytest's native node-id separator (`tests/foo.py::TestCase::test_case`).
_PYTEST_ID_SEPARATOR = "::"

# The opening bracket of a parametrised id's case label (`test_case[a-1]`).
_PARAMETRISATION_OPEN = "["

# The registry fields the coverage diff requires to be strings. An entry
# missing any of them is skipped THERE, so it is skipped here too.
_TRIPLE_KEYS = ("spec_root", "spec_file", "heading")


@dataclass(frozen=True, kw_only=True)
class UnresolvedNodeId:
    """A registry row whose `test` names something that does not exist.

    `entry` is the offending row verbatim, so the parent's diagnostic can name
    the heading the row claims to cover rather than only the dangling id.
    `reason` is the discriminator a caller branches on and `detail` the
    operator-facing evidence, kept separate for the reason `TierUnresolvable`
    keeps them separate: a diagnostic must be able to name the cause without a
    reader parsing prose.
    """

    entry: dict[str, object]
    reason: Literal["node-id-not-a-test-path", "module-file-absent", "test-function-absent"]
    detail: str


@dataclass(frozen=True, kw_only=True)
class NodeIdUnreadable:
    """A mapped module EXISTS and could not be read, so resolution is UNKNOWN.

    ⛔ NOT A VIOLATION. Reporting "this node id does not resolve" about a file
    the check never read would be the same false verdict the tier resolver's
    railway conversion removed — and reporting it from the direction added to
    stop false coverage claims would be worse, not better.
    """

    reason: Literal["test-file-unreadable", "test-file-unparseable"]
    detail: str


def _plain_name(*, segment: str) -> str:
    """`test_case[a-1]` → `test_case`: a parametrised id names the same function."""
    return segment.partition(_PARAMETRISATION_OPEN)[0]


def _names_a_triple(*, entry: dict[str, object]) -> bool:
    """Whether the row carries the full string triple the coverage diff reads.

    Mirrors `_registry_triples_and_todo_violations`'s guard deliberately: a
    malformed row the coverage diff already skips must not acquire a second,
    different verdict here.
    """
    return all(isinstance(entry.get(key), str) for key in _TRIPLE_KEYS)


def _module_candidates_and_target(*, test_id: str) -> tuple[list[Path], str] | None:
    """Split a node id into (candidate module paths, target `def` name).

    `tests.e2e.test_happy.test_minimal` →
    `([tests/e2e/test_happy.py, tests/e2e.py, tests.py], "test_minimal")`, most
    specific first — see bound 1 in the module docstring for why the chain
    rather than a single guess. `tests/foo.py::TestCase::test_case` →
    `([tests/foo.py], "test_case")`.

    Returns `None` when the id is neither spelling, which is an ANSWER (it
    resolves to no module by inspection, with no I/O involved) rather than a
    failure to look.
    """
    if _PYTEST_ID_SEPARATOR in test_id:
        path_part, _, remainder = test_id.partition(_PYTEST_ID_SEPARATOR)
        segments = [part for part in remainder.split(_PYTEST_ID_SEPARATOR) if part]
        if not segments:
            return None
        return [Path(path_part)], _plain_name(segment=segments[-1])
    parts = test_id.split(".")
    if len(parts) < _MIN_DOTTED_PARTS:
        return None
    candidates = [Path(*parts[:i]).with_suffix(".py") for i in range(len(parts) - 1, 0, -1)]
    return candidates, _plain_name(segment=parts[-1])


def _read_first_existing(
    *, repo_root: Path, candidates: list[Path]
) -> IOResult[tuple[Path, str] | None, NodeIdUnreadable]:
    """Read the most specific candidate module that exists; `None` when none does.

    ONE `try` rather than `is_file()` then `read_text()`: the pre-check pair
    fuses absent with unreadable AND leaves a TOCTOU second arm no test can
    reach. Splitting on `FileNotFoundError` separates them for free — absence
    means "keep searching the prefix chain", while any other `OSError` is a
    checkout defect this module refuses to render as a verdict.
    """
    for candidate in candidates:
        try:
            source = (repo_root / candidate).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except OSError as unreadable:
            return IOFailure(
                NodeIdUnreadable(reason="test-file-unreadable", detail=f"{candidate}: {unreadable}")
            )
        return IOSuccess((candidate, source))
    return IOSuccess(None)


def _defines(*, tree: ast.Module, name: str) -> bool:
    """Whether the module defines a `def`/`async def` of `name` at ANY nesting.

    Bound 2 of the module docstring: module-level function or method, the same
    lookup the tier resolver performs, so one node id cannot be resolvable to
    one direction and dangling to the other.
    """
    return any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
        for node in ast.walk(tree)
    )


def _entry_violation(
    *, repo_root: Path, entry: dict[str, object], test_id: str
) -> IOResult[UnresolvedNodeId | None, NodeIdUnreadable]:
    """Resolve one row's node id; `None` on the success track means it resolves."""
    split = _module_candidates_and_target(test_id=test_id)
    if split is None:
        return IOSuccess(
            UnresolvedNodeId(
                entry=entry,
                reason="node-id-not-a-test-path",
                detail=f"{test_id}: neither a dotted node id nor a `path::name` node id",
            )
        )
    candidates, target = split
    read = _read_first_existing(repo_root=repo_root, candidates=candidates)
    if isinstance(read, IOFailure):
        return read
    found = unsafe_perform_io(read.unwrap())
    if found is None:
        return IOSuccess(
            UnresolvedNodeId(
                entry=entry,
                reason="module-file-absent",
                detail=f"{test_id} -> no module file at {candidates[0]}",
            )
        )
    module_path, source = found
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as unparseable:
        return IOFailure(
            NodeIdUnreadable(
                reason="test-file-unparseable", detail=f"{test_id} -> {module_path}: {unparseable}"
            )
        )
    if _defines(tree=tree, name=target):
        return IOSuccess(None)
    return IOSuccess(
        UnresolvedNodeId(
            entry=entry,
            reason="test-function-absent",
            detail=f"{test_id} -> {module_path} defines no `def {target}`",
        )
    )


def unresolvable_node_ids(
    *, repo_root: Path, entries: list[dict[str, object]]
) -> IOResult[list[UnresolvedNodeId], NodeIdUnreadable]:
    """Registry rows whose mapped node id names no existing test (direction 5).

    ⛔ AN EMPTY LIST MEANS "RESOLVED, AND EVERY MAPPED ROW NAMES A REAL TEST" —
    nothing else. A single row the resolver could not decide takes the whole
    scan to the failure track rather than letting a partial answer be read as a
    complete one, exactly as `scenario_tier_violations` does; the parent's
    other directions are computed independently and still report in the run.
    """
    out: list[UnresolvedNodeId] = []
    for entry in entries:
        test_id = entry.get("test")
        if not isinstance(test_id, str) or test_id == _TODO or not _names_a_triple(entry=entry):
            continue
        scanned = _entry_violation(repo_root=repo_root, entry=entry, test_id=test_id)
        if isinstance(scanned, IOFailure):
            return scanned
        violation = unsafe_perform_io(scanned.unwrap())
        if violation is not None:
            out.append(violation)
    return IOSuccess(out)
