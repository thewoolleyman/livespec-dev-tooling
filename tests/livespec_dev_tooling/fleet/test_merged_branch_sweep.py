"""Tests for the merged-PR remote branch sweep tool."""

from __future__ import annotations

import json

import pytest

from livespec_dev_tooling.fleet._context import FleetContext, GhResult, GhRunner
from livespec_dev_tooling.fleet.merged_branch_sweep import (
    RepoSweepReport,
    SweepMode,
    fetch_manifest,
    format_reports,
    main,
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
    "--jq",
    ".[]",
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


def gh_jq_objects(*, payload: tuple[object, ...]) -> GhResult:
    return GhResult(
        returncode=0,
        stdout="\n".join(json.dumps(entry, indent=2) for entry in payload) + "\n",
        stderr="",
    )


def raw(*, text: str) -> GhResult:
    return GhResult(returncode=0, stdout=text, stderr="")


def make_context(*, runner: GhRunner) -> FleetContext:
    return FleetContext(owner="acme", run_gh=runner)


def prs_args(*, branch: str) -> tuple[str, ...]:
    return (
        "api",
        "--paginate",
        "--jq",
        ".[]",
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
        _BRANCHES_ARGS: gh_jq_objects(
            payload=(
                {"name": "feat/merged"},
                {"name": "feat/open"},
                {"name": "master"},
                {"name": "release"},
                {"name": "feat/unmerged"},
            )
        ),
        prs_args(branch="feat/merged"): gh_jq_objects(
            payload=(
                {
                    "number": 12,
                    "state": "closed",
                    "merged_at": "2026-07-03T12:00:00Z",
                },
            )
        ),
        prs_args(branch="feat/open"): gh_jq_objects(
            payload=(
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
            )
        ),
        prs_args(branch="feat/unmerged"): gh_jq_objects(
            payload=(
                {
                    "number": 14,
                    "state": "closed",
                    "merged_at": None,
                },
            )
        ),
    }


def main_default_table() -> dict[tuple[str, ...], GhResult]:
    """Canned fleet where widget's default branch is `main`, itself a merged-PR head."""
    table = base_table()
    table[("api", "repos/acme/widget")] = raw(text='{"default_branch": "main"}')
    table[_BRANCHES_ARGS] = gh_jq_objects(
        payload=(
            {"name": "main"},
            {"name": "feat/merged"},
            {"name": "master"},
            {"name": "release"},
        )
    )
    table[prs_args(branch="main")] = gh_jq_objects(
        payload=(
            {
                "number": 7,
                "state": "closed",
                "merged_at": "2026-07-01T12:00:00Z",
            },
        )
    )
    return table


def test_default_branch_is_never_sweepable_even_when_named_main() -> None:
    runner = RecordingRunner(table=main_default_table())
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert [(item.branch, item.pr_number) for item in reports[0].sweepable] == [("feat/merged", 12)]
    assert prs_args(branch="main") not in runner.calls
    assert prs_args(branch="master") not in runner.calls
    assert prs_args(branch="release") not in runner.calls


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


def test_failed_branch_listing_is_reported_loudly_without_false_empty() -> None:
    table = base_table()
    table[_BRANCHES_ARGS] = GhResult(
        returncode=1,
        stdout="",
        stderr="unknown flag: --slurp",
    )
    runner = RecordingRunner(table=table)
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert reports[0].error == (
        "GitHub API failed for widget at repos/acme/widget/branches?per_page=100: "
        "unknown flag: --slurp"
    )
    assert "no sweepable branches" not in format_reports(reports=reports, mode=SweepMode.DRY_RUN)
    assert format_reports(reports=reports, mode=SweepMode.DRY_RUN) == (
        "widget\n"
        "  ERROR GitHub API failed for widget at repos/acme/widget/branches?per_page=100: "
        "unknown flag: --slurp\n"
    )


def test_failed_branch_listing_without_stderr_reports_nonzero_exit() -> None:
    table = base_table()
    table[_BRANCHES_ARGS] = GhResult(returncode=1, stdout="", stderr="")
    runner = RecordingRunner(table=table)
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert reports[0].error == (
        "GitHub API failed for widget at repos/acme/widget/branches?per_page=100: "
        "gh api exited non-zero without stderr"
    )


def test_failed_pr_query_is_reported_loudly() -> None:
    table = base_table()
    table[prs_args(branch="feat/open")] = GhResult(
        returncode=1,
        stdout="",
        stderr="GraphQL rate limit",
    )
    runner = RecordingRunner(table=table)
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert reports[0].error == (
        "GitHub API failed for widget at "
        "repos/acme/widget/pulls?head=acme%3Afeat/open&state=all&per_page=100: "
        "GraphQL rate limit"
    )
    assert "no sweepable branches" not in format_reports(reports=reports, mode=SweepMode.DRY_RUN)


def test_no_sweepable_branches_prints_only_after_successful_listing() -> None:
    table = base_table()
    table[_BRANCHES_ARGS] = gh_jq_objects(payload=({"name": "master"},))
    runner = RecordingRunner(table=table)
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert format_reports(reports=reports, mode=SweepMode.DRY_RUN) == (
        "widget\n" "  no sweepable branches\n"
    )


def test_whitespace_only_paginated_output_reports_no_sweepable_branches() -> None:
    table = base_table()
    table[_BRANCHES_ARGS] = raw(text="\n  \n")
    runner = RecordingRunner(table=table)
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert format_reports(reports=reports, mode=SweepMode.DRY_RUN) == (
        "widget\n" "  no sweepable branches\n"
    )


def test_empty_paginated_output_reports_no_sweepable_branches() -> None:
    table = base_table()
    table[_BRANCHES_ARGS] = raw(text="")
    runner = RecordingRunner(table=table)
    manifest = fetch_manifest(ctx=make_context(runner=runner))
    assert manifest is not None

    reports = run_sweep(ctx=make_context(runner=runner), manifest=manifest, mode=SweepMode.DRY_RUN)

    assert format_reports(reports=reports, mode=SweepMode.DRY_RUN) == (
        "widget\n" "  no sweepable branches\n"
    )


def test_main_returns_nonzero_when_any_repo_report_has_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_manifest(*, ctx: FleetContext) -> object:
        del ctx
        return object()

    def fake_run_sweep(
        *, ctx: FleetContext, manifest: object, mode: object
    ) -> tuple[RepoSweepReport, ...]:
        del ctx, manifest, mode
        return (
            RepoSweepReport(
                repo="widget",
                sweepable=(),
                error="GitHub API failed for widget at repos/acme/widget/branches?per_page=100: boom",
            ),
        )

    monkeypatch.setattr("sys.argv", ["merged-branch-sweep", "--owner", "acme"])
    monkeypatch.setattr(
        "livespec_dev_tooling.fleet.merged_branch_sweep.fetch_manifest",
        fake_fetch_manifest,
    )
    monkeypatch.setattr("livespec_dev_tooling.fleet.merged_branch_sweep.run_sweep", fake_run_sweep)

    assert main() == 1


def test_fetch_manifest_records_malformed_content_distinctly_from_a_failed_fetch() -> None:
    """A fetched-but-unparseable manifest is a different fact from an unreachable one.

    Both used to return the same `None`, so an operator could not tell "the
    manifest on livespec master is corrupt" from "I could not reach GitHub" —
    which are opposite diagnoses with opposite responses.
    """
    ctx = FleetContext(
        owner="thewoolleyman",
        run_gh=_runner_returning(stdout="{ this is not valid jsonc"),
    )

    assert fetch_manifest(ctx=ctx) is None
    kinds = [failure.kind for failure in ctx.read_failures]
    assert "malformed_content" in kinds, f"got {kinds!r}"
    assert "not_found" not in kinds, "a successful fetch must not record a fetch failure"


def _runner_returning(*, stdout: str) -> GhRunner:
    def run(*, args: list[str], stdin: str | None = None) -> GhResult:  # noqa: ARG001
        return GhResult(returncode=0, stdout=stdout, stderr="")

    return run
