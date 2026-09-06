"""A throttled read and a permission gap must not render identically.

`livespec-dev-tooling-mmqe` was FILED as a credential/vantage gap — "members
unreadable to the CI credential ... needs a GitHub App installation fix, an
admin action outside any PR" — by an agent holding the failing log. Direct
measurement refuted every clause: the installation could see all nine members
and its primary pool read `limit=5000`. The cause was a throttle.

The misdiagnosis was AVAILABLE to be made because the run reported the two the
same way. `classify_gh_failure` already separated `rate_limited` from
`forbidden`, and both then became a `RowSkip` carrying prose, a blind row
saying only "enforced NOTHING this run", and a verdict counting blind rows.
GitHub answers a throttle with HTTP 403 — the SAME status as a denial — so the
status code cannot break the tie either, and the two want opposite responses:
slow down and retry later, versus an admin action that no retry substitutes
for.

These tests fix the distinction at the two places a reader actually looks: the
per-member row, and the run's overall verdict.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet import fleet_conformance
from livespec_dev_tooling.fleet._context import FleetContext, GhResult, GhRunner, ReadFailure
from livespec_dev_tooling.fleet._contract_rows import CENTRAL_VANTAGE
from livespec_dev_tooling.fleet.contract import parse_manifest
from livespec_dev_tooling.fleet.fleet_conformance import run_member_rows

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "fleet" / "_read_cause.py"
)
_MODULE_NAME = "livespec_dev_tooling.fleet._read_cause"

# The verbatim shapes the fleet App installation answers with. They are quoted
# rather than paraphrased because their INDISTINGUISHABILITY is the subject:
# both are HTTP 403, and only the body says which happened.
_RATE_LIMITED_STDERR = (
    "gh: API rate limit exceeded for installation ID 131208965. "
    "If you reach out to GitHub Support for help, please include the request ID "
    "8C30:2D9708:BB87665:C05B3F6:6A6FC1FC (HTTP 403)"
)
_FORBIDDEN_STDERR = "gh: Resource not accessible by integration (HTTP 403)"

_MANIFEST_SOURCE = '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}]}'
_MEMBER = "widget"
_MANIFEST_KEY = (
    "api",
    "repos/acme/livespec/contents/.livespec-fleet-manifest.jsonc?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_PROBE_KEY = ("api", "rate_limit")

_SKIP_EVENT = "fleet obligation not evaluable (can't-read is not absent)"
_BLIND_ROW_EVENT = "obligation row enforced NOTHING this run (skipped for every applicable member)"
_VERDICT_EVENT = "fleet conformance FAILED"


class RecordingLog:
    """Logger test double capturing each event's text AND its structured fields."""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []

    def error(self, event: str, **kwargs: object) -> None:
        self.records.append((event, kwargs))

    def warning(self, event: str, **kwargs: object) -> None:
        self.records.append((event, kwargs))

    def info(self, event: str, **kwargs: object) -> None:
        self.records.append((event, kwargs))

    def fields_for(self, *, event: str) -> list[dict[str, object]]:
        return [fields for recorded, fields in self.records if recorded == event]


def _refusing_runner(*, stderr: str) -> GhRunner:
    """Every read refused with `stderr`, except the manifest and the probe.

    The manifest and the credential probe answer so the sweep gets PAST its two
    preconditions and reaches the member rows — which is where the reporting
    defect lives. A run that stops at "credential unusable" never reaches it.
    """

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        key = tuple(args)
        if key == _PROBE_KEY:
            return GhResult(returncode=0, stdout='{"rate": {"remaining": 4999}}', stderr="")
        if key == _MANIFEST_KEY:
            return GhResult(returncode=0, stdout=_MANIFEST_SOURCE, stderr="")
        return GhResult(returncode=1, stdout="", stderr=stderr)

    return lift_gh(run)


def _swept(*, stderr: str) -> tuple[FleetContext, RecordingLog]:
    """Run the central member sweep with every member read refused by `stderr`."""
    ctx = FleetContext(owner="acme", run_gh=_refusing_runner(stderr=stderr))
    manifest = parse_manifest(source=_MANIFEST_SOURCE).unwrap()
    log = RecordingLog()
    _ = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantages=frozenset({CENTRAL_VANTAGE}))
    return ctx, log


def _causes(*, log: RecordingLog, event: str) -> set[object]:
    """Every `read_failure_cause` the records for `event` carry."""
    return {fields.get("read_failure_cause") for fields in log.fields_for(event=event)}


def test_a_throttled_member_row_says_rate_limited() -> None:
    """The row a reader looks at first must name the class, not just "unreadable"."""
    _ctx, log = _swept(stderr=_RATE_LIMITED_STDERR)

    skips = log.fields_for(event=_SKIP_EVENT)

    assert skips, "the sweep evaluated nothing, so there is no per-member row to read"
    assert _causes(log=log, event=_SKIP_EVENT) == {"rate-limited"}


def test_a_permission_denied_member_row_says_so_and_not_rate_limited() -> None:
    """The discriminator only works if the OTHER 403 reads differently."""
    _ctx, log = _swept(stderr=_FORBIDDEN_STDERR)

    assert _causes(log=log, event=_SKIP_EVENT) == {"permission-denied"}


def test_a_member_row_counts_the_two_kinds_separately() -> None:
    """A count of each is what makes "which of the two" answerable without a re-run."""
    _ctx, log = _swept(stderr=_RATE_LIMITED_STDERR)

    fields = log.fields_for(event=_SKIP_EVENT)[0]

    assert fields["member"] == _MEMBER
    assert isinstance(fields["rate_limited_reads"], int)
    assert fields["rate_limited_reads"] > 0
    assert fields["permission_denied_reads"] == 0
    assert "rate_limited" in fields["read_failure_kinds"]


def test_the_blind_row_report_carries_the_cause_and_its_remedy() -> None:
    """`blind_rows` is a PROGRESS marker; without the cause it reads as a finding count."""
    _ctx, log = _swept(stderr=_RATE_LIMITED_STDERR)

    blind = log.fields_for(event=_BLIND_ROW_EVENT)

    assert blind, "every applicable row was skipped, so at least one row is blind"
    assert _causes(log=log, event=_BLIND_ROW_EVENT) == {"rate-limited"}
    assert "no admin action helps" in str(blind[0]["read_failure_remedy"])


def test_the_overall_verdict_reports_the_two_kinds_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verdict is what a CI reader sees; it must not need the row detail to classify."""
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    monkeypatch.setattr(
        fleet_conformance, "default_gh_runner", _refusing_runner(stderr=_RATE_LIMITED_STDERR)
    )
    monkeypatch.setattr(fleet_conformance, "local_vantage", lambda **_kwargs: (None, None))
    log = RecordingLog()
    monkeypatch.setattr(fleet_conformance.structlog, "get_logger", lambda _name: log)

    assert fleet_conformance.main() == 4

    verdict = log.fields_for(event=_VERDICT_EVENT)
    assert verdict, "a run that failed on unreadable rows must state its verdict"
    assert verdict[0]["read_failure_cause"] == "rate-limited"
    assert verdict[0]["permission_denied_reads"] == 0


def test_the_manifest_precondition_failure_names_the_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The MEASURED occurrence: the sweep could not even enumerate members.

    Run 30499573870 logged `fleet manifest unavailable` with two `rate_limited`
    records beneath it, and was read as a permission gap anyway.
    """
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])

    def _all_refused(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        if tuple(args) == _PROBE_KEY:
            return GhResult(returncode=0, stdout='{"rate": {"remaining": 4999}}', stderr="")
        return GhResult(returncode=1, stdout="", stderr=_RATE_LIMITED_STDERR)

    monkeypatch.setattr(fleet_conformance, "default_gh_runner", lift_gh(_all_refused))
    monkeypatch.setattr(fleet_conformance, "local_vantage", lambda **_kwargs: (None, None))
    log = RecordingLog()
    monkeypatch.setattr(fleet_conformance.structlog, "get_logger", lambda _name: log)

    assert fleet_conformance.main() == 1

    unavailable = log.fields_for(event="fleet manifest unavailable")
    assert unavailable, "the run must say why it stopped"
    assert unavailable[0]["read_failure_cause"] == "rate-limited"


def _cause_fields() -> Any:
    """The projection under test, imported INSIDE the body.

    A top-level import of a module that does not exist yet dies at COLLECTION,
    which proves only unimportability. Asserting the file first makes the Red a
    genuine assertion about a module that is missing.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} carries the cause projection"
    return importlib.import_module(_MODULE_NAME).cause_fields


def _failure(*, kind: str, path: str) -> ReadFailure:
    return ReadFailure(operation="contents", path=path, returncode=1, kind=kind, detail="x")


def test_a_mixed_scope_refuses_to_collapse_to_one_class() -> None:
    """Reporting a mixed scope as either class alone sends the reader one wrong way."""
    cause_fields = _cause_fields()

    fields = cause_fields(
        failures=[
            _failure(kind="rate_limited", path="widget:AGENTS.md"),
            _failure(kind="forbidden", path="widget:justfile"),
        ]
    )

    assert fields["read_failure_cause"] == "rate-limited-and-permission-denied"
    assert fields["rate_limited_reads"] == 1
    assert fields["permission_denied_reads"] == 1


def test_a_scope_with_neither_kind_says_so_rather_than_guessing() -> None:
    """A transport failure is neither; naming it "throttled" would be an invention."""
    cause_fields = _cause_fields()

    fields = cause_fields(failures=[_failure(kind="transport", path="widget:AGENTS.md")])

    assert fields["read_failure_cause"] == "other-read-failure"
    assert fields["read_failure_kinds"] == ("transport",)


def test_an_empty_scope_reports_zero_rather_than_omitting_the_field() -> None:
    """A consumer must tell "zero" from "this run does not report it"."""
    cause_fields = _cause_fields()

    fields = cause_fields(failures=[])

    assert fields["read_failure_cause"] == "no-failed-read"
    assert fields["rate_limited_reads"] == 0
    assert fields["permission_denied_reads"] == 0


def test_member_scoping_matches_a_whole_path_segment_not_a_prefix() -> None:
    """`livespec` prefixes seven member names, and every run reads `livespec`.

    A substring test would attribute the manifest read to `livespec-dev-tooling`,
    `livespec-driver-codex` and the rest — every member would inherit a throttle
    it never hit.
    """
    cause_fields = _cause_fields()

    failures = [_failure(kind="rate_limited", path="repos/acme/livespec")]

    assert cause_fields(failures=failures, member="livespec")["rate_limited_reads"] == 1
    assert (
        cause_fields(failures=failures, member="livespec-dev-tooling")["read_failure_cause"]
        == "no-failed-read"
    )
