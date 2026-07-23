"""Tests for the release-dispatch sibling-matrix conformance filter."""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from livespec_dev_tooling.fleet.dispatch_matrix_filter import (
    FilterError,
    FilterOutcome,
    filter_siblings,
    main,
)

__all__: list[str] = []


def _verdict(*, member: str, failing_rows: list[str]) -> dict[str, object]:
    return {
        "member": member,
        "conformant": not failing_rows,
        "failing_rows": failing_rows,
    }


def test_all_conformant_passes_every_sibling_through_in_order() -> None:
    siblings = [{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}]
    verdicts = [
        _verdict(member="alpha", failing_rows=[]),
        _verdict(member="beta", failing_rows=[]),
        _verdict(member="gamma", failing_rows=[]),
    ]
    outcome = filter_siblings(siblings=siblings, verdicts=verdicts)
    assert isinstance(outcome, FilterOutcome)
    assert outcome.filtered == ({"name": "alpha"}, {"name": "beta"}, {"name": "gamma"})
    assert outcome.excluded == ()


def test_non_conformant_sibling_is_excluded_with_its_failing_rows() -> None:
    siblings = [{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}]
    verdicts = [
        _verdict(member="alpha", failing_rows=[]),
        _verdict(member="beta", failing_rows=["app-installation", "merge-settings"]),
        _verdict(member="gamma", failing_rows=[]),
    ]
    outcome = filter_siblings(siblings=siblings, verdicts=verdicts)
    assert isinstance(outcome, FilterOutcome)
    assert outcome.filtered == ({"name": "alpha"}, {"name": "gamma"})
    assert len(outcome.excluded) == 1
    exclusion = outcome.excluded[0]
    assert exclusion.member == "beta"
    assert exclusion.failing_rows == ("app-installation", "merge-settings")


def test_sibling_without_a_verdict_entry_is_a_structural_error() -> None:
    siblings = [{"name": "alpha"}, {"name": "ghost"}]
    verdicts = [_verdict(member="alpha", failing_rows=[])]
    outcome = filter_siblings(siblings=siblings, verdicts=verdicts)
    assert isinstance(outcome, FilterError)
    assert "ghost" in outcome.reason


def test_extra_verdict_members_not_in_the_sibling_set_are_ignored() -> None:
    # The verdict artifact covers EVERY manifest member; the sibling set
    # excludes the publishing repo, so a surplus verdict is normal.
    siblings = [{"name": "alpha"}]
    verdicts = [
        _verdict(member="alpha", failing_rows=[]),
        _verdict(member="publisher", failing_rows=[]),
    ]
    outcome = filter_siblings(siblings=siblings, verdicts=verdicts)
    assert isinstance(outcome, FilterOutcome)
    assert outcome.filtered == ({"name": "alpha"},)


@settings(deadline=None)
@given(
    names=st.lists(
        st.text(alphabet="abcdefghij-", min_size=1, max_size=12),
        min_size=0,
        max_size=8,
        unique=True,
    ),
    bad=st.sets(st.integers(min_value=0, max_value=7)),
)
def test_filtered_plus_excluded_partition_the_sibling_set(names: list[str], bad: set[int]) -> None:
    siblings = [{"name": name} for name in names]
    verdicts = [
        _verdict(
            member=name,
            failing_rows=["row-x"] if index in bad else [],
        )
        for index, name in enumerate(names)
    ]
    outcome = filter_siblings(siblings=siblings, verdicts=verdicts)
    assert isinstance(outcome, FilterOutcome)
    filtered_names = [entry["name"] for entry in outcome.filtered]
    excluded_names = [exclusion.member for exclusion in outcome.excluded]
    assert sorted(filtered_names + excluded_names) == sorted(names)
    assert not set(filtered_names) & set(excluded_names)
    # Order of the surviving matrix is the discovery order.
    assert filtered_names == [name for name in names if name not in excluded_names]


def test_main_writes_filtered_and_exclusions_and_exits_zero(tmp_path: Path) -> None:
    verdicts_path = tmp_path / "verdicts.json"
    siblings_path = tmp_path / "siblings.json"
    filtered_path = tmp_path / "filtered.json"
    exclusions_path = tmp_path / "exclusions.json"
    _ = verdicts_path.write_text(
        json.dumps(
            [
                _verdict(member="alpha", failing_rows=[]),
                _verdict(member="beta", failing_rows=["app-installation"]),
            ]
        ),
        encoding="utf-8",
    )
    _ = siblings_path.write_text(
        json.dumps([{"name": "alpha"}, {"name": "beta"}]), encoding="utf-8"
    )
    exit_code = main(
        argv=[
            "--verdicts",
            str(verdicts_path),
            "--siblings",
            str(siblings_path),
            "--filtered-out",
            str(filtered_path),
            "--exclusions-out",
            str(exclusions_path),
        ]
    )
    assert exit_code == 0
    assert json.loads(filtered_path.read_text(encoding="utf-8")) == [{"name": "alpha"}]
    exclusions = json.loads(exclusions_path.read_text(encoding="utf-8"))
    assert exclusions == [{"member": "beta", "failing_rows": ["app-installation"]}]


def test_main_fails_closed_on_missing_verdicts_artifact(tmp_path: Path) -> None:
    siblings_path = tmp_path / "siblings.json"
    _ = siblings_path.write_text(json.dumps([{"name": "alpha"}]), encoding="utf-8")
    exit_code = main(
        argv=[
            "--verdicts",
            str(tmp_path / "absent.json"),
            "--siblings",
            str(siblings_path),
            "--filtered-out",
            str(tmp_path / "filtered.json"),
            "--exclusions-out",
            str(tmp_path / "exclusions.json"),
        ]
    )
    assert exit_code == 1


def test_main_fails_closed_on_unparseable_verdicts(tmp_path: Path) -> None:
    verdicts_path = tmp_path / "verdicts.json"
    siblings_path = tmp_path / "siblings.json"
    _ = verdicts_path.write_text("not json", encoding="utf-8")
    _ = siblings_path.write_text(json.dumps([{"name": "alpha"}]), encoding="utf-8")
    exit_code = main(
        argv=[
            "--verdicts",
            str(verdicts_path),
            "--siblings",
            str(siblings_path),
            "--filtered-out",
            str(tmp_path / "filtered.json"),
            "--exclusions-out",
            str(tmp_path / "exclusions.json"),
        ]
    )
    assert exit_code == 1
