"""Consumer-tier: a canonical check waived in `pyproject.toml` is exempt from the aggregate and fleet gates.

The scenarios in `SPECIFICATION/scenarios.md` on canonical-check waivers (ratified
v099) read, for a fleet member that declares `canonical_check_waivers` under
`[tool.livespec_dev_tooling]` with a slug and a non-empty reason:

    Given its `just check` aggregate does not select the waived slug
    When `check-aggregate-completeness` runs in the member and the fleet-conformance
    row `canonical-check-slugs-wired` evaluates the member's master tree
    Then neither fails on the waived slug
    And the fleet-conformance run logs the waiver with the member, the slug and the reason

and, beside it, that a stale waiver fails, that a malformed waiver fails, that an
unreadable member `pyproject.toml` makes the fleet row skip, and that an unparseable
one applies no waiver in the in-repo check.

Both gates are driven over the REAL canonical inventory (`canonical_check_slugs()`,
the filesystem walk of the shipped `checks/` package), never an injected set: a
waiver is only meaningful against the slugs consumers actually owe, and a synthetic
set would let the fixture drift from the shipped inventory unnoticed. The in-repo
check runs through its own `main()` over a consumer tree under `tmp_path`; the fleet
row runs through `run_member_rows` over a canned `GhRunner`, so the LOG assertion is
about what the lane emits, which is where a waiver becomes visible to an operator.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs
from livespec_dev_tooling.checks import aggregate_completeness
from livespec_dev_tooling.fleet import _lanes
from livespec_dev_tooling.fleet._context import FleetContext, FleetMember, GhOutcome, GhResult
from livespec_dev_tooling.fleet._contract_model import ObligationRow
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS
from livespec_dev_tooling.fleet._lanes import run_member_rows
from livespec_dev_tooling.fleet.contract import Manifest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_ROW_ID = "canonical-check-slugs-wired"
_WAIVED = "check-heading-coverage"
_REASON = "Rust member: its own check-behavior-coverage owns the scenario-keyed coverage map"
_WAIVER_EVENT = "fleet obligation honoured a canonical-check waiver"
_MEMBER = FleetMember(repo="console", repo_class="library")
_MANIFEST = Manifest(owner="acme", members=(_MEMBER,), adopters=())
_EXIT_VIOLATIONS = 4


def _canonical() -> tuple[str, ...]:
    return unsafe_perform_io(canonical_check_slugs().unwrap())


def _justfile(*, omit: str | None) -> str:
    """A consumer aggregate selecting every canonical slug except `omit`."""
    listed = "\n".join(f"        {slug}" for slug in _canonical() if slug != omit)
    return f"default:\n    @just --list\n\ncheck:\n    targets=(\n{listed}\n    )\n"


def _waivers_toml(*, entries: str) -> str:
    return f"[tool.livespec_dev_tooling]\ncanonical_check_waivers = {entries}\n"


_WAIVER_ENTRY = f'[{{ slug = "{_WAIVED}", reason = "{_REASON}" }}]'


def _run_in_repo_check(
    *,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    justfile: str,
    pyproject: str | None,
) -> tuple[int, list[dict[str, object]]]:
    """`check-aggregate-completeness` over a consumer tree; its exit code and findings."""
    _ = (root / "justfile").write_text(justfile, encoding="utf-8")
    if pyproject is not None:
        _ = (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setattr("sys.argv", ["aggregate-completeness"])
    code = aggregate_completeness.main()
    lines = capsys.readouterr().err.splitlines()
    return code, [json.loads(line) for line in lines if line.startswith("{")]


class _Log:
    """A lane logger double keeping each event with its structured fields."""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **fields: object) -> None:
        self.records.append((event, fields))

    warning = info
    error = info

    def events(self, *, event: str) -> list[dict[str, object]]:
        return [fields for name, fields in self.records if name == event]


def _context(*, justfile: str, pyproject: str | None) -> FleetContext:
    """A fleet context whose member `console` carries `justfile` and, optionally, a pyproject."""
    paths = ["justfile", *([] if pyproject is None else ["pyproject.toml"])]
    tree = {"tree": [{"path": path, "mode": "100644"} for path in paths], "truncated": False}
    files = {"justfile": justfile, **({} if pyproject is None else {"pyproject.toml": pyproject})}
    table: dict[tuple[str, ...], GhResult] = {
        ("api", "repos/acme/console/git/trees/master?recursive=1"): GhResult(
            returncode=0, stdout=json.dumps(tree), stderr=""
        )
    }
    for path, text in files.items():
        raw = ("api", f"repos/acme/console/contents/{path}?ref=master")
        table[(*raw, "-H", "Accept: application/vnd.github.raw")] = GhResult(
            returncode=0, stdout=text, stderr=""
        )

    def run(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        del stdin
        return IOSuccess(table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="none")))

    return FleetContext(owner="acme", run_gh=run)


def _canonical_row_only(*, repo_class: str) -> tuple[ObligationRow, ...]:
    del repo_class
    return tuple(row for row in OBLIGATION_ROWS if row.row_id == _ROW_ID)


def _run_fleet_row(
    *, monkeypatch: pytest.MonkeyPatch, justfile: str, pyproject: str | None
) -> tuple[_lanes.MemberRowsResult, _Log]:
    monkeypatch.setattr(_lanes, "rows_for", _canonical_row_only)
    log = _Log()
    result = run_member_rows(
        ctx=_context(justfile=justfile, pyproject=pyproject),
        manifest=_MANIFEST,
        log=log,
    )
    return result, log


def test_a_waived_canonical_check_is_exempt_from_both_gates_and_the_fleet_run_logs_it(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    justfile = _justfile(omit=_WAIVED)
    pyproject = _waivers_toml(entries=_WAIVER_ENTRY)

    # Control: the same aggregate WITHOUT the waiver is convicted by both gates.
    bare_code, bare_findings = _run_in_repo_check(
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        justfile=justfile,
        pyproject=None,
    )
    bare_fleet, _ = _run_fleet_row(monkeypatch=monkeypatch, justfile=justfile, pyproject=None)
    assert bare_code == _EXIT_VIOLATIONS
    assert [
        f["slug"] for f in bare_findings if f.get("failure_mode") == "missing_canonical_slug"
    ] == [_WAIVED]
    assert bare_fleet.error_findings == 1

    # Given the waiver: neither fails on the slug.
    code, findings = _run_in_repo_check(
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        justfile=justfile,
        pyproject=pyproject,
    )
    fleet, log = _run_fleet_row(monkeypatch=monkeypatch, justfile=justfile, pyproject=pyproject)

    assert code == 0
    assert findings == []
    assert fleet.error_findings == 0
    assert fleet.blind_rows == 0
    # ... and the fleet-conformance run logs the waiver with member, slug and reason.
    assert log.events(event=_WAIVER_EVENT) == [
        {"row": _ROW_ID, "member": _MEMBER.repo, "slug": _WAIVED, "reason": _REASON}
    ]


def test_a_stale_waiver_fails_both_gates_naming_the_slug(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    justfile = _justfile(omit=None)
    pyproject = _waivers_toml(entries=_WAIVER_ENTRY)

    code, findings = _run_in_repo_check(
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        justfile=justfile,
        pyproject=pyproject,
    )
    fleet, log = _run_fleet_row(monkeypatch=monkeypatch, justfile=justfile, pyproject=pyproject)

    assert code == _EXIT_VIOLATIONS
    assert [f["waiver"] for f in findings if f.get("failure_mode") == "stale_canonical_waiver"] == [
        _WAIVED
    ]
    assert fleet.error_findings == 1
    assert any(
        "stale" in str(fields["detail"]) and _WAIVED in str(fields["detail"])
        for fields in log.events(event="fleet obligation violated")
    )


def test_a_malformed_waiver_fails_both_gates_naming_the_slug_or_the_position(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    justfile = _justfile(omit=None)
    pyproject = _waivers_toml(
        entries=f'[{{ slug = "{_WAIVED}", reason = "" }}, {{ reason = "no slug" }}]'
    )

    code, findings = _run_in_repo_check(
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        justfile=justfile,
        pyproject=pyproject,
    )
    fleet, log = _run_fleet_row(monkeypatch=monkeypatch, justfile=justfile, pyproject=pyproject)

    assert code == _EXIT_VIOLATIONS
    assert [
        f["waiver"] for f in findings if f.get("failure_mode") == "malformed_canonical_waiver"
    ] == [_WAIVED, "entry at position 1"]
    assert fleet.error_findings == 1
    detail = str(log.events(event="fleet obligation violated")[0]["detail"])
    assert "malformed" in detail
    assert _WAIVED in detail
    assert "entry at position 1" in detail


def test_an_unreadable_member_pyproject_skips_the_fleet_row_and_an_unparseable_one_applies_no_waiver(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    justfile = _justfile(omit=_WAIVED)
    broken = '[tool.livespec_dev_tooling\ncanonical_check_waivers = [{ slug = "'

    # The fleet row: the tree lists a pyproject.toml the run cannot parse -> skip, no finding.
    fleet, log = _run_fleet_row(monkeypatch=monkeypatch, justfile=justfile, pyproject=broken)
    assert fleet.error_findings == 0
    assert fleet.blind_rows == 1
    assert [
        fields["member"]
        for fields in log.events(event="fleet obligation not evaluable (can't-read is not absent)")
    ] == [_MEMBER.repo]
    assert log.events(event="fleet obligation violated") == []

    # The in-repo check: the same bytes apply no waiver, so the omitted slug is still reported.
    code, findings = _run_in_repo_check(
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        justfile=justfile,
        pyproject=broken,
    )
    assert code == _EXIT_VIOLATIONS
    assert [f["slug"] for f in findings if f.get("failure_mode") == "missing_canonical_slug"] == [
        _WAIVED
    ]
