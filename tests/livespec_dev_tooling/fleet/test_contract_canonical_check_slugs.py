"""Contract registration tests for the canonical-check aggregate fleet row."""

from __future__ import annotations

import pytest
from returns.io import IOSuccess
from test_fleet_conformance import RecordingLog
from test_rows_files import _MEMBER, make_context, tree_table

from livespec_dev_tooling.fleet import _lanes
from livespec_dev_tooling.fleet._context import FleetMember, GhResult, RowFinding
from livespec_dev_tooling.fleet._contract_classes import ALL_CLASSES
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


def test_canonical_slug_row_is_registered_for_fleet_members_only(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing aggregate is swept for `fleet`, never for manifest adopters."""
    registered = {row.row_id: row for row in OBLIGATION_ROWS}

    assert _ROW_ID in registered
    row = registered[_ROW_ID]
    assert row.assert_member is assert_canonical_check_slugs_wired
    assert row.applies_to == ALL_CLASSES
    assert all(
        _ROW_ID in {candidate.row_id for candidate in rows_for(repo_class=repo_class)}
        for repo_class in ALL_CLASSES
    )

    manifest = parse_manifest(source=_MANIFEST_WITH_ADOPTER).unwrap()
    monkeypatch.setattr(
        "livespec_dev_tooling.fleet._rows_canonical_check_slugs.canonical_check_slugs",
        lambda: IOSuccess(("check-alpha",)),
    )
    monkeypatch.setattr(_lanes, "rows_for", lambda *, repo_class: (row,))  # noqa: ARG005

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
