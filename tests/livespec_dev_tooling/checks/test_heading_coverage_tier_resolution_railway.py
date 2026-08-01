"""`scenario_tier_violations` puts its unresolvable reads on the `IOResult` railway.

Row 2 of the `OPEN` table in `plan/rop-railway-enforcement/qndn-75-triage.md`,
and the second unblocked offender of `livespec-dev-tooling-8o8e.9`. The triage
pairs it with `is_docs_only_change` under ONE question — *is a deliberate
fail-closed collapse of an inhabited failure track a violation, or a sanctioned
design?* — and this file pins the answer for the second half.

`_node_id_resolves_with_marker` caught `(OSError, SyntaxError)` and returned
`False`, documented as "no marker found so the prefix path governs". That fused
"this test carries no integration-tier marker" with "I could not read the file
to find out", and the parent then reported *"scenario heading mapped to
unit-tier test"* — a definitive tier verdict about a test the check never read.

The load-bearing pair is
`test_an_unreadable_test_file_is_unresolvable` beside
`test_an_absent_test_file_is_an_ordinary_violation`: both produced the SAME
violation entry before, and they are on OPPOSITE tracks now. The second is the
ruling — a node id naming no file has no marker because there is no test, and
that is a verdict the read produced.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOResult, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._heading_coverage_tier_resolution import (
    DEFAULT_SCENARIO_TIERS,
    TierUnresolvable,
    scenario_tier_violations,
)

if TYPE_CHECKING:
    from pathlib import Path

_NODE_ID = "tests.custom.test_flow.test_observable"

_MARKED = textwrap.dedent(
    """\
    import pytest


    @pytest.mark.integration
    def test_observable() -> None:
        assert True
    """
)

_UNMARKED = textwrap.dedent(
    """\
    def test_observable() -> None:
        assert True
    """
)

_UNPARSEABLE = "def test_observable( -> None:\n"


def _entries() -> list[dict[str, object]]:
    return [{"spec_file": "scenarios.md", "test": _NODE_ID}]


def _write_mapped_test(*, repo_root: Path, body: str) -> Path:
    """Author `tests/custom/test_flow.py` under `repo_root` — what `_NODE_ID` resolves to."""
    target = repo_root / "tests" / "custom" / "test_flow.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(body, encoding="utf-8")
    return target


def _scan(
    *, repo_root: Path, entries: list[dict[str, object]] | None = None
) -> IOResult[list[dict[str, object]], TierUnresolvable]:
    """Run the direction-4 scan over `entries`, defaulting to the one mapped entry."""
    return scenario_tier_violations(
        repo_root=repo_root,
        entries=_entries() if entries is None else entries,
        tiers=DEFAULT_SCENARIO_TIERS,
    )


def test_a_marked_test_answers_no_violations(*, tmp_path: Path) -> None:
    """The compliant path survives the conversion: `IOSuccess([])`."""
    _write_mapped_test(repo_root=tmp_path, body=_MARKED)

    scanned = _scan(repo_root=tmp_path)

    assert isinstance(scanned, IOSuccess)
    assert unsafe_perform_io(scanned.unwrap()) == []


def test_an_unmarked_test_answers_a_violation(*, tmp_path: Path) -> None:
    """A resolved test with no tier marker is a VERDICT, and stays on the success track."""
    _write_mapped_test(repo_root=tmp_path, body=_UNMARKED)

    scanned = _scan(repo_root=tmp_path)

    assert isinstance(scanned, IOSuccess)
    assert unsafe_perform_io(scanned.unwrap()) == _entries()


def test_an_absent_test_file_is_an_ordinary_violation(*, tmp_path: Path) -> None:
    """A node id naming no file has no marker — an ANSWER, not a failure.

    This is the ruling the unit turns on, and the contrast with
    `test_an_unreadable_test_file_is_unresolvable` is the whole point: both
    produced this same entry before the conversion.
    """
    scanned = _scan(repo_root=tmp_path)

    assert isinstance(scanned, IOSuccess)
    assert unsafe_perform_io(scanned.unwrap()) == _entries()


def test_an_undotted_node_id_is_an_ordinary_violation(*, tmp_path: Path) -> None:
    """A node id with no dot resolves to no module by inspection — no I/O, an answer."""
    entries: list[dict[str, object]] = [{"spec_file": "scenarios.md", "test": "notdotted"}]

    scanned = _scan(repo_root=tmp_path, entries=entries)

    assert isinstance(scanned, IOSuccess)
    assert unsafe_perform_io(scanned.unwrap()) == entries


def test_an_unreadable_test_file_is_unresolvable(*, tmp_path: Path) -> None:
    """A DIRECTORY where the mapped module belongs is a non-read, and says so.

    `chmod 000` proves nothing — this suite runs as root — so unreadability is
    spelled as a directory where a file is expected. The resulting
    `IsADirectoryError` is an `OSError` that is NOT a `FileNotFoundError`,
    which matters precisely because absence is the ANSWER arm above.
    """
    (tmp_path / "tests" / "custom" / "test_flow.py").mkdir(parents=True)

    scanned = _scan(repo_root=tmp_path)

    assert isinstance(scanned, IOFailure)
    unresolvable = unsafe_perform_io(scanned.failure())
    assert unresolvable.reason == "test-file-unreadable"
    assert _NODE_ID in unresolvable.detail


def test_a_non_directory_path_component_is_unresolvable(*, tmp_path: Path) -> None:
    """The mirror `OSError`: a FILE where the mapped module's package belongs.

    `tests/custom` as a regular file makes `tests/custom/test_flow.py` raise
    `NotADirectoryError` — again an `OSError` that is not `FileNotFoundError`,
    and again a checkout defect rather than a statement about the test's tier.
    """
    (tmp_path / "tests").mkdir()
    _ = (tmp_path / "tests" / "custom").write_text("", encoding="utf-8")

    scanned = _scan(repo_root=tmp_path)

    assert isinstance(scanned, IOFailure)
    unresolvable = unsafe_perform_io(scanned.failure())
    assert unresolvable.reason == "test-file-unreadable"


def test_an_unparseable_test_file_is_unresolvable(*, tmp_path: Path) -> None:
    """A mapped test that does not compile is named as such, not as a unit-tier test."""
    _write_mapped_test(repo_root=tmp_path, body=_UNPARSEABLE)

    scanned = _scan(repo_root=tmp_path)

    assert isinstance(scanned, IOFailure)
    unresolvable = unsafe_perform_io(scanned.failure())
    assert unresolvable.reason == "test-file-unparseable"
    assert _NODE_ID in unresolvable.detail


def test_an_embedded_nul_is_unresolvable(*, tmp_path: Path) -> None:
    """`ast.parse` raises `ValueError`, not `SyntaxError`, for an embedded NUL.

    It rides with `SyntaxError` because both mean the same thing to this
    module — the source exists and cannot be turned into a tree — and catching
    only `SyntaxError` would let a `ValueError` escape a function whose
    annotation promises an `IOResult`.
    """
    _write_mapped_test(repo_root=tmp_path, body="def test_observable() -> None:\n    x = '\x00'\n")

    scanned = _scan(repo_root=tmp_path)

    assert isinstance(scanned, IOFailure)
    unresolvable = unsafe_perform_io(scanned.failure())
    assert unresolvable.reason == "test-file-unparseable"


def test_one_unresolvable_entry_takes_the_whole_scan(*, tmp_path: Path) -> None:
    """A partial violation list must not be readable as a complete one.

    The entry ahead of the unresolvable one IS a violation, and the scan still
    returns the failure track rather than a list that looks finished. The
    parent's other three directions are computed independently and report in
    the same run, which is where the both-kinds-in-one-run contract lives.
    """
    _ = (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "custom" / "test_flow.py").mkdir(parents=True)
    entries: list[dict[str, object]] = [
        {"spec_file": "scenarios.md", "test": "tests.unit.test_pure.test_thing"},
        {"spec_file": "scenarios.md", "test": _NODE_ID},
    ]

    scanned = _scan(repo_root=tmp_path, entries=entries)

    assert isinstance(scanned, IOFailure)
    assert unsafe_perform_io(scanned.failure()).reason == "test-file-unreadable"
