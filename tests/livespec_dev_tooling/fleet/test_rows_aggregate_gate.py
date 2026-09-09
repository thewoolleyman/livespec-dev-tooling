"""Tests for `livespec_dev_tooling/fleet/_rows_aggregate_gate.py`.

The `aggregate-gate-wired` row across its full outcome lattice — a member
wiring both canonical meta-gates passes (the CONTROL the item demands: a
fully-wired member must not be reported), a member omitting either is
reported by name, the inventory shape and the justfile shape are both read
and the precedence between them is proven both ways, every can't-read shape
skips, and a manifest ADOPTER is never swept at all — through the
canned-response `FleetContext` the sibling row tests share (no network, no
real `gh`).

Every skip case is paired with the finding it would otherwise have been, so
no test here can pass by the row simply never firing.
"""

from __future__ import annotations

import pytest
from test_fleet_conformance import RecordingLog
from test_rows_files import _MEMBER, make_context, tree_table

from livespec_dev_tooling.fleet import _lanes
from livespec_dev_tooling.fleet._context import (
    FleetMember,
    GhResult,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._contract_classes import DEV_TOOLING_PIN_CLASSES
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS, rows_for
from livespec_dev_tooling.fleet._lanes import run_member_rows
from livespec_dev_tooling.fleet._rows_aggregate_gate import (
    AGGREGATE_GATE_SLUGS,
    CHECK_TARGETS_INVENTORY,
    JUSTFILE_PATH,
    assert_aggregate_gate_wired,
)
from livespec_dev_tooling.fleet.contract import parse_manifest

__all__: list[str] = []


_ROW_ID = "aggregate-gate-wired"
_AGGREGATE_SLUG = "check-aggregate-completeness"
_CI_MATRIX_SLUG = "check-ci-matrix-completeness"
_WIRED = (_AGGREGATE_SLUG, _CI_MATRIX_SLUG, "check-lint")


def _contents_args(*, repo: str, path: str) -> tuple[str, ...]:
    """The canned `gh` argv for a raw contents read of `repo`'s `path`."""
    return (
        "api",
        f"repos/acme/{repo}/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _justfile(*, targets: tuple[str, ...]) -> str:
    """A justfile whose bare `check:` recipe encloses `targets` in `targets=(...)`."""
    listed = "\n".join(f"        {target}" for target in targets)
    return (
        "check:\n"
        "    #!/usr/bin/env bash\n"
        "    set -uo pipefail\n"
        "    targets=(\n"
        f"{listed}\n"
        "    )\n"
        '    for target in "${targets[@]}"; do just "${target}"; done\n'
        "\n"
        "check-lint:\n"
        "    uv run ruff check .\n"
    )


def _inventory(*, targets: tuple[str, ...]) -> str:
    """A `check-targets.txt` inventory, with the comment and blank lines it may carry."""
    listed = "\n".join(targets)
    return f"# the aggregate's canonical targets\n\n{listed}\n"


def _table(
    *,
    repo: str = "widget",
    files: dict[str, str] | None = None,
    paths: list[str] | None = None,
    truncated: bool = False,
) -> dict[tuple[str, ...], GhResult]:
    """A canned table serving `files` from `repo`'s master tree.

    `paths` defaults to exactly the files served, so the tree and the
    contents reads agree; passing it explicitly is how a test makes a file
    LISTED but unreadable.
    """
    served = {} if files is None else files
    table = tree_table(paths=list(served) if paths is None else paths, truncated=truncated)
    for path, text in served.items():
        table[_contents_args(repo=repo, path=path)] = GhResult(returncode=0, stdout=text, stderr="")
    return table


def test_member_wiring_both_gates_in_its_justfile_passes() -> None:
    """The CONTROL: a fully-wired member must not be reported."""
    ctx = make_context(table=_table(files={JUSTFILE_PATH: _justfile(targets=_WIRED)}))
    assert assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER) == RowPass()


def test_member_wiring_both_gates_in_its_target_inventory_passes() -> None:
    """The same control for the OTHER aggregate shape.

    Four of the ten fleet members carry `check-targets.txt` rather than a
    justfile `targets=(...)` array (measured 2026-09-09); a reader that
    understood only the justfile would misreport every one of them.
    """
    ctx = make_context(table=_table(files={CHECK_TARGETS_INVENTORY: _inventory(targets=_WIRED)}))
    assert assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER) == RowPass()


def test_aggregate_omitting_aggregate_completeness_is_reported() -> None:
    ctx = make_context(
        table=_table(files={JUSTFILE_PATH: _justfile(targets=(_CI_MATRIX_SLUG, "check-lint"))})
    )
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert _MEMBER.repo in outcome.message
    assert _AGGREGATE_SLUG in outcome.message
    assert JUSTFILE_PATH in outcome.message
    # WARNING, not error, and deliberately so — the row's docstring records the
    # consequence judgement (one measured offender, owned by another tenant;
    # error severity would exclude it from release dispatch and freeze its pin).
    assert outcome.severity == "warning"


def test_aggregate_omitting_ci_matrix_completeness_is_reported() -> None:
    ctx = make_context(
        table=_table(files={JUSTFILE_PATH: _justfile(targets=(_AGGREGATE_SLUG, "check-lint"))})
    )
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert _CI_MATRIX_SLUG in outcome.message
    assert _AGGREGATE_SLUG not in outcome.message.split("omits", 1)[1]


def test_aggregate_omitting_both_gates_names_both() -> None:
    """The shape measured on `livespec-console-beads-fabro`, 2026-09-09."""
    ctx = make_context(table=_table(files={JUSTFILE_PATH: _justfile(targets=("check-lint",))}))
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert all(slug in outcome.message for slug in AGGREGATE_GATE_SLUGS)


def test_target_inventory_takes_precedence_over_the_justfile_both_ways() -> None:
    """The inventory is the aggregate when it exists — `ci_matrix_completeness`'s order.

    Asserted in BOTH directions so neither half can pass by the reader
    happening to look at the other file: an unwired justfile beside a wired
    inventory passes, and a wired justfile beside an unwired inventory is
    reported AGAINST THE INVENTORY.
    """
    wired_inventory = make_context(
        table=_table(
            files={
                CHECK_TARGETS_INVENTORY: _inventory(targets=_WIRED),
                JUSTFILE_PATH: _justfile(targets=("check-lint",)),
            }
        )
    )
    assert assert_aggregate_gate_wired(ctx=wired_inventory, member=_MEMBER) == RowPass()

    unwired_inventory = make_context(
        table=_table(
            files={
                CHECK_TARGETS_INVENTORY: _inventory(targets=("check-lint",)),
                JUSTFILE_PATH: _justfile(targets=_WIRED),
            }
        )
    )
    outcome = assert_aggregate_gate_wired(ctx=unwired_inventory, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert CHECK_TARGETS_INVENTORY in outcome.message


def test_member_with_no_committed_justfile_skips_naming_the_absent_files() -> None:
    """A member carrying neither aggregate file is a graceful skip, not an error.

    Whether a member owes a justfile at all is the sibling
    `worktree-pack-wired` row's obligation; this row reports only that it
    could not read an aggregate, and names both files it looked for.
    """
    ctx = make_context(table=_table(files={"README.md": "# widget\n"}))
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert JUSTFILE_PATH in outcome.reason
    assert CHECK_TARGETS_INVENTORY in outcome.reason


def test_truncated_tree_skips_rather_than_convicting_on_absence() -> None:
    ctx = make_context(table=_table(files={"README.md": "# widget\n"}, truncated=True))
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "truncated" in outcome.reason


def test_unreadable_tree_skips() -> None:
    ctx = make_context(table={})
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "unreadable" in outcome.reason


def test_unreadable_inventory_skips() -> None:
    ctx = make_context(table=_table(files={}, paths=[CHECK_TARGETS_INVENTORY]))
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert CHECK_TARGETS_INVENTORY in outcome.reason


def test_unreadable_justfile_skips() -> None:
    ctx = make_context(table=_table(files={}, paths=[JUSTFILE_PATH]))
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert JUSTFILE_PATH in outcome.reason


def test_justfile_with_no_bare_check_recipe_skips() -> None:
    """A parameterized `check *skip_targets:` aggregate is not a violation.

    `livespec-runtime` declares exactly this and delegates to a script, which
    is why it also carries the `check-targets.txt` inventory. A member with
    the parameterized recipe and NO inventory has an aggregate this row
    cannot enumerate — a skip, never a conviction.
    """
    ctx = make_context(
        table=_table(
            files={JUSTFILE_PATH: 'check *skip_targets:\n    .github/scripts/check.sh "$@"\n'}
        )
    )
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "not enumerable" in outcome.reason


def test_justfile_check_recipe_without_a_targets_array_skips() -> None:
    ctx = make_context(table=_table(files={JUSTFILE_PATH: "check:\n    just check-lint\n"}))
    outcome = assert_aggregate_gate_wired(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "targets=(...)" in outcome.reason


def test_row_is_registered_and_armed_in_the_obligation_table() -> None:
    """The row is IN the one table both engines walk, scoped by class.

    A row that exists but is unregistered enforces nothing — the exact
    silence `livespec-dev-tooling-739o` is about.
    """
    registered = {row.row_id: row for row in OBLIGATION_ROWS}

    assert registered[_ROW_ID].assert_member is assert_aggregate_gate_wired
    assert registered[_ROW_ID].applies_to == DEV_TOOLING_PIN_CLASSES
    assert all(slug in registered[_ROW_ID].manual_hint for slug in AGGREGATE_GATE_SLUGS)
    # Scoped BY CLASS: every dev-tooling-consuming class owes it, and the
    # enforcement suite — the SOURCE of the canonical slugs — does not.
    assert _ROW_ID in {row.row_id for row in rows_for(repo_class="console")}
    assert _ROW_ID not in {row.row_id for row in rows_for(repo_class="enforcement-suite")}


_MANIFEST_WITH_ADOPTER = """{
  "owner": "acme",
  "fleet": [{ "repo": "widget", "class": "impl-plugin" }],
  "adopters": [{ "repo": "sidecar", "profile": ["baseline"], "posture": "pinned" }]
}
"""


def _adopter_table() -> dict[tuple[str, ...], GhResult]:
    """Canned trees + justfiles for one fleet member and one adopter, BOTH unwired."""
    unwired = _justfile(targets=("check-lint",))
    table = _table(files={JUSTFILE_PATH: unwired})
    table[("api", "repos/acme/sidecar/git/trees/master?recursive=1")] = table[
        ("api", "repos/acme/widget/git/trees/master?recursive=1")
    ]
    table[_contents_args(repo="sidecar", path=JUSTFILE_PATH)] = GhResult(
        returncode=0, stdout=unwired, stderr=""
    )
    return table


def test_manifest_adopters_are_never_swept_by_the_aggregate_gate_row(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An adopter produces no aggregate-gate finding because the row never runs on it.

    NON-VACUOUS BY CONSTRUCTION: `sidecar`'s canned aggregate omits both
    slugs, so the row WOULD convict it — the control assertion proves that
    directly, against the same canned bytes. What spares it is that the
    obligation table is keyed by repo CLASS and an adopter declares none, so
    `run_member_rows` iterates `manifest.members` only. The lane is driven
    with this row alone (the `roster-probe` precedent) so the assertion is
    about THIS row rather than about a whole green fixture.
    """
    manifest = parse_manifest(source=_MANIFEST_WITH_ADOPTER).unwrap()
    row = next(candidate for candidate in OBLIGATION_ROWS if candidate.row_id == _ROW_ID)
    monkeypatch.setattr(_lanes, "rows_for", lambda *, repo_class: (row,))  # noqa: ARG005

    # The control: the very same aggregate text convicts when the row DOES run.
    control = make_context(table=_adopter_table())
    sidecar = FleetMember(repo="sidecar", repo_class="impl-plugin")
    assert isinstance(assert_aggregate_gate_wired(ctx=control, member=sidecar), RowFinding)

    # A FRESH context for the sweep: the control read sidecar's tree, and a
    # shared memo cache would make "the lane never touched sidecar" unprovable.
    log = RecordingLog()
    result = run_member_rows(ctx=make_context(table=_adopter_table()), manifest=manifest, log=log)

    assert manifest.member_names() == frozenset({"widget"})
    assert tuple(adopter.repo for adopter in manifest.adopters) == ("sidecar",)
    assert tuple(verdict.member for verdict in result.member_verdicts) == ("widget",)
    assert all(fields.get("member") != "sidecar" for _, fields in log.records)
    assert any(fields.get("member") == "widget" for _, fields in log.records)
