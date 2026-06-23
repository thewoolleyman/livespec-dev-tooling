"""Tests for `livespec_dev_tooling/fleet/wire_fleet_member.py`.

The reconcile engine runs in-process against canned-response contexts
(sharing the same one-member-manifest fixture shape the conformance
tests use); the CLI entry point is exercised across its precondition /
unresolved / success branches, plus one `python -m` subprocess
invocation for the `__main__` guard (missing --repo → argparse usage
error).
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

from _protection_fixtures import aligned_merge_settings_payload, aligned_protection_payload

from livespec_dev_tooling.fleet import wire_fleet_member
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowOutcome,
    RowSkip,
)
from livespec_dev_tooling.fleet.contract import ObligationRow
from livespec_dev_tooling.fleet.wire_fleet_member import reconcile_member

if TYPE_CHECKING:
    import pytest
    import structlog.stdlib

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="library")
_MANIFEST_SOURCE = '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}]}'
_MANIFEST_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec/contents/.livespec-fleet-manifest.jsonc",
    "-H",
    "Accept: application/vnd.github.raw",
)
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_PYPROJECT_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/pyproject.toml",
    "-H",
    "Accept: application/vnd.github.raw",
)
_LATEST_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec-dev-tooling/releases/latest")
_SECRETS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/actions/secrets")
_INSTALL_ARGS: tuple[str, ...] = ("api", "installation/repositories?per_page=100")
_PROTECTION_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/branches/master/protection")
_REPO_ARGS: tuple[str, ...] = ("api", "repos/acme/widget")
_TOPICS_GET: tuple[str, ...] = ("api", "repos/acme/widget/topics")
_TOPICS_PUT: tuple[str, ...] = (
    "api",
    "repos/acme/widget/topics",
    "--method",
    "PUT",
    "--input",
    "-",
)
_CI_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.github/workflows/ci.yml",
    "-H",
    "Accept: application/vnd.github.raw",
)

_CI_YML = "jobs:\n  check:\n    strategy:\n      matrix:\n        target:\n          - check-a\n"
_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.0.0" }\n'


def make_runner(*, table: dict[tuple[str, ...], GhResult]) -> GhRunner:
    """Canned-response `GhRunner` keyed on full arg tuples."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    return run


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""
    return FleetContext(owner="acme", run_gh=make_runner(table=table))


def ok(*, payload: object) -> GhResult:
    """A successful API result carrying a JSON payload."""
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def raw(*, text: str) -> GhResult:
    """A successful raw-content API result."""
    return GhResult(returncode=0, stdout=text, stderr="")


def _green_table(*, topics: list[str] | None = None) -> dict[tuple[str, ...], GhResult]:
    """A table where every applicable row for the library member passes."""
    paths = [
        ".github/workflows/ci.yml",
        ".github/workflows/bump-pin-from-dispatch.yml",
        ".github/workflows/pin-freshness.yml",
        ".github/workflows/release-dispatch.yml",
        "pyproject.toml",
    ]
    tree_payload = {"tree": [{"path": p, "mode": "100644"} for p in paths], "truncated": False}
    return {
        _MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE),
        _TREE_ARGS: ok(payload=tree_payload),
        _PYPROJECT_ARGS: raw(text=_PYPROJECT),
        _LATEST_ARGS: ok(payload={"tag_name": "v1.0.0"}),
        _SECRETS_ARGS: ok(payload={"secrets": [{"name": "APP_ID"}, {"name": "APP_PRIVATE_KEY"}]}),
        _INSTALL_ARGS: ok(payload={"repositories": [{"name": "widget"}]}),
        _PROTECTION_ARGS: ok(payload=aligned_protection_payload()),
        _REPO_ARGS: ok(payload=aligned_merge_settings_payload()),
        _CI_ARGS: raw(text=_CI_YML),
        _TOPICS_GET: ok(payload={"names": topics if topics is not None else ["livespec-sibling"]}),
    }


def _log() -> structlog.stdlib.BoundLogger:
    import structlog

    return structlog.get_logger("test_wire_fleet_member")


def test_green_member_has_nothing_to_reconcile() -> None:
    ctx = make_context(table=_green_table())
    assert reconcile_member(ctx=ctx, member=_MEMBER, log=_log()) == 0


def test_missing_topic_is_reconciled_via_put() -> None:
    table = _green_table(topics=[])
    table[_TOPICS_PUT] = ok(payload={})
    ctx = make_context(table=table)
    assert reconcile_member(ctx=ctx, member=_MEMBER, log=_log()) == 0


def test_failed_reconcile_counts_as_unresolved() -> None:
    # Topic missing and the PUT absent from the table → reconcile fails.
    ctx = make_context(table=_green_table(topics=[]))
    assert reconcile_member(ctx=ctx, member=_MEMBER, log=_log()) == 1


def test_manual_only_row_counts_as_unresolved() -> None:
    # App installation not covering the member has no machine reconcile.
    table = _green_table()
    table[_INSTALL_ARGS] = ok(payload={"repositories": [{"name": "other"}]})
    ctx = make_context(table=table)
    assert reconcile_member(ctx=ctx, member=_MEMBER, log=_log()) == 1


def test_skips_and_warnings_are_not_wiring_concerns() -> None:
    # Unreadable secrets → skip; stale pin → warning; neither unresolved.
    table = _green_table()
    del table[_SECRETS_ARGS]
    table[_LATEST_ARGS] = ok(payload={"tag_name": "v9.9.9"})
    ctx = make_context(table=table)
    assert reconcile_member(ctx=ctx, member=_MEMBER, log=_log()) == 0


def test_reconcile_returning_skip_counts_as_unresolved(*, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_assert(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
        del ctx, member
        return RowFinding(message="synthetic violation")

    def skipping_reconcile(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
        del ctx, member
        return RowSkip(reason="synthetic can't-reconcile")

    synthetic = ObligationRow(
        row_id="synthetic-row",
        obligation_type="github-state",
        applies_to=frozenset({"library"}),
        assert_member=failing_assert,
        reconcile=skipping_reconcile,
    )

    def fake_rows_for(*, repo_class: str) -> tuple[ObligationRow, ...]:
        del repo_class
        return (synthetic,)

    monkeypatch.setattr(wire_fleet_member, "rows_for", fake_rows_for)
    ctx = make_context(table={})
    assert reconcile_member(ctx=ctx, member=_MEMBER, log=_log()) == 1


def _patch_runner(
    *, monkeypatch: pytest.MonkeyPatch, table: dict[tuple[str, ...], GhResult]
) -> None:
    monkeypatch.setattr(wire_fleet_member, "default_gh_runner", make_runner(table=table))


def test_main_owner_unresolvable_is_precondition_failure(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["wire-fleet-member", "--repo", "widget"])

    def no_owner(*, cwd: object = None) -> str | None:
        del cwd
        return None

    monkeypatch.setattr(wire_fleet_member, "resolve_owner", no_owner)
    assert wire_fleet_member.main() == 1


def test_main_unfetchable_manifest_is_precondition_failure(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["wire-fleet-member", "--repo", "widget", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table={})
    assert wire_fleet_member.main() == 1


def test_main_unregistered_repo_enforces_register_first(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys, "argv", ["wire-fleet-member", "--repo", "straggler", "--owner", "acme"]
    )
    _patch_runner(monkeypatch=monkeypatch, table=_green_table())
    assert wire_fleet_member.main() == 1


def test_main_green_member_exits_zero(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["wire-fleet-member", "--repo", "widget", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_green_table())
    assert wire_fleet_member.main() == 0


def test_main_unresolved_rows_exit_four(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["wire-fleet-member", "--repo", "widget", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_green_table(topics=[]))
    assert wire_fleet_member.main() == 4


def test_module_invocation_without_repo_is_usage_error() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "livespec_dev_tooling.fleet.wire_fleet_member"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "--repo" in result.stderr
