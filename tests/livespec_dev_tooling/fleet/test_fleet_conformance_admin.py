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

The credential-CLASS split is pinned here too: under a `ghs_`-class
effective credential (a GitHub App installation token — the dispatch
credential a Fabro sandbox holds, projected as GITHUB_TOKEN) the lane's
rows are OUT-OF-VANTAGE (owned by the operator's own pre-push) and the
run passes at zero API reads, while under a user-class credential the
blind escalation stays exactly as shipped (livespec-dev-tooling-29qo).
Every CLI-level test therefore controls the token env explicitly: these
tests must pass identically on an operator host and inside a dispatch
sandbox whose ambient GITHUB_TOKEN is `ghs_`-class.
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


# The exact `event` string `_lanes` emits for a row the running lane
# structurally cannot evaluate. Asserted verbatim (the central suite's
# `_OUT_OF_VANTAGE_EVENT` precedent): the wording IS the signal an
# operator reading a green dispatch-context run scans for.
_OUT_OF_VANTAGE_EVENT = "obligation row is outside this lane's vantage (another lane owns it)"


def _admin_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the CLI as the OPERATOR context.

    Explicit `--owner` so no git remote is consulted, and no ambient env
    token, so the run is user-class (the lane's own vantage) even inside
    a dispatch sandbox whose environment projects a `ghs_`-class
    GITHUB_TOKEN. Tests exercising the dispatch-class path set their own
    token on top of this baseline.
    """
    monkeypatch.setattr(sys, "argv", ["fleet-conformance-admin", "--owner", "acme"])
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


def _shortfall_table() -> dict[tuple[str, ...], GhResult]:
    """The green two-member table with every admin-scoped read unreadable.

    The shape a credential without admin scope presents: manifest and
    member contents answer, the secrets list and the protection payload
    do not.
    """
    table = _two_member_table(blind_app_installation=False)
    for repo in ("widget", "gadget"):
        del table[("api", f"repos/acme/{repo}/actions/secrets")]
        del table[("api", f"repos/acme/{repo}/branches/master/protection")]
    return table


def _install_runner(
    monkeypatch: pytest.MonkeyPatch, *, table: dict[tuple[str, ...], GhResult]
) -> None:
    """Point the module's default gh runner at a canned-response table."""
    monkeypatch.setattr(fleet_conformance_admin, "default_gh_runner", make_runner(table=table))


def _install_recording_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    table: dict[tuple[str, ...], GhResult],
    calls: list[tuple[str, ...]],
) -> None:
    """Install a canned runner that also records every gh invocation into `calls`.

    Shared by the posture test (asserting WHICH repos are read) and the
    dispatch-class test (asserting NOTHING is read at all): what a lane
    does NOT read is part of its contract, and the recorded call list is
    how both tests make that assertable.
    """
    inner = make_runner(table=table)

    def recording(*, args: list[str], stdin: str | None = None) -> GhResult:
        calls.append(tuple(args))
        return inner(args=args, stdin=stdin)

    monkeypatch.setattr(fleet_conformance_admin, "default_gh_runner", recording)


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


def test_admin_lane_fails_loud_on_a_credential_shortfall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A USER-class run without admin scope must FAIL the lane, not read clean.

    This is the inverse of the central lane's treatment: there, these rows
    are out-of-vantage (expected, owned elsewhere). Here they are BLIND,
    because this IS the lane that should have read them — and a blind row
    is error severity now that the vantage model leaves no row structurally
    blind in any healthy context (b02's recorded end state): a lane that
    OWNS a row but could not read its source exits non-zero rather than
    passing vacuously. No lever, env var, or exemption can demote this.

    The explicit `ghp_` token pins the boundary of the dispatch-class
    classification: it applies to the `ghs_` class ONLY. An operator whose
    own user-class credential lacks (or lost) admin scope is a credential
    SHORTFALL inside this lane's vantage, never a reclassification — the
    run stays blind and stays exit 4.
    """
    _admin_argv(monkeypatch)
    monkeypatch.setenv("GH_TOKEN", "ghp_operator-pat-lacking-admin-scope")
    _install_runner(monkeypatch, table=_shortfall_table())

    assert fleet_conformance_admin.main() == 4


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
    data (`check-tests-no-subprocess-spawn`). Token env cleared explicitly
    (this test bypasses `_admin_argv` to omit `--owner`): an ambient
    `ghs_`-class token would classify the run dispatch-class before owner
    resolution is ever consulted.
    """
    monkeypatch.setattr(sys, "argv", ["fleet-conformance-admin"])
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
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
    _admin_argv(monkeypatch)
    _install_recording_runner(
        monkeypatch, table=_adopter_table(adopted_settings=_SUCCESSOR_SETTINGS), calls=calls
    )

    assert fleet_conformance_admin.main() == 0
    assert [call for call in calls if any("adopted" in arg for arg in call)]
    assert not [call for call in calls if any("keepsake" in arg for arg in call)]
    assert not [call for call in calls if any("showcase" in arg for arg in call)]


def test_admin_lane_is_out_of_vantage_under_a_dispatch_class_credential(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `ghs_`-class run classifies the lane OUT-OF-VANTAGE: exit 0, zero reads.

    The dispatch credential — a GitHub App installation token, projected
    into the sandbox as GITHUB_TOKEN — has admin scope DELIBERATELY
    withheld (the ratified v045 capability boundary), so a `ghs_`-class
    context is structurally not this lane's vantage: the lane's own design
    scopes it to the operator's pre-push under their own admin gh
    credentials. Treating that class as a credential shortfall instead
    (blind, exit 4) is the repo-wide factory outage journaled on
    livespec-dev-tooling-34t2: the Fabro sandbox's commit hooks reach the
    `just check` aggregate, so since ec66951 wired this lane in, NO
    dispatch sandbox could complete a Red commit. This is vantage
    CLASSIFICATION, the same mechanism `central_run_vantages` applies to
    the `central-app` row — not a lever, env var, or exemption: the
    sibling shortfall test above pins that a user-class credential still
    fails loud.

    Three properties pinned: exit 0; ZERO gh reads (the canned shortfall
    table reproduces today's sandbox death, and the recorded call list
    proves the classification never consults it — not even for the
    manifest, so an expired or fake dispatch token cannot turn
    classification into a precondition failure); and the out-of-vantage
    report names BOTH admin member rows plus the adopter leg, each owned
    by the operator's pre-push context under their own admin gh
    credentials.
    """
    calls: list[tuple[str, ...]] = []
    _admin_argv(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_dispatch-app-installation-token")
    _install_recording_runner(monkeypatch, table=_shortfall_table(), calls=calls)

    assert fleet_conformance_admin.main() == 0
    assert calls == []
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    reported = {
        record["row"]: record for record in records if record["event"] == _OUT_OF_VANTAGE_EVENT
    }
    assert set(reported) == {
        "secret-names",
        "branch-protection",
        "adopter-claude-plugin-currency",
    }
    for fields in reported.values():
        assert fields["vantage"] == "admin"
        owned_by = fields["owned_by"]
        assert isinstance(owned_by, str)
        assert "check-fleet-conformance-admin" in owned_by
        assert "operator's own admin gh credentials" in owned_by
        assert "pre-push" in owned_by


def test_admin_lane_fails_when_the_released_adopter_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable released adopter is BLIND — an error that fails the lane.

    This lane OWNS the adopter currency leg, so a released adopter it
    cannot read is the b02 shape — the leg enforced nothing — matching
    the member rows' treatment: blind is error severity and moves the
    exit to the finding code, never a vacuous pass. The
    blind/posture-excluded log accounting is asserted at the unit level
    in `test_adopter_lane`.
    """
    _admin_argv(monkeypatch)
    _install_runner(monkeypatch, table=_adopter_table(adopted_settings=None))

    assert fleet_conformance_admin.main() == 4


def test_admin_lane_unusable_credential_fails_before_any_row_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin lane gets the same z4qi preflight, and the same non-relaxation.

    It is the only context that enforces these rows, so a demoted credential
    verdict here would be a zero-enforcement hole rather than merely a missed
    signal.
    """
    _admin_argv(monkeypatch)
    table = _two_member_table(blind_app_installation=False)
    table[("api", "rate_limit")] = GhResult(
        returncode=1, stdout="", stderr="gh: Resource not accessible (HTTP 403)"
    )
    _install_runner(monkeypatch, table=table)

    assert fleet_conformance_admin.main() == 1
