"""Tests for fleet enforcement of the full canonical check aggregate."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess
from test_rows_files import _MEMBER, make_context, tree_table

from livespec_dev_tooling.canonical_checks import ChecksPackageUnreadable
from livespec_dev_tooling.fleet._context import FleetContext, GhResult, RowFinding, RowPass, RowSkip

__all__: list[str] = []


_MODULE_NAME = "livespec_dev_tooling.fleet._rows_canonical_check_slugs"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling/fleet/_rows_canonical_check_slugs.py"
)
_JUSTFILE_PATH = "justfile"


def _contents_args(*, path: str) -> tuple[str, ...]:
    """The canned `gh` argv for one raw master-file read."""
    return (
        "api",
        f"repos/acme/{_MEMBER.repo}/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _justfile(*, targets: tuple[str, ...]) -> str:
    """A bare `check:` recipe with an enumerable aggregate target array."""
    listed = "\n".join(f"        {target}" for target in targets)
    return (
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    targets=(\n"
        f"{listed}\n"
        "    )\n"
        '    for target in "${targets[@]}"; do just "${target}"; done\n'
    )


def _context_with_targets(*, targets: tuple[str, ...]) -> FleetContext:
    """A member master tree whose aggregate contains `targets`."""
    table = tree_table(paths=[_JUSTFILE_PATH])
    table[_contents_args(path=_JUSTFILE_PATH)] = GhResult(
        returncode=0,
        stdout=_justfile(targets=targets),
        stderr="",
    )
    return make_context(table=table)


def _rows_module():
    """Import the new row only after its Red assertion has run."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def test_member_missing_a_canonical_slug_is_an_error_and_complete_aggregate_passes(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fleet row names the member and every omitted canonical slug."""
    rows = _rows_module()
    canonical = ("check-alpha", "check-beta")
    monkeypatch.setattr(rows, "canonical_check_slugs", lambda: IOSuccess(canonical))

    missing = rows.assert_canonical_check_slugs_wired(
        ctx=_context_with_targets(targets=("check-alpha",)), member=_MEMBER
    )

    assert isinstance(missing, RowFinding)
    assert missing.severity == "error"
    assert _MEMBER.repo in missing.message
    assert "check-beta" in missing.message
    assert (
        rows.assert_canonical_check_slugs_wired(
            ctx=_context_with_targets(targets=canonical), member=_MEMBER
        )
        == RowPass()
    )


def test_row_skips_unreadable_member_tree_and_aggregate() -> None:
    """A missing source of aggregate targets stays unknown rather than a conviction."""
    rows = _rows_module()

    unreadable_tree = rows.assert_canonical_check_slugs_wired(
        ctx=make_context(table={}), member=_MEMBER
    )
    assert isinstance(unreadable_tree, RowSkip)
    assert "tree unreadable" in unreadable_tree.reason

    aggregate_unreadable = rows.assert_canonical_check_slugs_wired(
        ctx=make_context(table=tree_table(paths=[_JUSTFILE_PATH])), member=_MEMBER
    )
    assert isinstance(aggregate_unreadable, RowSkip)
    assert _JUSTFILE_PATH in aggregate_unreadable.reason


def test_unreadable_canonical_inventory_is_an_error(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """The fleet check fails closed when the canonical set cannot be established."""
    rows = _rows_module()
    unreadable = ChecksPackageUnreadable(package_path=Path("checks"), reason="fixture")
    monkeypatch.setattr(rows, "canonical_check_slugs", lambda: IOFailure(unreadable))

    outcome = rows.assert_canonical_check_slugs_wired(
        ctx=_context_with_targets(targets=("check-alpha",)), member=_MEMBER
    )

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "canonical check inventory unreadable" in outcome.message


def test_row_establishes_its_vendor_path_when_imported_first(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row's vendored result imports do not depend on an earlier fleet import."""
    _ = _rows_module()
    vendor_path = str(Path(__file__).resolve().parents[3] / "livespec_dev_tooling/_vendor")

    with monkeypatch.context() as isolated:
        isolated.setattr(sys, "path", [entry for entry in sys.path if entry != vendor_path])
        isolated.delitem(sys.modules, _MODULE_NAME)
        reloaded = importlib.import_module(_MODULE_NAME)

        assert callable(reloaded.assert_canonical_check_slugs_wired)
        assert vendor_path in sys.path
