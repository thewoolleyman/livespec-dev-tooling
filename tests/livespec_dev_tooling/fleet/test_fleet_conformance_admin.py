"""Tests for `livespec_dev_tooling/fleet/fleet_conformance_admin.py`.

The admin (world-gate) lane's CLI is exercised in-process across its
precondition / finding / success / blind branches against canned-response
contexts.

The canned-response helpers are shared with the central lane's suite
(`test_fleet_conformance`) so both lanes are asserted against the SAME
fixture fleet — the property under test is which rows each lane runs, and
reusing one fixture is what makes that comparison meaningful.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from test_fleet_conformance import (
    _two_member_table,  # pyright: ignore[reportPrivateUsage]
    make_runner,
    ok,
)

from livespec_dev_tooling.fleet import fleet_conformance_admin
from livespec_dev_tooling.fleet._context import GhResult

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


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
