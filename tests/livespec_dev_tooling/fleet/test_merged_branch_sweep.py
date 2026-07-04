"""Tests for the merged-PR remote branch sweep tool."""

from __future__ import annotations

import json

from livespec_dev_tooling.fleet._context import FleetContext, GhResult, GhRunner
from livespec_dev_tooling.fleet.merged_branch_sweep import (
    SweepMode,
    fetch_manifest,
    format_reports,
    run_sweep,
)

__all__: list[str] = []


_MANIFEST_SOURCE = '{"owner": "acme", "fleet": [{"repo": "widget", "class": "library"}]}'
_MANIFEST_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec/contents/.livespec-fleet-manifest.jsonc?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_BRANCHES_ARGS: tuple[str, ...] = (
    "api",
    "--paginate",
    "--slurp",
    "repos/acme/widget/branches?per_page=100",
)


class RecordingRunner:
    """Canned-response `GhRunner` that records every invocation."""

    def __init__(self, *, table: dict[tuple[str, ...], GhResult]) -> None:
        self.table = table
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        key = tuple(args)
        self.calls.append(key)
        return self.table.get(key, GhResult(returncode=1, stdout="", stderr="no canned"))


def ok(*, payload: object) -> GhResult:
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def raw(*, text: str) -> GhResult:
    return GhResult(returncode=0, stdout=text, stderr="")


def make_context(*, runner: GhRunner) -> FleetContext:
    return FleetContext(owner="acme", run_gh=runner)


def prs_args(*, branch: str) -> tuple[str, ...]:
    return (
        "api",
        "--paginate",
        "--slurp",
        f"repos/acme/widget/pulls?head=acme%3A{branch}&state=all&per_page=100",
    )


def delete_args(*, branch: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/git/refs/heads/{branch}",
        "--method",
        "DELETE",
        "--input",
        "-",
    )


def base_table() -> dict[tuple[str, ...], GhResult]:
    return {
        _MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE),
        _BRANCHES_ARGS: ok(
            payload=[
                [
                    {"name": "feat/merged"},
                    {"name": "feat/open"},
                    {"name": "master"},
                    {"name": "release"},
                    {"name": "feat/unmerged"},
                ]
            ]
        ),
        prs_args(branch="feat/merged"): ok(
            payload=[
                [
                    {
                        "number": 12,
                        "state": "closed",
                        "merged_at": "2026-07-03T12:00:00Z",
                    }
                ]
            ]
        ),
        prs_args(branch="feat/open"): ok(
            payload=[
                [
                    {
                        "number": 13,
                        "state": "open",
                        "merged_at": None,
                    },
                    {
                        "number": 11,
                        "state": "closed",
                        "merged_at": "2026-07-02T12:00:00Z",
                    },
                ]
            ]
        ),
        prs_args(branch="feat/unmerged"): ok(
            payload=[
                [
                    {
                        "number": 14,
                        "state": "closed",
                        "merged_at": None,
                    }
                ]
            ]
        ),
    }


def test_fetch_manifest_reads_livespec_core_fleet_manifest() -> None:
    runner = RecordingRunner(table=base_table())
    manifest = fetch_manifest(ctx=make_context(runner=runner))

    assert manifest is not None
    assert [member.repo for member in manifest.members] == ["widget"]
    assert _MANIFEST_ARGS in runner.calls


def test_sweep_classification_is_pr_state_based_only() -> None:
    runner = RecordingRunner(table=base_table())
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert [(item.branch, item.pr_number) for item in reports[0].sweepable] == [("feat/merged", 12)]
    assert prs_args(branch="master") not in runner.calls
    assert prs_args(branch="release") not in runner.calls
    assert not any(
        call[0:2] == ("api", "repos/acme/widget/git/refs/heads/feat/merged")
        for call in runner.calls
    )


def test_dry_run_report_names_sweepable_branch_and_merged_pr() -> None:
    runner = RecordingRunner(table=base_table())
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert format_reports(reports=reports, mode=SweepMode.DRY_RUN) == (
        "widget\n" "  feat/merged -> merged PR #12\n"
    )


def test_execute_deletes_only_sweepable_branches() -> None:
    table = base_table()
    table[delete_args(branch="feat/merged")] = GhResult(returncode=0, stdout="", stderr="")
    runner = RecordingRunner(table=table)
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.EXECUTE)

    assert [item.branch for item in reports[0].deleted] == ["feat/merged"]
    assert delete_args(branch="feat/merged") in runner.calls
    assert delete_args(branch="feat/open") not in runner.calls
    assert delete_args(branch="feat/unmerged") not in runner.calls
