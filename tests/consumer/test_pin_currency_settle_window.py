"""Consumer-tier: the pin-currency settle window, read off a member verdict.

Covers the `SPECIFICATION/scenarios.md` never-fired staleness scenarios and
the `SPECIFICATION/contracts.md` section "Pin-currency severity policy" that
ratifies them (v039).

The consumer-observable surface here is NOT a `python -m` check but the
per-member verdict artifact `fleet_conformance --emit-member-verdicts`
writes: `reusable-release-dispatch.yml`'s dispatch-matrix filter reads it and
excludes exactly the members whose rows failed. So these tests drive the
whole shipped path a release fan-out drives — the manifest, the central
lane, the per-class obligation table, the pin rows, and the shared settle
window — and assert on the row ids that reach a member's verdict, which is
the byte the filter acts on. A unit test calling one row function cannot
show that, which is why `scenarios.md` headings require this tier.
"""

from __future__ import annotations

import io
import json
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from returns.io import IOSuccess

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhOutcome,
    GhResult,
)
from livespec_dev_tooling.fleet._contract_rows import CENTRAL_VANTAGE
from livespec_dev_tooling.fleet._lanes import MemberVerdict, run_member_rows
from livespec_dev_tooling.fleet._snapshot import DownloadOutcome, DownloadResult
from livespec_dev_tooling.fleet.contract import Manifest

if TYPE_CHECKING:
    import structlog.stdlib

__all__: list[str] = []

pytestmark = pytest.mark.consumer


_MEMBER = FleetMember(repo="widget", repo_class="library")
_MANIFEST = Manifest(owner="acme", members=(_MEMBER,), adopters=())
_COMPAT_ROW = "compat-pin-currency"
_DEV_TOOLING_ROW = "dev-tooling-pin"
_PAST_THE_WINDOW = timedelta(hours=5)
_INSIDE_THE_WINDOW = timedelta(minutes=20)

_STALE_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.2.0" }\n'
_STALE_LIVESPEC_JSONC = json.dumps({"library": {"compat": {"pinned": "v1.0.0", "livespec": "v1"}}})


def _stamp(*, age: timedelta) -> str:
    """A `published_at` exactly `age` old, in GitHub's `Z`-suffixed spelling."""
    return (datetime.now(tz=timezone.utc) - age).strftime("%Y-%m-%dT%H:%M:%SZ")


def _contents_args(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _bare_archive(*, repo: str) -> bytes:
    """A real gzip tarball carrying one empty first-party package for `repo`."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        entry = tarfile.TarInfo(name=f"acme-{repo}-abc123/pkg/__init__.py")
        entry.size = 0
        bundle.addfile(entry, io.BytesIO(b""))
    return buffer.getvalue()


def _download(*, args: list[str], dest: Path) -> DownloadResult:
    _ = dest.write_bytes(_bare_archive(repo=args[1].split("/")[2]))
    return IOSuccess(DownloadOutcome(returncode=0, stderr=""))


def _table(
    *, published_at: str, open_prs: list[dict[str, object]]
) -> dict[tuple[str, ...], GhResult]:
    files = {"pyproject.toml": _STALE_PYPROJECT, ".livespec.jsonc": _STALE_LIVESPEC_JSONC}
    tree = {"tree": [{"path": path, "mode": "100644"} for path in files], "truncated": False}
    table = {
        ("api", "repos/acme/widget/git/trees/master?recursive=1"): GhResult(
            returncode=0, stdout=json.dumps(tree), stderr=""
        ),
        ("api", "repos/acme/widget/pulls?state=open&per_page=100"): GhResult(
            returncode=0, stdout=json.dumps(open_prs), stderr=""
        ),
    }
    for repo in ("livespec", "livespec-dev-tooling"):
        table[("api", f"repos/acme/{repo}/releases/latest")] = GhResult(
            returncode=0,
            stdout=json.dumps({"tag_name": "v9.9.9", "published_at": published_at}),
            stderr="",
        )
    for path, text in files.items():
        table[_contents_args(path=path)] = GhResult(returncode=0, stdout=text, stderr="")
    return table


def _context(
    *, published_at: str, open_prs: list[dict[str, object]], preflight: bool
) -> FleetContext:
    table = _table(published_at=published_at, open_prs=open_prs)

    def run(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        del stdin
        return IOSuccess(table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="none")))

    return FleetContext(
        owner="acme",
        run_gh=run,
        download_gh=_download,
        filter_consuming_preflight=preflight,
    )


def _log() -> structlog.stdlib.BoundLogger:
    import structlog

    return structlog.get_logger("test_pin_currency_settle_window")


def _verdict(
    *,
    age: timedelta,
    preflight: bool = True,
    open_prs: list[dict[str, object]] | None = None,
) -> MemberVerdict:
    """The one member's verdict from a full central-lane sweep."""
    result = run_member_rows(
        ctx=_context(
            published_at=_stamp(age=age),
            open_prs=[] if open_prs is None else open_prs,
            preflight=preflight,
        ),
        manifest=_MANIFEST,
        log=_log(),
        vantages=frozenset({CENTRAL_VANTAGE}),
    )
    verdicts = [entry for entry in result.member_verdicts if entry.member == _MEMBER.repo]
    assert len(verdicts) == 1
    return verdicts[0]


def test_never_fired_past_the_settle_window_reaches_the_member_verdict() -> None:
    """Both pin sites escalate, so the dispatch-matrix filter can exclude the member.

    This is the state the 2026-07-30 fan-out outage ran in — stale with NO
    bump PR — which before v039 could not enter the escalating class at all,
    whatever severity that class carried.
    """
    verdict = _verdict(age=_PAST_THE_WINDOW)

    assert _COMPAT_ROW in verdict.failing_rows
    assert _DEV_TOOLING_ROW in verdict.failing_rows


def test_never_fired_inside_the_settle_window_stays_out_of_the_member_verdict() -> None:
    """Inside the window the finding is a warning, so no member is excluded."""
    verdict = _verdict(age=_INSIDE_THE_WINDOW)

    assert _COMPAT_ROW not in verdict.failing_rows
    assert _DEV_TOOLING_ROW not in verdict.failing_rows


def test_both_staleness_classes_are_evaluated_and_stay_lane_scoped() -> None:
    """The partition is exhaustive, and BOTH halves keep the ratified scoping.

    The fired-and-could-not-land half escalates at any release age; the
    never-fired half escalates only past the window; and neither reaches a
    verdict outside the filter-consuming fan-out preflight, where a failing
    row can only red a whole job rather than exclude one member.
    """
    fired = _verdict(
        age=_INSIDE_THE_WINDOW,
        open_prs=[
            {
                "number": 7,
                "title": "chore(deps): bump livespec pin to v9.9.9",
                "head": {"ref": "bump-livespec-v9.9.9"},
            }
        ],
    )
    never_fired = _verdict(age=_PAST_THE_WINDOW)
    per_pr_ci = _verdict(age=_PAST_THE_WINDOW, preflight=False)

    assert _COMPAT_ROW in fired.failing_rows
    assert _COMPAT_ROW in never_fired.failing_rows
    assert _COMPAT_ROW not in per_pr_ci.failing_rows
    assert _DEV_TOOLING_ROW not in per_pr_ci.failing_rows
