"""Tests for `livespec_dev_tooling/fleet/fleet_conformance_admin.py`.

The admin (world-gate) lane's CLI is exercised in-process across its
precondition / finding / success / blind branches against canned-response
contexts.

The canned-response helpers are shared with the central lane's suite
(`test_fleet_conformance`) so both lanes are asserted against the SAME
fixture fleet — the property under test is which rows each lane runs, and
reusing one fixture is what makes that comparison meaningful.

The adopter-manifest fixtures below exercise the posture-gated adopter
currency leg this lane OWNS (livespec-dev-tooling-453): `manifest.adopters`
iterated for exactly one concern — `claude-plugin-currency` — and only
where `posture == "released"`; every other posture is a declared choice
the lane honors by never reading the repo at all.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

from test_fleet_conformance import (
    _MANIFEST_ARGS,  # pyright: ignore[reportPrivateUsage]
    _two_member_table,  # pyright: ignore[reportPrivateUsage]
    make_runner,
    ok,
    raw,
)

from livespec_dev_tooling.fleet import fleet_conformance_admin
from livespec_dev_tooling.fleet._context import GhResult

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


# The two-member green fleet plus three adopters mirroring the live
# manifest's posture split: two `pinned` (declared choices the currency
# leg must honor by exclusion) and one `released` (the only adopter the
# leg may hold to currency).
_ADOPTER_MANIFEST_SOURCE = (
    '{"owner": "acme", "members": ['
    '{"repo": "widget", "class": "library"}, '
    '{"repo": "gadget", "class": "library"}], '
    '"adopters": ['
    '{"repo": "keepsake", "profile": ["baseline"], "posture": "pinned"}, '
    '{"repo": "showcase", "profile": ["baseline", "app"], "posture": "pinned"}, '
    '{"repo": "adopted", "profile": ["baseline", "app"], "posture": "released"}]}'
)

# Settings satisfying the currency row via its sanctioned successor slot
# (the exact shape homelab landed: mechanism + documentedIn, both non-empty).
_SUCCESSOR_SETTINGS = json.dumps(
    {
        "livespecPluginCurrencySuccessor": {
            "mechanism": "inline SessionStart updater loop",
            "documentedIn": ".ai/plugin-currency.md",
        }
    }
)
# Settings satisfying NEITHER recognized currency form: no SessionStart
# ensure-plugins hook and no documented successor.
_NONCONFORMANT_SETTINGS = '{"hooks": {}}'


def _adopter_table(*, adopted_settings: str | None) -> dict[tuple[str, ...], GhResult]:
    """The green two-member admin table under the three-adopter manifest.

    `adopted_settings` is the released adopter's `.claude/settings.json`
    text; None cans no reads for it at all, so its tree is unreadable —
    the can't-read shape a private adopter presents to a credential that
    cannot see it.
    """
    table = _two_member_table(blind_app_installation=False)
    table[_MANIFEST_ARGS] = raw(text=_ADOPTER_MANIFEST_SOURCE)
    if adopted_settings is None:
        return table
    tree_payload = {
        "tree": [{"path": ".claude/settings.json", "mode": "100644"}],
        "truncated": False,
    }
    table[("api", "repos/acme/adopted/git/trees/master?recursive=1")] = ok(payload=tree_payload)
    table[
        (
            "api",
            "repos/acme/adopted/contents/.claude/settings.json?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        )
    ] = raw(text=adopted_settings)
    return table


def _admin_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the CLI with an explicit owner so no git remote is consulted."""
    monkeypatch.setattr(sys, "argv", ["fleet-conformance-admin", "--owner", "acme"])


def _install_runner(
    monkeypatch: pytest.MonkeyPatch, *, table: dict[tuple[str, ...], GhResult]
) -> None:
    """Point the module's default gh runner at a canned-response table."""
    monkeypatch.setattr(fleet_conformance_admin, "default_gh_runner", make_runner(table=table))


def test_admin_lane_passes_when_every_admin_row_is_satisfied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _admin_argv(monkeypatch)
    _install_runner(monkeypatch, table=_two_member_table(blind_app_installation=False))

    assert fleet_conformance_admin.main() == 0


def test_admin_lane_fails_on_an_admin_row_finding(monkeypatch: pytest.MonkeyPatch) -> None:
    """A member missing a required Actions secret NAME is an error-severity finding."""
    table = _two_member_table(blind_app_installation=False)
    table[("api", "repos/acme/widget/actions/secrets")] = ok(
        payload={"secrets": [{"name": "APP_ID"}]}
    )
    _admin_argv(monkeypatch)
    _install_runner(monkeypatch, table=table)

    assert fleet_conformance_admin.main() == 4


def test_admin_lane_reports_a_credential_shortfall_as_blind_not_as_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running WITHOUT admin scope must not read as a clean run.

    This is the inverse of the central lane's treatment: there, these rows
    are out-of-vantage (expected, owned elsewhere). Here they are blind,
    because this IS the lane that should have read them. Exit stays 0 —
    blind is warning severity in both lanes — but the blind count is what
    makes the shortfall visible rather than silent.
    """
    table = _two_member_table(blind_app_installation=False)
    for repo in ("widget", "gadget"):
        del table[("api", f"repos/acme/{repo}/actions/secrets")]
        del table[("api", f"repos/acme/{repo}/branches/master/protection")]
    _admin_argv(monkeypatch)
    _install_runner(monkeypatch, table=table)

    assert fleet_conformance_admin.main() == 0


def test_admin_lane_has_no_run_lever(monkeypatch: pytest.MonkeyPatch) -> None:
    """A lever defaulting to unset would restore the zero-enforcement hole.

    The central sweep self-skips when `LIVESPEC_RUN_FLEET_CONFORMANCE` is
    unset. The admin lane must NOT inherit that: it is the only context
    that enforces these rows, so it runs whenever `just check` runs.
    """
    monkeypatch.delenv("LIVESPEC_RUN_FLEET_CONFORMANCE", raising=False)
    _admin_argv(monkeypatch)
    _install_runner(monkeypatch, table=_two_member_table(blind_app_installation=False))

    assert fleet_conformance_admin.main() == 0


def test_admin_lane_fails_loud_when_the_manifest_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _admin_argv(monkeypatch)
    _install_runner(monkeypatch, table={})

    assert fleet_conformance_admin.main() == 1


def test_admin_lane_fails_loud_when_the_owner_is_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No `--owner` and no github.com origin is a precondition failure, not a pass.

    Exercised in-process rather than by spawning `python -m`: the
    `if __name__ == "__main__"` guard is coverage-excluded, so a subprocess
    would buy no coverage while racing the parallel dispatcher's coverage
    data (`check-tests-no-subprocess-spawn`).
    """
    monkeypatch.setattr(sys, "argv", ["fleet-conformance-admin"])
    monkeypatch.setattr(fleet_conformance_admin, "resolve_owner", lambda: None)

    assert fleet_conformance_admin.main() == 1


def test_admin_lane_fails_when_a_released_adopter_is_nonconformant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recurrence guard for livespec-dev-tooling-453: `manifest.adopters` has a consumer.

    The defect class behind that item is a parsed-but-unread manifest
    field: `contract.py` typed and parsed `adopters`, nothing iterated
    them, and a nonconformant `released` adopter changed no outcome
    anywhere. This test pins the consumer BEHAVIORALLY — a `released`
    adopter whose settings satisfy neither recognized currency form must
    flip this lane's exit to 4. It asserts through the CLI entry point
    against manifest content alone, so any refactor that severs the
    manifest→adopter-iteration path fails here no matter which module
    carries the iteration — a parsed-but-unread `adopters` field can
    never again look consumed.
    """
    _admin_argv(monkeypatch)
    _install_runner(monkeypatch, table=_adopter_table(adopted_settings=_NONCONFORMANT_SETTINGS))

    assert fleet_conformance_admin.main() == 4


def test_admin_lane_reads_released_adopters_and_never_pinned_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Posture gates the iteration itself: `released` is read, `pinned` never is.

    livespec non-functional-requirements.md: the sweep "does NOT hold to
    currency any repo whose `posture` is not `released`" — honoring a
    declared pin means never even reading the repo, not reading it and
    then excusing the result. The conformant released adopter satisfies
    the currency row via the successor slot, so the lane exits 0.
    """
    calls: list[tuple[str, ...]] = []
    inner = make_runner(table=_adopter_table(adopted_settings=_SUCCESSOR_SETTINGS))

    def recording(*, args: list[str], stdin: str | None = None) -> GhResult:
        calls.append(tuple(args))
        return inner(args=args, stdin=stdin)

    _admin_argv(monkeypatch)
    monkeypatch.setattr(fleet_conformance_admin, "default_gh_runner", recording)

    assert fleet_conformance_admin.main() == 0
    assert [call for call in calls if any("adopted" in arg for arg in call)]
    assert not [call for call in calls if any("keepsake" in arg for arg in call)]
    assert not [call for call in calls if any("showcase" in arg for arg in call)]


def test_admin_lane_stays_green_when_the_released_adopter_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable released adopter is BLIND (warning, exit 0), never a failure.

    This lane OWNS the adopter currency leg, so a released adopter it
    cannot read is the b02 shape — reported blind (the leg enforced
    nothing), matching the member rows' treatment: blind warns and never
    moves the exit code. The blind/posture-excluded log accounting is
    asserted at the unit level in `test_adopter_lane`.
    """
    _admin_argv(monkeypatch)
    _install_runner(monkeypatch, table=_adopter_table(adopted_settings=None))

    assert fleet_conformance_admin.main() == 0
