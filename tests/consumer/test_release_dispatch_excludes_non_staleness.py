"""Consumer-tier: the `SPECIFICATION/scenarios.md` scenario in which a member with an
unparseable pin file or a non-pin error row is still excluded from the release
dispatch.

    Given a fleet member with an error-severity can't-parse pin finding, or an
    error-severity finding on a row other than a pin-currency row
    When the release fan-out filters its dispatch matrix
    Then the member MUST be excluded from the dispatch with an annotation naming
    it and the failing rows

This is the BOUNDARY of the staleness carve-out, and it is the half that makes
the carve-out safe rather than a hole. `SPECIFICATION/contracts.md` section
"Pin-currency severity policy" grants the exception to a finding of either
ratified STALENESS class and to nothing else: a can't-parse pin finding still
excludes, because the bump rewrite the dispatch would open cannot be applied to
a pin file that does not parse, and a member missing its secrets, shims, App
installation or branch protection cannot absorb a bump at all.

The can't-parse case is the sharp one, and it is why the verdict artifact
carries a staleness CLASS rather than a list of pin-currency row names. A stale
pin and an unparseable pin file are BOTH error-severity findings on the SAME
`compat-pin-currency` row. A filter keyed on the row id would read them as one
thing and dispatch blindly to a member whose committed pins nobody can parse —
so the sweep leg below asserts the row reaches the verdict UNMARKED, and the
filter leg asserts an unmarked row still excludes.
"""

from __future__ import annotations

import io
import json
import tarfile
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
from livespec_dev_tooling.fleet._lanes import member_verdict_payload, run_member_rows
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
_NON_PIN_ROW = "app-installation"

# Bytes at the path the `livespec_jsonc_compat_pinned` format claims, which the
# walk FINDS and cannot parse: a truncated object, the shape a half-applied
# rewrite really leaves behind.
_UNPARSEABLE = '{ "library": { "compat": { "pinned": "v1.0.0", '


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
    """A member whose committed pin file cannot be parsed, in the preflight lane."""
    files = {".livespec.jsonc": _UNPARSEABLE}
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
            stdout=json.dumps({"tag_name": "v9.9.9", "published_at": "2020-01-01T00:00:00Z"}),
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

    return structlog.get_logger("test_release_dispatch_excludes_non_staleness")


def _unparseable_pin_verdict() -> dict[str, object]:
    """The artifact entry the real central sweep writes for that member.

    Produced by the SHIPPED projection over a SHIPPED sweep rather than written
    by hand, so the filter legs below are reading the bytes a release fan-out
    would actually hand them.
    """
    result = run_member_rows(
        ctx=_context(),
        manifest=_MANIFEST,
        log=_log(),
        vantages=frozenset({CENTRAL_VANTAGE}),
    )
    payload = member_verdict_payload(member_verdicts=result.member_verdicts)
    entries = [entry for entry in payload if entry["member"] == _MEMBER.repo]
    assert len(entries) == 1, f"one manifest member must produce one verdict; got {payload!r}"
    return entries[0]


def _filter(
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
    assert (
        main(
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
        == 0
    ), "an exclusion is an ordinary result; only a structural failure reds the preflight"
    return (
        json.loads(filtered_path.read_text(encoding="utf-8")),
        json.loads(exclusions_path.read_text(encoding="utf-8")),
    )


def test_an_unparseable_pin_file_reaches_the_verdict_unmarked_by_the_staleness_class() -> None:
    """The row id is not the answer: the SAME row carries both kinds of finding."""
    verdict = _unparseable_pin_verdict()

    assert _COMPAT_ROW in verdict["failing_rows"], (
        "a can't-parse pin finding is error severity in the filter-consuming fan-out "
        f"preflight, so it must reach the verdict at all; got {verdict!r}"
    )
    assert _COMPAT_ROW not in verdict["staleness_rows"], (
        "a can't-parse finding is NOT one of the two ratified staleness classes, so it "
        "must reach the filter UNMARKED — marking it would dispatch blindly to a member "
        f"whose committed pin file nobody can parse; got {verdict!r}"
    )


def test_a_member_with_an_unparseable_pin_file_is_excluded_from_the_dispatch(
    tmp_path: Path,
) -> None:
    """No bump rewrite can be applied to a file that does not parse, so no dispatch."""
    filtered, summary = _filter(
        tmp_path=tmp_path, verdicts=[_unparseable_pin_verdict()], siblings=[_MEMBER.repo]
    )

    assert filtered == [], (
        "the member MUST be excluded from the dispatch matrix — this is the boundary "
        f"that keeps the staleness carve-out from becoming a hole; got {filtered!r}"
    )
    excluded = [entry for entry in summary if entry["member"] == _MEMBER.repo]
    assert (
        len(excluded) == 1 and excluded[0]["excluded"] is True
    ), f"the summary must record the exclusion as an exclusion; got {summary!r}"
    assert (
        _COMPAT_ROW in excluded[0]["failing_rows"]
    ), f"the summary must name the failing rows the exclusion rests on; got {summary!r}"


def test_a_non_pin_error_row_excludes_even_beside_a_staleness_row(tmp_path: Path) -> None:
    """The carve-out is per FINDING, not per member: one unmarked row still excludes.

    A member missing its App installation cannot absorb a bump at all, so its
    staleness findings — however many — do not buy it a dispatch.
    """
    filtered, summary = _filter(
        tmp_path=tmp_path,
        verdicts=[
            {
                "member": _MEMBER.repo,
                "conformant": False,
                "failing_rows": [_COMPAT_ROW, _NON_PIN_ROW],
                "staleness_rows": [_COMPAT_ROW],
            }
        ],
        siblings=[_MEMBER.repo],
    )

    assert filtered == [], (
        "one error-severity finding on a row other than a pin-currency row excludes the "
        f"member, whatever else it also fails; got {filtered!r}"
    )
    entry = summary[0]
    assert entry["excluded"] is True
    assert sorted(entry["failing_rows"]) == sorted([_COMPAT_ROW, _NON_PIN_ROW]), (
        "the annotation names EVERY failing row, not just the excluding one: an operator "
        f"reading it must see the whole repair list; got {entry!r}"
    )


def test_the_exclusion_annotation_names_the_member_and_its_failing_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """stdout is a protocol channel here — the Actions runner renders the annotation."""
    _ = _filter(tmp_path=tmp_path, verdicts=[_unparseable_pin_verdict()], siblings=[_MEMBER.repo])

    annotations = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("::warning::")
    ]
    assert any(
        _MEMBER.repo in line and _COMPAT_ROW in line and "EXCLUDED" in line for line in annotations
    ), (
        "the exclusion MUST surface as a workflow annotation naming the member and the "
        "failing rows — a silently omitted sibling is the livespec-bmxs hazard; got "
        f"{annotations!r}"
    )
