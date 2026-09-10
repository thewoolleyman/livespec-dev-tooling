"""Consumer-tier: `SPECIFICATION/scenarios.md` §"an unparseable pin file is a finding, never a passing row".

    Given a fleet member carries a file at a path a known pin format claims
    And the walk finds that file and cannot parse its contents
    When the pin-currency row for that format is evaluated
    Then the row MUST NOT report a passing outcome
    And the row MUST report a finding naming the member and the unparseable file
    And the finding MUST be distinguishable from that member carrying no pin of
    that format at all
    And the finding MUST be error severity in the release fan-out preflight and
    warning severity in every other evaluating context

Every arm is driven over the whole shipped path a release fan-out drives — the
manifest, the per-class obligation table, the injected `GhRunner` seam, the
tree listing, the contents fetch, and the pin walk — with only the member's
committed `.livespec.jsonc` BYTES varying between them. The three trees differ
in nothing else, which is what makes "distinguishable from carrying no pin at
all" an assertion about the row rather than about the fixture.

Two surfaces are read, deliberately. `run_member_rows` produces the
`MemberVerdict` the release fan-out's dispatch-matrix filter consumes, and it
carries row IDS only — so it is where the SEVERITY clause is asserted, because
severity is exactly what decides whether a row reaches that verdict. The row
function's own `RowOutcome` is where the MESSAGE lives, so the naming clause is
asserted there. Neither surface can answer the other's question.

The regression this closes was silent in the worst way: an unparseable pin file
arrived as an in-band record with a sentinel format, `_records_for`'s filter
dropped it, zero records reached the staleness comparison, and "no stale pins"
rendered as `RowPass()` — a member excluded from nothing, on the strength of a
file nobody could read.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest
import structlog
from returns.io import IOSuccess

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhOutcome,
    GhResult,
    RowFinding,
    RowPass,
)
from livespec_dev_tooling.fleet._contract_rows import CENTRAL_VANTAGE
from livespec_dev_tooling.fleet._lanes import run_member_rows
from livespec_dev_tooling.fleet._rows_pin_currency import assert_livespec_compat_pin_currency
from livespec_dev_tooling.fleet._snapshot import DownloadOutcome, DownloadResult
from livespec_dev_tooling.fleet.contract import Manifest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_MEMBER = FleetMember(repo="widget", repo_class="library")
_MANIFEST = Manifest(owner="acme", members=(_MEMBER,), adopters=())
_COMPAT_ROW = "compat-pin-currency"
_PIN_FILE = ".livespec.jsonc"

# Bytes at the path the `livespec_jsonc_compat_pinned` format claims, which the
# walk finds and cannot parse: a truncated object, the shape a half-applied
# rewrite really leaves behind.
_UNPARSEABLE = '{ "library": { "compat": { "pinned": "v1.0.0", '
# The same path, parseable and current, so the row has a genuine PASS to be
# distinguishable from as well as an absence.
_CURRENT = json.dumps({"library": {"compat": {"pinned": "v9.9.9", "livespec": "v1"}}})


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


def _context(*, pin_text: str | None, preflight: bool) -> FleetContext:
    """A context whose member carries `pin_text` at the pin path, or nothing there."""
    files = {} if pin_text is None else {_PIN_FILE: pin_text}
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
        filter_consuming_preflight=preflight,
    )


def _outcome(*, pin_text: str | None, preflight: bool = True) -> RowFinding | RowPass | object:
    """The compat pin-currency row's own outcome, where the message lives."""
    return assert_livespec_compat_pin_currency(
        ctx=_context(pin_text=pin_text, preflight=preflight), member=_MEMBER
    )


def _failing_rows(*, pin_text: str | None, preflight: bool) -> tuple[str, ...]:
    """The row ids that reached the member verdict a release fan-out filters on."""
    result = run_member_rows(
        ctx=_context(pin_text=pin_text, preflight=preflight),
        manifest=_MANIFEST,
        log=structlog.get_logger("test_pin_file_unparseable_row"),
        vantages=frozenset({CENTRAL_VANTAGE}),
    )
    verdicts = [entry for entry in result.member_verdicts if entry.member == _MEMBER.repo]
    assert len(verdicts) == 1, f"the one manifest member must produce one verdict; got {verdicts!r}"
    return verdicts[0].failing_rows


def test_an_unparseable_pin_file_is_a_finding_naming_the_member_and_the_file() -> None:
    """Never a pass, and the diagnostic carries both facts a remedy needs."""
    outcome = _outcome(pin_text=_UNPARSEABLE)

    assert not isinstance(outcome, RowPass), (
        f"the row MUST NOT report a passing outcome for a pin file it could not parse — "
        f"passing here is what excluded the member from nothing while its committed bytes "
        f"were unreadable; got {outcome!r}"
    )
    assert isinstance(outcome, RowFinding), (
        f"a can't-PARSE is a definitive, reproducible property of committed bytes, so it "
        f"is a FINDING rather than the skip a transient can't-read earns; got {outcome!r}"
    )
    assert _MEMBER.repo in outcome.message and _PIN_FILE in outcome.message, (
        f"the finding MUST name the member and the unparseable file — the per-member "
        f"remedy is 'fix your file', which needs both; got {outcome.message!r}"
    )


def test_the_finding_is_distinguishable_from_carrying_no_pin_of_that_format() -> None:
    """Absence is an answer; an unreadable presence is not, and the two must not agree."""
    absent = _outcome(pin_text=None)
    current = _outcome(pin_text=_CURRENT)
    unparseable = _outcome(pin_text=_UNPARSEABLE)

    assert isinstance(absent, RowPass), (
        f"a member carrying no pin of the format has nothing stale — the ratified "
        f"missing-file tolerance — so its row passes; got {absent!r}"
    )
    assert isinstance(current, RowPass), (
        f"a parseable, current pin passes too, so the finding below is earned by "
        f"UNPARSEABILITY rather than by the fixture merely carrying a file; got {current!r}"
    )
    assert type(unparseable) is not type(absent), (
        f"the finding MUST be distinguishable from that member carrying no pin of that "
        f"format at all: rendering both as the same outcome is exactly the fail-open that "
        f"turned an unreadable file into a passing row; "
        f"unparseable={unparseable!r} absent={absent!r}"
    )


def test_the_severity_is_scoped_to_the_evaluating_context() -> None:
    """Error where a per-member remedy can be applied, warning everywhere else."""
    preflight = _outcome(pin_text=_UNPARSEABLE, preflight=False)
    assert isinstance(preflight, RowFinding), preflight
    assert preflight.severity == "warning", (
        f"outside the filter-consuming fan-out preflight a failing row can only red a "
        f"whole job rather than exclude one member, so the finding stays a warning; "
        f"got {preflight.severity!r}"
    )
    assert _outcome(pin_text=_UNPARSEABLE) != preflight, (
        "the preflight and non-preflight outcomes must differ, or the scoping asserted "
        "here is not being applied at all"
    )

    assert _COMPAT_ROW in _failing_rows(pin_text=_UNPARSEABLE, preflight=True), (
        "in the release fan-out preflight the finding MUST be error severity, which is "
        "what puts the row in the member verdict the dispatch-matrix filter reads — "
        "otherwise the fan-out dispatches blindly to a member whose pins nobody can read"
    )
    assert _COMPAT_ROW not in _failing_rows(pin_text=_UNPARSEABLE, preflight=False), (
        "in every other evaluating context it is a warning, so it must not reach the "
        "verdict and exclude the member"
    )
    assert _COMPAT_ROW not in _failing_rows(pin_text=_CURRENT, preflight=True), (
        "a current pin must not reach the verdict in any context — without this the two "
        "assertions above could hold of a row that fails unconditionally"
    )
