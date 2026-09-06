"""`unresolvable_node_ids` resolves a registry row's node id against the tree.

Direction 5 of `heading_coverage`, added by `livespec-dev-tooling-8t0i`. Until
it landed the check NEVER resolved the node ids it was given: a row naming a
nonexistent function, or a wholly nonexistent module, exited 0 in silence while
the four directions the check does implement all fired correctly.

⛔ THE LOAD-BEARING LEG OF THIS FILE IS THE POSITIVE CONTROL, not the negative
one. A resolver that quietly resolves nothing and returns `[]` for everything
would be indistinguishable from the old behaviour while appearing to fix it, so
`test_an_absent_module_is_a_violation` and
`test_a_module_without_the_function_is_a_violation` — the two sabotage controls
measured in `livespec-overseer` at release 1.24.1 — come first and assert the
violation FIRES, with `test_a_fully_resolvable_row_is_no_violation` beside them
proving a healthy registry still passes.

The `IOResult` pair mirrors `_heading_coverage_tier_resolution`'s railway: an id
that resolves to nothing is an ANSWER (success track, a violation), while a
module that EXISTS and cannot be read or parsed is a FAILURE (failure track,
UNRESOLVED — not a dangling-id verdict about a file the check never read).
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOResult, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._heading_coverage_node_id_resolution import (
    NodeIdUnreadable,
    UnresolvedNodeId,
    unresolvable_node_ids,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


_MODULE_REL = "tests/custom/test_flow.py"
_NODE_ID = "tests.custom.test_flow.test_observable"

_DEFINES_IT = textwrap.dedent(
    """\
    def test_observable() -> None:
        assert True
    """
)

_DEFINES_SOMETHING_ELSE = textwrap.dedent(
    """\
    def test_unrelated() -> None:
        assert True
    """
)

_UNPARSEABLE = "def test_observable( -> None:\n"


def _row(*, test_id: object) -> dict[str, object]:
    """A registry row carrying the full string triple, mapped to `test_id`."""
    return {
        "spec_root": "SPECIFICATION",
        "spec_file": "scenarios.md",
        "heading": "## Observable outcomes",
        "test": test_id,
    }


def _write_module(*, repo_root: Path, rel_path: str, body: str) -> None:
    """Author a module under `repo_root` at `rel_path`."""
    target = repo_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(body, encoding="utf-8")


def _scan(
    *, repo_root: Path, entries: list[dict[str, object]]
) -> IOResult[list[UnresolvedNodeId], NodeIdUnreadable]:
    return unresolvable_node_ids(repo_root=repo_root, entries=entries)


def _violations(*, repo_root: Path, entries: list[dict[str, object]]) -> list[UnresolvedNodeId]:
    """The direction-5 violations, unwrapped off the railway.

    The `IOSuccess` assertion is not ceremony: it makes each caller's standing
    assumption — that its fixture is READABLE — a checked one, so a case that
    accidentally lands on the failure track fails naming the track rather than
    raising out of an unwrap.
    """
    scanned = _scan(repo_root=repo_root, entries=entries)
    assert isinstance(scanned, IOSuccess), f"expected a resolvable scan; got {scanned!r}"
    return unsafe_perform_io(scanned.unwrap())


# ---------------------------------------------------------------------------
# The two sabotage controls — the POSITIVE half of the acceptance.
# ---------------------------------------------------------------------------


def test_an_absent_module_is_a_violation(*, tmp_path: Path) -> None:
    """A node id naming a module that does not exist FIRES, naming the path it sought.

    Sabotage control 2 of `livespec-dev-tooling-8t0i`: a wholly nonexistent
    module under `tests/integration` exited 0, silently, before this landed.
    """
    entries = [_row(test_id=_NODE_ID)]

    violations = _violations(repo_root=tmp_path, entries=entries)

    assert len(violations) == 1
    assert violations[0].reason == "module-file-absent"
    assert violations[0].entry == entries[0]
    assert _MODULE_REL in violations[0].detail


def test_a_module_without_the_function_is_a_violation(*, tmp_path: Path) -> None:
    """An EXISTING module that defines no such function FIRES.

    Sabotage control 1: the harder half, because the module resolves and only
    the trailing segment is a lie — the shape a pre-mapped row takes when its
    author copied a real module path beside a test that was never written.
    """
    _write_module(repo_root=tmp_path, rel_path=_MODULE_REL, body=_DEFINES_SOMETHING_ELSE)

    violations = _violations(repo_root=tmp_path, entries=[_row(test_id=_NODE_ID)])

    assert len(violations) == 1
    assert violations[0].reason == "test-function-absent"
    assert "test_observable" in violations[0].detail


def test_a_fully_resolvable_row_is_no_violation(*, tmp_path: Path) -> None:
    """The NEGATIVE control: a registry whose every mapped id resolves passes."""
    _write_module(repo_root=tmp_path, rel_path=_MODULE_REL, body=_DEFINES_IT)

    assert _violations(repo_root=tmp_path, entries=[_row(test_id=_NODE_ID)]) == []


# ---------------------------------------------------------------------------
# Node-id spellings — both occur in governed registries.
# ---------------------------------------------------------------------------


def test_a_pytest_path_node_id_resolves(*, tmp_path: Path) -> None:
    """The pytest-native `path::name` spelling resolves like the dotted one."""
    _write_module(repo_root=tmp_path, rel_path=_MODULE_REL, body=_DEFINES_IT)

    entries = [_row(test_id=f"{_MODULE_REL}::test_observable")]

    assert _violations(repo_root=tmp_path, entries=entries) == []


def test_a_pytest_path_node_id_with_a_class_segment_resolves(*, tmp_path: Path) -> None:
    """`path::Class::method` resolves on the trailing segment, the method."""
    _write_module(
        repo_root=tmp_path,
        rel_path=_MODULE_REL,
        body="class TestFlow:\n    def test_observable(self) -> None:\n        assert True\n",
    )

    entries = [_row(test_id=f"{_MODULE_REL}::TestFlow::test_observable")]

    assert _violations(repo_root=tmp_path, entries=entries) == []


def test_a_pytest_path_node_id_naming_no_file_is_a_violation(*, tmp_path: Path) -> None:
    """A `path::name` id whose file is absent fires the same module verdict."""
    entries = [_row(test_id=f"{_MODULE_REL}::test_observable")]

    violations = _violations(repo_root=tmp_path, entries=entries)

    assert len(violations) == 1
    assert violations[0].reason == "module-file-absent"


def test_a_pytest_separator_with_no_trailing_name_is_a_violation(*, tmp_path: Path) -> None:
    """`path::` names no test at all — an answer by inspection, with no I/O."""
    violations = _violations(repo_root=tmp_path, entries=[_row(test_id=f"{_MODULE_REL}::")])

    assert len(violations) == 1
    assert violations[0].reason == "node-id-not-a-test-path"


def test_an_undotted_single_token_is_a_violation(*, tmp_path: Path) -> None:
    """A single-token id resolves to no module by inspection — likewise an answer."""
    violations = _violations(repo_root=tmp_path, entries=[_row(test_id="weirdsingletoken")])

    assert len(violations) == 1
    assert violations[0].reason == "node-id-not-a-test-path"
    assert "weirdsingletoken" in violations[0].detail


def test_a_parametrised_node_id_resolves_to_its_function(*, tmp_path: Path) -> None:
    """`...test_observable[case-1]` names the same `def` — the label is not part of it."""
    _write_module(repo_root=tmp_path, rel_path=_MODULE_REL, body=_DEFINES_IT)

    entries = [_row(test_id=f"{_NODE_ID}[case-1]")]

    assert _violations(repo_root=tmp_path, entries=entries) == []


def test_a_class_qualified_dotted_node_id_resolves(*, tmp_path: Path) -> None:
    """`tests.custom.test_flow.TestFlow.test_observable` names `tests/custom/test_flow.py`.

    Bound 1 of the module docstring, and the reason the module half searches
    the prefix chain longest-first instead of assuming the module is
    everything-but-the-last-segment: the naive split would seek
    `tests/custom/test_flow/TestFlow.py` and convict a correctly-spelled row.
    """
    _write_module(
        repo_root=tmp_path,
        rel_path=_MODULE_REL,
        body="class TestFlow:\n    def test_observable(self) -> None:\n        assert True\n",
    )

    entries = [_row(test_id="tests.custom.test_flow.TestFlow.test_observable")]

    assert _violations(repo_root=tmp_path, entries=entries) == []


def test_an_async_test_function_resolves(*, tmp_path: Path) -> None:
    """An `async def` test is a definition too."""
    _write_module(
        repo_root=tmp_path,
        rel_path=_MODULE_REL,
        body="async def test_observable() -> None:\n    assert True\n",
    )

    assert _violations(repo_root=tmp_path, entries=[_row(test_id=_NODE_ID)]) == []


# ---------------------------------------------------------------------------
# Rows this direction deliberately does not judge.
# ---------------------------------------------------------------------------


def test_a_todo_row_is_not_resolved(*, tmp_path: Path) -> None:
    """`test: "TODO"` is the registry's machine-readable placeholder — direction 3 owns it."""
    assert _violations(repo_root=tmp_path, entries=[_row(test_id="TODO")]) == []


def test_a_non_string_test_field_is_skipped(*, tmp_path: Path) -> None:
    """A non-string `test` carries no node id to resolve."""
    assert _violations(repo_root=tmp_path, entries=[_row(test_id=42)]) == []


def test_a_row_without_the_full_triple_is_skipped(*, tmp_path: Path) -> None:
    """A malformed row the coverage diff already skips must not acquire a second verdict."""
    entries: list[dict[str, object]] = [
        {"spec_root": "SPECIFICATION", "spec_file": "spec.md", "heading": 42, "test": _NODE_ID}
    ]

    assert _violations(repo_root=tmp_path, entries=entries) == []


# ---------------------------------------------------------------------------
# The failure track — a non-read is never an existence verdict.
# ---------------------------------------------------------------------------


def test_an_unreadable_module_is_unresolved(*, tmp_path: Path) -> None:
    """A DIRECTORY where the mapped module belongs is a non-read, and says so.

    `chmod 000` proves nothing — this suite runs as root — so unreadability is
    spelled as a directory where a file is expected. The resulting
    `IsADirectoryError` is an `OSError` that is NOT a `FileNotFoundError`,
    which matters precisely because absence is the ANSWER arm above.
    """
    (tmp_path / _MODULE_REL).mkdir(parents=True)

    scanned = _scan(repo_root=tmp_path, entries=[_row(test_id=_NODE_ID)])

    assert isinstance(scanned, IOFailure)
    unreadable = unsafe_perform_io(scanned.failure())
    assert unreadable.reason == "test-file-unreadable"
    assert _MODULE_REL in unreadable.detail


def test_an_unparseable_module_is_unresolved(*, tmp_path: Path) -> None:
    """A mapped module that does not compile cannot answer whether it defines the test."""
    _write_module(repo_root=tmp_path, rel_path=_MODULE_REL, body=_UNPARSEABLE)

    scanned = _scan(repo_root=tmp_path, entries=[_row(test_id=_NODE_ID)])

    assert isinstance(scanned, IOFailure)
    unreadable = unsafe_perform_io(scanned.failure())
    assert unreadable.reason == "test-file-unparseable"
    assert _NODE_ID in unreadable.detail


def test_an_embedded_nul_is_unresolved(*, tmp_path: Path) -> None:
    """`ast.parse` raises `ValueError`, not `SyntaxError`, for an embedded NUL.

    It rides with `SyntaxError` because both mean the same thing here — the
    source exists and cannot be turned into a tree — and catching only
    `SyntaxError` would let a `ValueError` escape a function whose annotation
    promises an `IOResult`.
    """
    _write_module(
        repo_root=tmp_path,
        rel_path=_MODULE_REL,
        body="def test_observable() -> None:\n    x = '\x00'\n",
    )

    scanned = _scan(repo_root=tmp_path, entries=[_row(test_id=_NODE_ID)])

    assert isinstance(scanned, IOFailure)
    assert unsafe_perform_io(scanned.failure()).reason == "test-file-unparseable"


def test_one_unresolvable_row_takes_the_whole_scan(*, tmp_path: Path) -> None:
    """A partial violation list must not be readable as a complete one.

    The row ahead of the unreadable one IS a violation, and the scan still
    returns the failure track rather than a list that looks finished — the same
    ruling `scenario_tier_violations` takes.
    """
    (tmp_path / _MODULE_REL).mkdir(parents=True)
    entries = [_row(test_id="tests.other.test_absent.test_gone"), _row(test_id=_NODE_ID)]

    scanned = _scan(repo_root=tmp_path, entries=entries)

    assert isinstance(scanned, IOFailure)
    assert unsafe_perform_io(scanned.failure()).reason == "test-file-unreadable"
