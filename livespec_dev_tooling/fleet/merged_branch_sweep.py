"""Sweep stale remote branches whose head PRs are already merged.

This is an operator tool, not a CI check. It reads livespec core's fleet
manifest at run time, evaluates each remote branch strictly from PR state,
and defaults to a dry-run report. Branch ancestry is intentionally not
consulted because the fleet rebase-merges PRs. A repo's DEFAULT branch —
whatever it is named — is never sweepable, even when it was once the head
of a merged PR (e.g. after a `main` -> `master` migration).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast
from urllib.parse import quote

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    GhResult,
    default_gh_runner,
    gh_answer,
    resolve_owner,
)
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet.contract import Manifest, parse_manifest

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "RepoSweepReport",
    "SweepMode",
    "SweepableBranch",
    "fetch_manifest",
    "format_reports",
    "main",
    "run_sweep",
]

_MANIFEST_REPO = "livespec"
_MANIFEST_PATH = ".livespec-fleet-manifest.jsonc"
# Fleet-convention literals protected in EVERY repo: `release` is the fleet's
# release channel, and `master` stays as a belt-and-suspenders literal. These
# are NOT the whole protection: each repo's ACTUAL default branch (whatever it
# is named) is additionally protected per repo in `_sweepable_branches` via
# `FleetContext.canonical_ref`, so a `main`-default repo can never have its
# default branch swept.
_PROTECTED_BRANCHES = frozenset({"master", "release"})
_ModeName = Literal["dry-run", "execute"]


@dataclass(frozen=True, kw_only=True)
class _SweepModeValue:
    value: _ModeName


class SweepMode:
    DRY_RUN: Final = _SweepModeValue(value="dry-run")
    EXECUTE: Final = _SweepModeValue(value="execute")


@dataclass(frozen=True, kw_only=True)
class SweepableBranch:
    branch: str
    pr_number: int


@dataclass(frozen=True, kw_only=True)
class RepoSweepReport:
    repo: str
    sweepable: tuple[SweepableBranch, ...]
    deleted: tuple[SweepableBranch, ...] = ()
    error: str | None = None


@dataclass(frozen=True, kw_only=True)
class _ApiFailure:
    repo: str
    path: str
    stderr: str

    def message(self) -> str:
        return f"GitHub API failed for {self.repo} at {self.path}: {self.stderr}"


_ApiPayload = tuple[object, ...] | _ApiFailure


def fetch_manifest(*, ctx: FleetContext) -> Manifest | None:
    """Fetch livespec core's committed fleet manifest from `master`."""
    text = ctx.file_text(repo=_MANIFEST_REPO, path=_MANIFEST_PATH)
    if text is None:  # pragma: no cover
        return None
    parsed = parse_manifest(source=text)
    if isinstance(parsed, Failure):
        # Reaching here means the fetch SUCCEEDED and the bytes are unparseable.
        # Recording it separately is what makes "could not fetch the manifest"
        # and "fetched a malformed manifest" distinguishable downstream; they
        # were the same `None` before.
        #
        # The reason is interpolated because the manifest lives in ANOTHER
        # repo: whoever reads this line does not have the bytes in front of
        # them, and "did not parse" alone left them re-parsing a 39-member
        # document by hand to find the one bad record.
        ctx.record_read_failure(
            operation="manifest",
            path=f"{_MANIFEST_REPO}:{_MANIFEST_PATH}",
            returncode=0,
            kind="malformed_content",
            detail=f"manifest fetched but did not parse: {parsed.failure().reason}",
        )
        return None
    return parsed.unwrap()


def run_sweep(
    *, ctx: FleetContext, manifest: Manifest, mode: _SweepModeValue
) -> tuple[RepoSweepReport, ...]:
    """Classify every manifest repo and optionally delete sweepable refs."""
    reports: list[RepoSweepReport] = []
    for member in manifest.members:
        sweepable = _sweepable_branches(ctx=ctx, repo=member.repo)
        if isinstance(sweepable, _ApiFailure):
            reports.append(
                RepoSweepReport(repo=member.repo, sweepable=(), error=sweepable.message())
            )
            continue
        deleted = _delete_sweepable(ctx=ctx, repo=member.repo, branches=sweepable, mode=mode)
        reports.append(
            RepoSweepReport(repo=member.repo, sweepable=tuple(sweepable), deleted=tuple(deleted))
        )
    return tuple(reports)


def format_reports(*, reports: tuple[RepoSweepReport, ...], mode: _SweepModeValue) -> str:
    """Human-readable per-repo report for stdout."""
    lines: list[str] = []
    for report in reports:
        lines.append(report.repo)
        if report.error is not None:
            lines.append(f"  ERROR {report.error}")
            continue
        if not report.sweepable:  # pragma: no cover
            lines.append("  no sweepable branches")
            continue
        for item in report.sweepable:
            suffix = " deleted" if mode == SweepMode.EXECUTE and item in report.deleted else ""
            lines.append(f"  {item.branch} -> merged PR #{item.pr_number}{suffix}")
    return "\n".join(lines) + "\n"


def _sweepable_branches(*, ctx: FleetContext, repo: str) -> list[SweepableBranch] | _ApiFailure:
    branch_names = _branch_names(ctx=ctx, repo=repo)
    if isinstance(branch_names, _ApiFailure):
        return branch_names
    protected = _PROTECTED_BRANCHES | {ctx.canonical_ref(repo=repo)}
    sweepable: list[SweepableBranch] = []
    for branch in branch_names:
        if branch in protected:
            continue
        merged = _merged_pr_head(ctx=ctx, repo=repo, branch=branch)
        if isinstance(merged, _ApiFailure):
            return merged
        if merged is not None:
            sweepable.append(merged)
    return sweepable


def _branch_names(*, ctx: FleetContext, repo: str) -> tuple[str, ...] | _ApiFailure:
    path = f"repos/{ctx.owner}/{repo}/branches?per_page=100"
    payload = _api_pages(ctx=ctx, repo=repo, path=path)
    if isinstance(payload, _ApiFailure):
        return payload
    names: list[str] = []
    for entry in payload:
        if isinstance(entry, dict):  # pragma: no branch
            name = cast("dict[str, object]", entry).get("name")
            if isinstance(name, str):  # pragma: no branch
                names.append(name)
    return tuple(names)


def _merged_pr_head(
    *, ctx: FleetContext, repo: str, branch: str
) -> SweepableBranch | _ApiFailure | None:
    pulls = _pulls_for_head(ctx=ctx, repo=repo, branch=branch)
    if isinstance(pulls, _ApiFailure):
        return pulls
    if any(_is_open_pull(record=record) for record in pulls):
        return None
    merged = [_pull_number(record=record) for record in pulls if _is_merged_pull(record=record)]
    numbers = [number for number in merged if number is not None]
    if not numbers:
        return None
    return SweepableBranch(branch=branch, pr_number=max(numbers))


def _pulls_for_head(
    *, ctx: FleetContext, repo: str, branch: str
) -> tuple[dict[str, object], ...] | _ApiFailure:
    head = quote(f"{ctx.owner}:{branch}")
    path = f"repos/{ctx.owner}/{repo}/pulls?head={head}&state=all&per_page=100"
    payload = _api_pages(ctx=ctx, repo=repo, path=path)
    if isinstance(payload, _ApiFailure):
        return payload
    pulls: list[dict[str, object]] = []
    for entry in payload:
        if isinstance(entry, dict):  # pragma: no branch
            pulls.append(cast("dict[str, object]", entry))
    return tuple(pulls)


def _is_open_pull(*, record: dict[str, object]) -> bool:
    return record.get("state") == "open"


def _is_merged_pull(*, record: dict[str, object]) -> bool:
    return record.get("state") == "closed" and isinstance(record.get("merged_at"), str)


def _pull_number(*, record: dict[str, object]) -> int | None:
    number = record.get("number")
    if isinstance(number, int):
        return number
    return None  # pragma: no cover


def _delete_sweepable(
    *, ctx: FleetContext, repo: str, branches: list[SweepableBranch], mode: _SweepModeValue
) -> list[SweepableBranch]:
    if mode == SweepMode.DRY_RUN:
        return []
    deleted: list[SweepableBranch] = []
    for branch in branches:
        path = f"repos/{ctx.owner}/{repo}/git/refs/heads/{quote(branch.branch, safe='/')}"
        result = gh_answer(outcome=ctx.api(path=path, method="DELETE", body="{}"))
        # A branch is recorded as deleted only when a `gh` that RAN said so.
        # `isinstance` first because an invocation that never happened has no
        # exit code, and defaulting it to "deleted" would report a sweep that
        # never touched the remote.
        if not isinstance(result, InvocationNotPerformed) and result.returncode == 0:
            deleted.append(branch)
    return deleted


def _api_pages(*, ctx: FleetContext, repo: str, path: str) -> _ApiPayload:
    result = gh_answer(outcome=ctx.run_gh(args=["api", "--paginate", "--jq", ".[]", path]))
    if isinstance(result, InvocationNotPerformed):
        return _ApiFailure(repo=repo, path=path, stderr=result.reason)
    if result.returncode != 0:
        return _ApiFailure(repo=repo, path=path, stderr=_stderr_text(result=result))
    decoder = json.JSONDecoder()
    text = result.stdout
    items: list[object] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        try:
            item, index = decoder.raw_decode(text, index)
            items.append(cast("object", item))
        except json.JSONDecodeError as exc:  # pragma: no cover
            return _ApiFailure(
                repo=repo,
                path=path,
                stderr=f"invalid JSON from gh: {exc.msg}",
            )
    return tuple(items)


def _stderr_text(*, result: GhResult) -> str:
    if result.stderr.strip():
        return result.stderr.strip()
    return "gh api exited non-zero without stderr"


def _build_parser() -> argparse.ArgumentParser:  # pragma: no cover
    parser = argparse.ArgumentParser(
        prog="merged-branch-sweep",
        description="Dry-run or execute stale merged-PR head branch cleanup across the fleet.",
    )
    _ = parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner override; defaults to the origin remote's owner.",
    )
    _ = parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete sweepable remote branches. Omit for the default dry-run report.",
    )
    return parser


def main() -> int:  # pragma: no cover
    args = _build_parser().parse_args()
    owner = cast("str | None", args.owner) or resolve_owner(cwd=Path.cwd())
    if owner is None:
        _ = sys.stderr.write("owner unresolvable: pass --owner or run inside a github.com clone\n")
        return 1
    ctx = FleetContext(owner=owner, run_gh=default_gh_runner)
    manifest = fetch_manifest(ctx=ctx)
    if manifest is None:
        _ = sys.stderr.write(
            f"fleet manifest unavailable: {owner}/{_MANIFEST_REPO}:{_MANIFEST_PATH}\n"
            + "".join(
                f"  cause: {failure.operation} {failure.path} "
                f"[{failure.kind}] rc={failure.returncode} {failure.detail}\n"
                for failure in ctx.read_failures
            )
        )
        return 1
    mode = SweepMode.EXECUTE if bool(args.execute) else SweepMode.DRY_RUN
    reports = run_sweep(ctx=ctx, manifest=manifest, mode=mode)
    _ = sys.stdout.write(format_reports(reports=reports, mode=mode))
    return 1 if any(report.error is not None for report in reports) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
