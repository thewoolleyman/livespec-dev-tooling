"""The dispatch filter's EXCLUDING-vs-NAMED disposition of error findings.

`SPECIFICATION/contracts.md` section "Pin-currency severity policy" (v093) and
`SPECIFICATION/scenarios.md` section "Scenario: a member with an unparseable pin
file or a non-pin error row is still excluded from the release dispatch": an
error finding for a member in the dispatch sibling set excludes that member,
EXCEPT a finding of either ratified staleness class. A can't-PARSE pin finding
still excludes, "because the bump rewrite cannot be applied to a pin file that
does not parse".

So the disposition is NOT derivable from the row id: `compat-pin-currency` can
fail for staleness (non-excluding) or for a can't-parse (excluding), and the two
must part ways. The carrier is therefore the FINDING's own class —
`_row_finding.PIN_STALENESS_FINDING_CLASS` — which the lane re-cuts per member
into the verdict artifact's `non_excluding_rows`, and the filter reads from
there. These tests pin both halves: the classification the finding carries, and
the partition the filter derives from it.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from returns.result import Success
from test_rows_files import make_context

from livespec_dev_tooling.cross_repo.pin_autodiscovery import PinFileUnparseable
from livespec_dev_tooling.fleet._context import FleetContext, FleetMember
from livespec_dev_tooling.fleet._pin_walk_failure import walk_failure_outcome
from livespec_dev_tooling.fleet.dispatch_matrix_filter import filter_siblings, main

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")


def _row_finding_module() -> object:
    """The finding-classification module, asserted present before it is imported.

    The module path is asserted rather than imported at module scope on
    purpose: a top-level import of a module that does not exist yet dies at
    COLLECTION, which proves only unimportability. This fails on a genuine
    assertion instead.
    """
    module_path = (
        Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "fleet" / "_row_finding.py"
    )
    assert module_path.is_file(), f"the finding-classification module is absent: {module_path}"
    return importlib.import_module("livespec_dev_tooling.fleet._row_finding")


def _preflight_context() -> FleetContext:
    """A filter-consuming preflight context — the one lane where findings escalate.

    An empty canned table, because the can't-parse rendering below reads
    nothing: the walk already failed, and that failure is handed in. Built
    through the shared `make_context` rather than a local runner closure so
    this file declares no seam of its own.
    """
    return replace(make_context(table={}), filter_consuming_preflight=True)


def _verdict(
    *,
    member: str,
    failing_rows: list[str],
    non_excluding_rows: list[str] | None = None,
) -> dict[str, object]:
    return {
        "member": member,
        "conformant": not failing_rows,
        "failing_rows": failing_rows,
        "non_excluding_rows": [] if non_excluding_rows is None else non_excluding_rows,
    }


def test_pin_staleness_finding_carries_the_non_excluding_class() -> None:
    module = _row_finding_module()
    staleness_class = cast("str", module.PIN_STALENESS_FINDING_CLASS)
    finding = cast(
        "object",
        module.pin_staleness_finding(message="widget: pin stale", severity="error"),
    )
    assert cast("str", finding.finding_class) == staleness_class  # pyright: ignore[reportAttributeAccessIssue]
    assert cast("str", finding.severity) == "error"  # pyright: ignore[reportAttributeAccessIssue]
    # Severity and disposition are ORTHOGONAL: the staleness class keeps error
    # severity and stops excluding. A plain finding carries no class at all,
    # which is what makes "excluding" the default for every other row.
    plain = cast("object", module.RowFinding(message="widget: something else"))
    assert cast("str", plain.finding_class) == ""  # pyright: ignore[reportAttributeAccessIssue]


def test_cant_parse_pin_finding_is_not_classified_as_staleness() -> None:
    module = _row_finding_module()
    staleness_class = cast("str", module.PIN_STALENESS_FINDING_CLASS)
    outcome = walk_failure_outcome(
        ctx=_preflight_context(),
        member=_MEMBER,
        pin_format="livespec_jsonc_compat_pinned",
        failure=PinFileUnparseable(
            pin_walk="livespec_jsonc_compat_pinned",
            file_path=".livespec.jsonc",
            detail="trailing comma",
        ),
    )
    assert cast("str", outcome.severity) == "error"  # pyright: ignore[reportAttributeAccessIssue]
    assert cast("str", outcome.finding_class) != staleness_class  # pyright: ignore[reportAttributeAccessIssue]


def test_a_pin_row_failing_for_cant_parse_still_excludes_its_member() -> None:
    # The row id is a pin-currency row, so an id-keyed filter would retain
    # this member. The verdict's `non_excluding_rows` is empty, which is what
    # a can't-parse finding leaves behind, and the member is excluded.
    result = filter_siblings(
        siblings=[{"name": "alpha"}, {"name": "beta"}],
        verdicts=[
            _verdict(member="alpha", failing_rows=[]),
            _verdict(member="beta", failing_rows=["compat-pin-currency"]),
        ],
    )
    assert isinstance(result, Success), result
    outcome = result.unwrap()
    assert outcome.filtered == ({"name": "alpha"},)
    assert [one.member for one in outcome.excluded] == ["beta"]
    assert outcome.excluded[0].failing_rows == ("compat-pin-currency",)
    assert outcome.retained == ()


def test_a_non_pin_error_row_still_excludes_its_member() -> None:
    result = filter_siblings(
        siblings=[{"name": "beta"}],
        verdicts=[_verdict(member="beta", failing_rows=["app-installation"])],
    )
    assert isinstance(result, Success), result
    outcome = result.unwrap()
    assert outcome.filtered == ()
    assert [one.member for one in outcome.excluded] == ["beta"]
    assert outcome.retained == ()


def test_a_member_whose_only_error_rows_are_non_excluding_is_retained_and_named() -> None:
    result = filter_siblings(
        siblings=[{"name": "alpha"}, {"name": "beta"}],
        verdicts=[
            _verdict(member="alpha", failing_rows=[]),
            _verdict(
                member="beta",
                failing_rows=["compat-pin-currency", "dev-tooling-pin"],
                non_excluding_rows=["compat-pin-currency", "dev-tooling-pin"],
            ),
        ],
    )
    assert isinstance(result, Success), result
    outcome = result.unwrap()
    assert outcome.filtered == ({"name": "alpha"}, {"name": "beta"})
    assert outcome.excluded == ()
    assert [one.member for one in outcome.retained] == ["beta"]
    assert outcome.retained[0].failing_rows == ("compat-pin-currency", "dev-tooling-pin")


def test_one_excluding_row_beside_a_non_excluding_one_still_excludes() -> None:
    # The scenario's "only error findings" is load-bearing: a staleness
    # finding does not shelter a can't-parse finding sitting beside it.
    result = filter_siblings(
        siblings=[{"name": "beta"}],
        verdicts=[
            _verdict(
                member="beta",
                failing_rows=["compat-pin-currency", "uses-pin-currency"],
                non_excluding_rows=["compat-pin-currency"],
            )
        ],
    )
    assert isinstance(result, Success), result
    outcome = result.unwrap()
    assert outcome.filtered == ()
    assert [one.member for one in outcome.excluded] == ["beta"]
    # The summary names EVERY error finding for the member, not just the
    # excluding ones.
    assert outcome.excluded[0].failing_rows == ("compat-pin-currency", "uses-pin-currency")
    assert outcome.retained == ()


def test_a_malformed_non_excluding_rows_value_fails_closed() -> None:
    result = filter_siblings(
        siblings=[{"name": "beta"}],
        verdicts=[
            {
                "member": "beta",
                "conformant": False,
                "failing_rows": ["compat-pin-currency"],
                "non_excluding_rows": "compat-pin-currency",
            }
        ],
    )
    assert not isinstance(result, Success), result
    assert "beta" in result.failure().reason


def test_a_non_string_non_excluding_row_fails_closed() -> None:
    result = filter_siblings(
        siblings=[{"name": "beta"}],
        verdicts=[
            {
                "member": "beta",
                "conformant": False,
                "failing_rows": ["compat-pin-currency"],
                "non_excluding_rows": ["compat-pin-currency", 7],
            }
        ],
    )
    assert not isinstance(result, Success), result
    assert "beta" in result.failure().reason


def _write_inputs(*, tmp_path: Path) -> tuple[Path, Path]:
    """One excluded member and one retained member, as the two input artifacts."""
    verdicts_path = tmp_path / "verdicts.json"
    siblings_path = tmp_path / "siblings.json"
    _ = verdicts_path.write_text(
        json.dumps(
            [
                _verdict(member="alpha", failing_rows=["app-installation"]),
                _verdict(
                    member="beta",
                    failing_rows=["compat-pin-currency"],
                    non_excluding_rows=["compat-pin-currency"],
                ),
            ]
        ),
        encoding="utf-8",
    )
    _ = siblings_path.write_text(
        json.dumps([{"name": "alpha"}, {"name": "beta"}]), encoding="utf-8"
    )
    return verdicts_path, siblings_path


def test_main_names_the_retained_findings_and_dispatches_that_member(tmp_path: Path) -> None:
    verdicts_path, siblings_path = _write_inputs(tmp_path=tmp_path)
    filtered_path = tmp_path / "filtered.json"
    exclusions_path = tmp_path / "exclusions.json"
    retained_path = tmp_path / "retained.json"
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
            "--retained-out",
            str(retained_path),
        ]
    )
    assert exit_code == 0
    # The stale-pin member is DISPATCHED TO: the dispatch is the remedy for
    # its stale pin, so excluding it would remove the cure.
    assert json.loads(filtered_path.read_text(encoding="utf-8")) == [{"name": "beta"}]
    assert json.loads(exclusions_path.read_text(encoding="utf-8")) == [
        {"member": "alpha", "failing_rows": ["app-installation"]}
    ]
    assert json.loads(retained_path.read_text(encoding="utf-8")) == [
        {"member": "beta", "failing_rows": ["compat-pin-currency"]}
    ]


def test_main_still_runs_when_no_retained_output_is_requested(tmp_path: Path) -> None:
    # `--retained-out` is OPTIONAL on purpose: the fan-out workflow that
    # invokes this filter is pinned at a release, so a REQUIRED new flag would
    # make every unbumped caller exit 2 and red the whole fan-out. A caller
    # that asks for no retained artifact still gets the retained member in the
    # dispatch matrix, and still sees it named in the run's annotations.
    verdicts_path, siblings_path = _write_inputs(tmp_path=tmp_path)
    filtered_path = tmp_path / "filtered.json"
    exit_code = main(
        argv=[
            "--verdicts",
            str(verdicts_path),
            "--siblings",
            str(siblings_path),
            "--filtered-out",
            str(filtered_path),
            "--exclusions-out",
            str(tmp_path / "exclusions.json"),
        ]
    )
    assert exit_code == 0
    assert json.loads(filtered_path.read_text(encoding="utf-8")) == [{"name": "beta"}]
    assert not (tmp_path / "retained.json").exists()


def test_main_annotates_every_retained_member_by_name_and_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    verdicts_path, siblings_path = _write_inputs(tmp_path=tmp_path)
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
    assert exit_code == 0
    captured = capsys.readouterr().out
    retained_lines = [line for line in captured.splitlines() if "beta" in line]
    assert retained_lines, captured
    # Named loudly, and named as NOT excluded — the silent-omission hazard
    # cuts both ways: a member kept for a reason must say which findings it
    # was kept despite.
    assert any("compat-pin-currency" in line for line in retained_lines)
    assert any("not excluded" in line.casefold() for line in retained_lines)
