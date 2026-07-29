"""Tests for `livespec_dev_tooling/fleet/_adopter_lane.py`.

The adopter currency leg's three outcome categories — evaluated, blind,
and posture-excluded — plus its vantage behavior, asserted at the unit
level against canned-response contexts and the `RecordingLog` double.
The CLI-level recurrence guard for livespec-dev-tooling-453 (the
manifest→adopter-iteration path must stay live) rides in
`test_fleet_conformance_admin`.
"""

from __future__ import annotations

import json

from returns.result import Success
from test_fleet_conformance import RecordingLog, make_context, make_runner, ok, raw

from livespec_dev_tooling.fleet._adopter_lane import (
    ADOPTER_CURRENCY_ROW_ID,
    POSTURE_EXCLUDED_EVENT,
    run_adopter_rows,
)
from livespec_dev_tooling.fleet._context import FleetContext, GhResult
from livespec_dev_tooling.fleet.contract import Manifest, parse_manifest

__all__: list[str] = []


# The exact event strings the leg emits, asserted verbatim (the
# `test_fleet_conformance` precedent): the wording IS the signal an
# operator scans a green run's log for, so a drift in it is a change
# in behavior, not cosmetics.
_BLIND_ROW_EVENT = "obligation row enforced NOTHING this run (skipped for every applicable member)"
_OUT_OF_VANTAGE_EVENT = "obligation row is outside this lane's vantage (another lane owns it)"
_POSTURE_EXCLUDED_EVENT = "adopter excluded by posture (declared choice honored, not evaluated)"

_ADOPTERS_MANIFEST_SOURCE = (
    '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}], '
    '"adopters": ['
    '{"repo": "keepsake", "profile": ["baseline"], "posture": "pinned"}, '
    '{"repo": "showcase", "profile": ["baseline", "app"], "posture": "none"}, '
    '{"repo": "adopted", "profile": ["baseline", "app"], "posture": "released"}]}'
)
_PINNED_ONLY_MANIFEST_SOURCE = (
    '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}], '
    '"adopters": [{"repo": "keepsake", "profile": ["baseline"], "posture": "pinned"}]}'
)
_NO_ADOPTERS_MANIFEST_SOURCE = (
    '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}]}'
)

_SUCCESSOR_SETTINGS = json.dumps(
    {
        "livespecPluginCurrencySuccessor": {
            "mechanism": "inline SessionStart updater loop",
            "documentedIn": ".ai/plugin-currency.md",
        }
    }
)
_NONCONFORMANT_SETTINGS = '{"hooks": {}}'


def _manifest(*, source: str) -> Manifest:
    outcome = parse_manifest(source=source)
    assert isinstance(outcome, Success), outcome
    return outcome.unwrap()


def _recording_context(
    *, table: dict[tuple[str, ...], GhResult], calls: list[tuple[str, ...]]
) -> FleetContext:
    """A canned-response context whose runner records every gh invocation."""
    inner = make_runner(table=table)

    def recording(*, args: list[str], stdin: str | None = None) -> GhResult:
        calls.append(tuple(args))
        return inner(args=args, stdin=stdin)

    return FleetContext(owner="acme", run_gh=recording)


def _adopted_reads(*, settings_text: str) -> dict[tuple[str, ...], GhResult]:
    """Canned reads answering the currency row for the released adopter."""
    tree_payload = {
        "tree": [{"path": ".claude/settings.json", "mode": "100644"}],
        "truncated": False,
    }
    return {
        ("api", "repos/acme/adopted/git/trees/master?recursive=1"): ok(payload=tree_payload),
        (
            "api",
            "repos/acme/adopted/contents/.claude/settings.json?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        ): raw(text=settings_text),
    }


def test_posture_excluded_adopters_are_reported_and_never_read() -> None:
    """Exclusion is a labeled category — logged per adopter, never an API read.

    The spec's posture gate is a declared choice ("never 'helpfully'
    updated"): a `pinned` or `none` adopter is not merely tolerated as a
    skip, it is HONORED — zero reads — and the honoring is stated at info
    severity so a green run shows the exclusions instead of implying them.
    """
    calls: list[tuple[str, ...]] = []
    ctx = _recording_context(table=_adopted_reads(settings_text=_SUCCESSOR_SETTINGS), calls=calls)
    log = RecordingLog()

    result = run_adopter_rows(
        ctx=ctx,
        manifest=_manifest(source=_ADOPTERS_MANIFEST_SOURCE),
        log=log,
        vantage="admin",
    )
    excluded = {
        fields["adopter"]: fields for fields in log.fields_for(event=_POSTURE_EXCLUDED_EVENT)
    }

    assert POSTURE_EXCLUDED_EVENT == _POSTURE_EXCLUDED_EVENT
    assert set(excluded) == {"keepsake", "showcase"}
    assert excluded["keepsake"]["posture"] == "pinned"
    assert excluded["showcase"]["posture"] == "none"
    assert result.posture_excluded == ("keepsake", "showcase")
    assert result.evaluated == 1
    assert result.error_findings == 0
    assert result.blind_rows == 0
    assert not [call for call in calls if any("keepsake" in arg for arg in call)]
    assert not [call for call in calls if any("showcase" in arg for arg in call)]


def test_released_adopter_finding_is_error_severity() -> None:
    """Adopter findings fail loud — there is no warning demotion path."""
    ctx = make_context(table=_adopted_reads(settings_text=_NONCONFORMANT_SETTINGS))
    log = RecordingLog()

    result = run_adopter_rows(
        ctx=ctx,
        manifest=_manifest(source=_ADOPTERS_MANIFEST_SOURCE),
        log=log,
        vantage="admin",
    )
    violations = log.fields_for(event="fleet obligation violated")

    assert result.error_findings == 1
    assert result.evaluated == 1
    assert result.blind_rows == 0
    assert len(violations) == 1
    assert violations[0]["row"] == ADOPTER_CURRENCY_ROW_ID
    assert violations[0]["member"] == "adopted"


def test_unreadable_released_adopter_is_blind_in_the_owning_lane() -> None:
    """Can't-read in the lane that OWNS the leg is the b02 signal, not a pass."""
    ctx = make_context(table={})
    log = RecordingLog()

    result = run_adopter_rows(
        ctx=ctx,
        manifest=_manifest(source=_ADOPTERS_MANIFEST_SOURCE),
        log=log,
        vantage="admin",
    )
    blind = log.fields_for(event=_BLIND_ROW_EVENT)

    assert result.blind_rows == 1
    assert result.evaluated == 0
    assert result.error_findings == 0
    assert len(blind) == 1
    assert blind[0]["row"] == ADOPTER_CURRENCY_ROW_ID
    assert blind[0]["applicable"] == 1
    assert blind[0]["skipped"] == 1
    assert blind[0]["reasons"] == ("master tree unreadable",)


def test_central_lane_reports_the_leg_out_of_vantage_at_zero_api_cost() -> None:
    """A lane that does not own the leg defers it — no reads, owner named.

    The central lane's automated contexts hold the fleet App installation
    token, which MUST NOT reach adopter repos, so evaluating there could
    only ever skip — the vacuously-green shape this leg's admin homing
    exists to avoid. The posture partition is the owning lane's report,
    so no posture-excluded lines appear here either.
    """
    calls: list[tuple[str, ...]] = []
    ctx = _recording_context(table={}, calls=calls)
    log = RecordingLog()

    result = run_adopter_rows(
        ctx=ctx,
        manifest=_manifest(source=_ADOPTERS_MANIFEST_SOURCE),
        log=log,
    )
    reported = log.fields_for(event=_OUT_OF_VANTAGE_EVENT)

    assert result.out_of_vantage_rows == 1
    assert result.evaluated == 0
    assert result.error_findings == 0
    assert result.blind_rows == 0
    assert result.posture_excluded == ("keepsake", "showcase")
    assert len(reported) == 1
    assert reported[0]["row"] == ADOPTER_CURRENCY_ROW_ID
    assert reported[0]["applicable"] == 1
    assert reported[0]["vantage"] == "admin"
    assert reported[0]["owned_by"] == "check-fleet-conformance-admin"
    assert log.fields_for(event=_POSTURE_EXCLUDED_EVENT) == []
    assert calls == []


def test_no_released_adopters_yields_no_out_of_vantage_line() -> None:
    """A leg applicable to nobody is not reported as deferred-to-elsewhere.

    This mirrors the member sweep's accounting: an out-of-vantage line
    counts the members a row APPLIED to, so a row applying to zero
    members never appears. With every adopter posture-excluded there is
    nothing for the admin lane to evaluate, hence nothing to defer.
    """
    ctx = make_context(table={})
    log = RecordingLog()

    result = run_adopter_rows(
        ctx=ctx,
        manifest=_manifest(source=_PINNED_ONLY_MANIFEST_SOURCE),
        log=log,
    )

    assert result.out_of_vantage_rows == 0
    assert result.posture_excluded == ("keepsake",)
    assert log.fields_for(event=_OUT_OF_VANTAGE_EVENT) == []


def test_manifest_without_adopters_is_inert_in_both_lanes() -> None:
    for vantage in ("central", "admin"):
        ctx = make_context(table={})
        log = RecordingLog()

        result = run_adopter_rows(
            ctx=ctx,
            manifest=_manifest(source=_NO_ADOPTERS_MANIFEST_SOURCE),
            log=log,
            vantage=vantage,
        )

        assert result.error_findings == 0
        assert result.blind_rows == 0
        assert result.out_of_vantage_rows == 0
        assert result.evaluated == 0
        assert result.posture_excluded == ()
        assert log.events == []
