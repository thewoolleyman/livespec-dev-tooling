"""Fail-closed edge coverage for the dispatch-matrix conformance filter."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_dev_tooling.fleet.dispatch_matrix_filter import (
    FilterError,
    filter_siblings,
    main,
)

__all__: list[str] = []


def test_malformed_verdict_entry_is_a_structural_error() -> None:
    outcome = filter_siblings(
        siblings=[{"name": "alpha"}],
        verdicts=[{"member": 7, "conformant": True, "failing_rows": []}],
    )
    assert isinstance(outcome, FilterError)
    assert "malformed verdict entry" in outcome.reason


def test_non_list_failing_rows_is_a_structural_error() -> None:
    outcome = filter_siblings(
        siblings=[{"name": "alpha"}],
        verdicts=[{"member": "alpha", "conformant": True, "failing_rows": "nope"}],
    )
    assert isinstance(outcome, FilterError)
    assert "malformed failing_rows" in outcome.reason


def test_non_string_failing_row_is_a_structural_error() -> None:
    outcome = filter_siblings(
        siblings=[{"name": "alpha"}],
        verdicts=[{"member": "alpha", "conformant": False, "failing_rows": [3]}],
    )
    assert isinstance(outcome, FilterError)
    assert "non-string failing row" in outcome.reason


def test_malformed_sibling_entry_is_a_structural_error() -> None:
    outcome = filter_siblings(
        siblings=[{"nombre": "alpha"}],
        verdicts=[{"member": "alpha", "conformant": True, "failing_rows": []}],
    )
    assert isinstance(outcome, FilterError)
    assert "malformed sibling entry" in outcome.reason


def _write_inputs(*, tmp_path: Path, verdicts_text: str, siblings_text: str) -> list[str]:
    verdicts_path = tmp_path / "verdicts.json"
    siblings_path = tmp_path / "siblings.json"
    _ = verdicts_path.write_text(verdicts_text, encoding="utf-8")
    _ = siblings_path.write_text(siblings_text, encoding="utf-8")
    return [
        "--verdicts",
        str(verdicts_path),
        "--siblings",
        str(siblings_path),
        "--filtered-out",
        str(tmp_path / "filtered.json"),
        "--exclusions-out",
        str(tmp_path / "exclusions.json"),
    ]


def test_main_fails_closed_on_non_array_json(tmp_path: Path) -> None:
    argv = _write_inputs(
        tmp_path=tmp_path,
        verdicts_text=json.dumps({"member": "alpha"}),
        siblings_text=json.dumps([{"name": "alpha"}]),
    )
    assert main(argv=argv) == 1


def test_main_fails_closed_on_non_object_array_entry(tmp_path: Path) -> None:
    argv = _write_inputs(
        tmp_path=tmp_path,
        verdicts_text=json.dumps(["not-an-object"]),
        siblings_text=json.dumps([{"name": "alpha"}]),
    )
    assert main(argv=argv) == 1


def test_main_fails_closed_on_filter_error(tmp_path: Path) -> None:
    argv = _write_inputs(
        tmp_path=tmp_path,
        verdicts_text=json.dumps([]),
        siblings_text=json.dumps([{"name": "ghost"}]),
    )
    assert main(argv=argv) == 1
