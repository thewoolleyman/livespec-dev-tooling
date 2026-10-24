"""Consumer-tier: the `SPECIFICATION/scenarios.md` scenario in which a member whose
only error findings are stale pins still receives the release dispatch.

    Given a fleet member whose only error-severity findings in the fan-out
    preflight are pin-currency staleness findings
    When the release fan-out filters its dispatch matrix
    Then the member MUST receive the sibling-released dispatch
    And the run's exclusion summary MUST name each of those findings for that member

The rule this closes is the one `SPECIFICATION/contracts.md` section "Pin-currency
severity policy" states outright: the `sibling-released` dispatch IS the remedy
for a stale pin, because the bump pull request it opens supersedes any stuck
one — so excluding the member removes the cure. Measured 2026-10-22:
livespec-console-beads-fabro last received a dispatch on 10-15 because ONE
`compat-pin-currency` row was error-severity, and every dev-tooling,
orchestrator and runtime dispatch that would have cured it was withheld for a
week.

TWO SURFACES ARE READ, deliberately, because neither can answer the other's
question. The per-member verdict artifact is the contract between the central
sweep and the fan-out's filter: the sweep decides WHICH failing rows carry a
staleness class, and the filter decides what that means for the dispatch
matrix. So the sweep is driven end-to-end over the injected `GhRunner` seam and
asserted on its classification, while the filter is driven over the artifact it
is contracted to read and asserted on the matrix and the summary it writes.

The fixture member for the sweep leg is deliberately NOT conformant in general —
a fixture rich enough to satisfy every obligation row would be asserting about
the fixture rather than about the classification. What matters is that the
staleness rows and ONLY the staleness rows are marked, which is exactly the
input the filter's rule consumes.
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
from livespec_dev_tooling.fleet._lanes import run_member_rows
from livespec_dev_tooling.fleet._snapshot import DownloadOutcome, DownloadResult
from livespec_dev_tooling.fleet.contract import Manifest
from livespec_dev_tooling.fleet.dispatch_matrix_filter import main

if TYPE_CHECKING:
    import structlog.stdlib

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_MEMBER = FleetMember(repo="widget", repo_class="library")
_MANIFEST = Manifest(owner="acme", members=(_MEMBER,), adopters=())
_COMPAT_ROW = "compat-pin-currency"
_DEV_TOOLING_ROW = "dev-tooling-pin"
# Past the ratified two-hour settle window, so the NEVER-FIRED class escalates
# to error severity in the filter-consuming preflight and reaches the verdict.
_PAST_THE_WINDOW = timedelta(hours=5)

_STALE_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.2.0" }\n'
_STALE_LIVESPEC_JSONC = json.dumps({"library": {"compat": {"pinned": "v1.0.0", "livespec": "v1"}}})


def _stamp(*, age: timedelta) -> str:
    """A `published_at` exactly `age` old, in GitHub's `Z`-suffixed spelling."""
    return (datetime.now(tz=timezone.utc) - age).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _context() -> FleetContext:
    """A member carrying two stale pins and no open bump PR, in the preflight lane."""
    files = {"pyproject.toml": _STALE_PYPROJECT, ".livespec.jsonc": _STALE_LIVESPEC_JSONC}
    tree = {"tree": [{"path": path, "mode": "100644"} for path in files], "truncated": False}
    table: dict[tuple[str, ...], GhResult] = {
        ("api", "repos/acme/widget/git/trees/master?recursive=1"): GhResult(
            returncode=0, stdout=json.dumps(tree), stderr=""
        ),
        ("api", "repos/acme/widget/pulls?state=open&per_page=100"): GhResult(
            returncode=0, stdout="[]", stderr=""
        ),
    }
    for repo in ("livespec", "livespec-dev-tooling"):
        table[("api", f"repos/acme/{repo}/releases/latest")] = GhResult(
            returncode=0,
            stdout=json.dumps({"tag_name": "v9.9.9", "published_at": _stamp(age=_PAST_THE_WINDOW)}),
            stderr="",
        )
    for path, text in files.items():
        table[
            (
                "api",
                f"repos/acme/widget/contents/{path}?ref=master",
                "-H",
                "Accept: application/vnd.github.raw",
            )
        ] = GhResult(returncode=0, stdout=text, stderr="")

    def run(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        del stdin
        return IOSuccess(table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="none")))

    return FleetContext(
        owner="acme",
        run_gh=run,
        download_gh=_download,
        filter_consuming_preflight=True,
    )


def _log() -> structlog.stdlib.BoundLogger:
    import structlog

    return structlog.get_logger("test_release_dispatch_staleness_keeps_member")


def _filtered(
    *, tmp_path: Path, verdicts: list[dict[str, object]], siblings: list[str]
) -> tuple[list[object], list[object]]:
    """Drive the shipped filter over one verdict artifact; return both artifacts."""
    verdicts_path = tmp_path / "verdicts.json"
    siblings_path = tmp_path / "siblings.json"
    filtered_path = tmp_path / "filtered.json"
    exclusions_path = tmp_path / "exclusions.json"
    _ = verdicts_path.write_text(json.dumps(verdicts), encoding="utf-8")
    _ = siblings_path.write_text(
        json.dumps([{"name": name} for name in siblings]), encoding="utf-8"
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
    assert exit_code == 0, (
        "a staleness-only member is an ordinary result, not a structural failure: the "
        "filter must keep the preflight job green and decide the matrix"
    )
    return (
        json.loads(filtered_path.read_text(encoding="utf-8")),
        json.loads(exclusions_path.read_text(encoding="utf-8")),
    )


def _staleness_only_verdict() -> dict[str, object]:
    """The artifact entry for a member whose every error row is a staleness row."""
    return {
        "member": "widget",
        "conformant": False,
        "failing_rows": [_DEV_TOOLING_ROW, _COMPAT_ROW],
        "staleness_rows": [_DEV_TOOLING_ROW, _COMPAT_ROW],
    }


def test_a_staleness_only_member_stays_in_the_dispatch_matrix(tmp_path: Path) -> None:
    """The dispatch is the cure, so the filter must not withhold it over staleness."""
    filtered, _ = _filtered(
        tmp_path=tmp_path,
        verdicts=[
            _staleness_only_verdict(),
            {"member": "other", "conformant": True, "failing_rows": [], "staleness_rows": []},
        ],
        siblings=["widget", "other"],
    )

    assert {"name": "widget"} in filtered, (
        "a member whose only error findings are pin-currency staleness findings MUST "
        "receive the sibling-released dispatch — excluding it removes the bump PR that "
        f"is the remedy for the very staleness it was excluded for; got {filtered!r}"
    )
    assert filtered == [{"name": "widget"}, {"name": "other"}], (
        "every conformant sibling must still be dispatched to, in discovery order, so "
        f"keeping the stale member costs nobody else their dispatch; got {filtered!r}"
    )


def test_the_run_summary_still_names_each_staleness_finding_for_that_member(
    tmp_path: Path,
) -> None:
    """Scoping lowers nothing here: the findings stay loud, they just stop excluding."""
    _, summary = _filtered(
        tmp_path=tmp_path,
        verdicts=[_staleness_only_verdict()],
        siblings=["widget"],
    )

    named = [entry for entry in summary if entry["member"] == "widget"]
    assert len(named) == 1, (
        "the run's exclusion summary MUST name the member whose staleness findings were "
        f"not acted on — a silent keep is the livespec-bmxs omission hazard; got {summary!r}"
    )
    entry = named[0]
    assert entry["excluded"] is False, (
        "the summary must say the member was DISPATCHED TO despite its findings, or a "
        f"reader cannot tell a named keep from a real exclusion; got {entry!r}"
    )
    assert sorted(entry["failing_rows"]) == sorted([_COMPAT_ROW, _DEV_TOOLING_ROW]), (
        "each of the member's staleness findings must be named by its row, which is what "
        f"the fan-out's step summary renders; got {entry!r}"
    )


def test_the_central_sweep_marks_the_staleness_rows_the_filter_reads() -> None:
    """The classification travels from the row that made the finding to the filter.

    Without it the filter cannot tell a staleness finding on `compat-pin-currency`
    from a can't-parse finding on the SAME row, and the row id alone is not an
    answer — which is why the verdict artifact carries the class rather than a
    list of pin-currency row names the filter could hardcode.
    """
    result = run_member_rows(
        ctx=_context(),
        manifest=_MANIFEST,
        log=_log(),
        vantages=frozenset({CENTRAL_VANTAGE}),
    )
    verdicts = [entry for entry in result.member_verdicts if entry.member == _MEMBER.repo]
    assert len(verdicts) == 1, f"one manifest member must produce one verdict; got {verdicts!r}"
    verdict = verdicts[0]

    assert set(verdict.staleness_rows) == {_COMPAT_ROW, _DEV_TOOLING_ROW}, (
        "both ratified staleness classes must be MARKED as such on the verdict the "
        f"fan-out filter reads; got {verdict.staleness_rows!r}"
    )
    assert set(verdict.staleness_rows) <= set(verdict.failing_rows), (
        "a marked row is a subset of the error-severity rows, never a separate list: "
        f"the mark says what KIND of error finding it is; got {verdict!r}"
    )
    assert set(verdict.failing_rows) - set(verdict.staleness_rows), (
        "this fixture's member also fails ordinary obligation rows, and those must NOT "
        "be marked — otherwise the assertion above would hold of a mark applied to every "
        f"failing row; got {verdict!r}"
    )
