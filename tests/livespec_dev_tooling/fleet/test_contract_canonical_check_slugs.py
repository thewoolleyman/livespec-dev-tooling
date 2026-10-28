"""Contract registration tests for the canonical-check aggregate fleet row."""

from __future__ import annotations

import pytest
from returns.io import IOSuccess
from test_fleet_conformance import RecordingLog
from test_rows_files import _MEMBER, make_context, tree_table

from livespec_dev_tooling.fleet import _lanes
from livespec_dev_tooling.fleet._context import FleetMember, GhResult, RowFinding
from livespec_dev_tooling.fleet._contract_classes import ALL_CLASSES
from livespec_dev_tooling.fleet._contract_model import ObligationRow
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS, rows_for
from livespec_dev_tooling.fleet._lanes import run_member_rows
from livespec_dev_tooling.fleet._rows_canonical_check_slugs import (
    assert_canonical_check_slugs_wired,
)
from livespec_dev_tooling.fleet.contract import parse_manifest

__all__: list[str] = []


_ROW_ID = "canonical-check-slugs-wired"
_JUSTFILE_PATH = "justfile"
_MANIFEST_WITH_ADOPTER = """{
  "owner": "acme",
  "fleet": [{ "repo": "widget", "class": "impl-plugin" }],
  "adopters": [{ "repo": "sidecar", "profile": ["baseline"], "posture": "pinned" }]
}
"""


def _contents_args(*, repo: str) -> tuple[str, ...]:
    """The canned `gh` argv for one member justfile read."""
    return (
        "api",
        f"repos/acme/{repo}/contents/{_JUSTFILE_PATH}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _unwired_justfile() -> str:
    """A committed aggregate that omits the controlled canonical slug."""
    return (
        "check:\n"
        "    targets=(\n"
        "        check-lint\n"
        "    )\n"
        '    for target in "${targets[@]}"; do just "${target}"; done\n'
    )


def _table() -> dict[tuple[str, ...], GhResult]:
    """Canned unwired aggregates for both the manifest member and its adopter."""
    table = tree_table(paths=[_JUSTFILE_PATH])
    unwired = _unwired_justfile()
    table[_contents_args(repo="widget")] = GhResult(returncode=0, stdout=unwired, stderr="")
    table[("api", "repos/acme/sidecar/git/trees/master?recursive=1")] = table[
        ("api", "repos/acme/widget/git/trees/master?recursive=1")
    ]
    table[_contents_args(repo="sidecar")] = GhResult(returncode=0, stdout=unwired, stderr="")
    return table


def _canonical_row_only(*, repo_class: str) -> tuple[ObligationRow, ...]:
    """Keep the lane test focused on the canonical-slug obligation."""
    del repo_class
    registered = {row.row_id: row for row in OBLIGATION_ROWS}
    return (registered[_ROW_ID],)


def test_canonical_slug_row_is_registered_for_every_fleet_class() -> None:
    """The contract table binds the canonical aggregate asserter universally."""
    registered = {row.row_id: row for row in OBLIGATION_ROWS}

    assert _ROW_ID in registered
    row = registered[_ROW_ID]
    assert row.assert_member is assert_canonical_check_slugs_wired
    assert row.applies_to == ALL_CLASSES
    assert all(
        _ROW_ID in {candidate.row_id for candidate in rows_for(repo_class=repo_class)}
        for repo_class in ALL_CLASSES
    )


def test_canonical_slug_row_is_run_for_fleet_members_only(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing aggregate is swept for `fleet`, never for manifest adopters."""
    manifest = parse_manifest(source=_MANIFEST_WITH_ADOPTER).unwrap()
    monkeypatch.setattr(
        "livespec_dev_tooling.fleet._rows_canonical_check_slugs.canonical_check_slugs",
        lambda: IOSuccess(("check-alpha",)),
    )
    monkeypatch.setattr(_lanes, "rows_for", _canonical_row_only)

    control = assert_canonical_check_slugs_wired(
        ctx=make_context(table=_table()),
        member=FleetMember(repo="sidecar", repo_class=_MEMBER.repo_class),
    )
    assert isinstance(control, RowFinding)

    log = RecordingLog()
    result = run_member_rows(ctx=make_context(table=_table()), manifest=manifest, log=log)

    assert result.error_findings == 1
    assert tuple(verdict.member for verdict in result.member_verdicts) == ("widget",)
    assert result.member_verdicts[0].failing_rows == (_ROW_ID,)
    assert all(fields.get("member") != "sidecar" for _, fields in log.records)


_WAIVER_EVENT = "fleet obligation honoured a canonical-check waiver"
_PYPROJECT_PATH = "pyproject.toml"
_WAIVER_REASON = "Rust member; its coverage map is owned by its own check"


def _waiver_table(*, justfile: str) -> dict[tuple[str, ...], GhResult]:
    """Canned master tree for `widget`: an aggregate, plus a pyproject waiving `check-alpha`."""
    table = tree_table(paths=[_JUSTFILE_PATH, _PYPROJECT_PATH])
    table[_contents_args(repo="widget")] = GhResult(returncode=0, stdout=justfile, stderr="")
    table[
        (
            "api",
            f"repos/acme/widget/contents/{_PYPROJECT_PATH}?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        )
    ] = GhResult(
        returncode=0,
        stdout=(
            "[tool.livespec_dev_tooling]\n"
            f'canonical_check_waivers = [{{ slug = "check-alpha", reason = "{_WAIVER_REASON}" }}]\n'
        ),
        stderr="",
    )
    return table


def _justfile_selecting(*, slugs: tuple[str, ...]) -> str:
    listed = "\n".join(f"        {slug}" for slug in slugs)
    return f"check:\n    targets=(\n{listed}\n    )\n"


def test_lane_logs_the_honoured_waiver_with_member_slug_and_reason(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fully satisfied member still leaves a record of what it was excused from."""
    manifest = parse_manifest(source=_MANIFEST_WITH_ADOPTER).unwrap()
    monkeypatch.setattr(
        "livespec_dev_tooling.fleet._rows_canonical_check_slugs.canonical_check_slugs",
        lambda: IOSuccess(("check-alpha", "check-lint")),
    )
    monkeypatch.setattr(_lanes, "rows_for", _canonical_row_only)
    log = RecordingLog()

    result = run_member_rows(
        ctx=make_context(table=_waiver_table(justfile=_justfile_selecting(slugs=("check-lint",)))),
        manifest=manifest,
        log=log,
    )

    assert result.error_findings == 0
    assert log.fields_for(event=_WAIVER_EVENT) == [
        {"row": _ROW_ID, "member": "widget", "slug": "check-alpha", "reason": _WAIVER_REASON}
    ]


def test_lane_logs_the_honoured_waiver_even_when_another_slug_fails_the_member(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = parse_manifest(source=_MANIFEST_WITH_ADOPTER).unwrap()
    monkeypatch.setattr(
        "livespec_dev_tooling.fleet._rows_canonical_check_slugs.canonical_check_slugs",
        lambda: IOSuccess(("check-alpha", "check-beta", "check-lint")),
    )
    monkeypatch.setattr(_lanes, "rows_for", _canonical_row_only)
    log = RecordingLog()

    result = run_member_rows(
        ctx=make_context(table=_waiver_table(justfile=_justfile_selecting(slugs=("check-lint",)))),
        manifest=manifest,
        log=log,
    )

    assert result.error_findings == 1
    assert [fields["slug"] for fields in log.fields_for(event=_WAIVER_EVENT)] == ["check-alpha"]
    assert len(log.error_events) == 1
