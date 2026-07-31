"""Tests for `livespec_dev_tooling/fleet/_rows_local_beads.py`.

Each beads-runtime probe is exercised across its three branches — no `.beads/`
directory (skip), prerequisite present (pass), prerequisite absent (a
WARNING-severity guided finding) — through a canned-response command runner and a
real `tmp_path` checkout. No host mutation, no real subprocess, and (the
probe-only discipline) no secret value is ever read or asserted on.
"""

from __future__ import annotations

from pathlib import Path

from returns.io import IOSuccess

from livespec_dev_tooling.fleet._context import RowFinding, RowPass, RowSkip
from livespec_dev_tooling.fleet._local_context import (
    CommandOutcome,
    CommandResult,
    LocalContext,
)
from livespec_dev_tooling.fleet._rows_local_beads import (
    DOLT_SERVER_HOST,
    DOLT_SERVER_PORT,
    reconcile_beads_bd_binary,
    reconcile_beads_config_committed,
    reconcile_beads_dolt_server,
    reconcile_beads_metadata_present,
    reconcile_beads_tenant_secret,
)

__all__: list[str] = []

_OK = CommandResult(returncode=0, stdout="", stderr="")
_FAIL = CommandResult(returncode=1, stdout="", stderr="x")

_BD_PROBE = (
    "bash",
    "-c",
    'if test -n "${LIVESPEC_BD_PATH:-}"; then '
    'test -x "$LIVESPEC_BD_PATH"; '
    'else bd_path="$(command -v bd 2>/dev/null)" && '
    'test -n "$bd_path" && test -x "$bd_path"; fi',
)
_DOLT_PROBE = (
    "timeout",
    "2",
    "bash",
    "-c",
    f"exec 3<>/dev/tcp/{DOLT_SERVER_HOST}/{DOLT_SERVER_PORT}",
)
_SECRET_PROBE = ("bash", "-c", 'test -n "${BEADS_DOLT_PASSWORD:-}"')
_CONFIG_PROBE = ("git", "ls-files", "--error-unmatch", ".beads/config.yaml")


def _ctx(
    *, checkout: Path, table: dict[tuple[str, ...], CommandResult] | None = None
) -> LocalContext:
    """A `LocalContext` over a canned runner keyed on the full args tuple (default OK)."""
    lookup = table or {}

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        del cwd
        return IOSuccess(lookup.get(tuple(args), _OK))

    return LocalContext(checkout=checkout, home=checkout / "home", run=run)


def _with_beads(*, tmp_path: Path) -> Path:
    """Create a `.beads/` tenant directory so the runtime rows apply."""
    (tmp_path / ".beads").mkdir()
    return tmp_path


def test_dolt_server_constants_force_tcp() -> None:
    assert (DOLT_SERVER_HOST, DOLT_SERVER_PORT) == ("127.0.0.1", 3307)


def test_bd_binary_skips_without_beads(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_beads_bd_binary(ctx=_ctx(checkout=tmp_path)), RowSkip)


def test_bd_binary_passes_when_present(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_bd_binary(ctx=ctx), RowPass)


def test_bd_binary_absent_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path), table={_BD_PROBE: _FAIL})
    outcome = reconcile_beads_bd_binary(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "LIVESPEC_BD_PATH" in outcome.message
    assert "`bd` on PATH" in outcome.message


def test_dolt_server_skips_without_beads(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_beads_dolt_server(ctx=_ctx(checkout=tmp_path)), RowSkip)


def test_dolt_server_passes_when_reachable(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_dolt_server(ctx=ctx), RowPass)


def test_dolt_server_unreachable_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path), table={_DOLT_PROBE: _FAIL})
    outcome = reconcile_beads_dolt_server(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "3307" in outcome.message


def test_tenant_secret_skips_without_beads(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_beads_tenant_secret(ctx=_ctx(checkout=tmp_path)), RowSkip)


def test_tenant_secret_passes_when_present(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_tenant_secret(ctx=ctx), RowPass)


def test_tenant_secret_absent_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path), table={_SECRET_PROBE: _FAIL})
    outcome = reconcile_beads_tenant_secret(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "BEADS_DOLT_PASSWORD" in outcome.message


def test_config_committed_skips_without_beads(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_beads_config_committed(ctx=_ctx(checkout=tmp_path)), RowSkip)


def test_config_committed_passes_when_tracked(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    assert isinstance(reconcile_beads_config_committed(ctx=ctx), RowPass)


def test_config_committed_untracked_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path), table={_CONFIG_PROBE: _FAIL})
    outcome = reconcile_beads_config_committed(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert ".beads/config.yaml" in outcome.message


def test_metadata_skips_without_beads(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_beads_metadata_present(ctx=_ctx(checkout=tmp_path)), RowSkip)


def test_metadata_passes_when_present(*, tmp_path: Path) -> None:
    beads = _with_beads(tmp_path=tmp_path)
    (beads / ".beads" / "metadata.json").write_text("{}", encoding="utf-8")
    assert isinstance(reconcile_beads_metadata_present(ctx=_ctx(checkout=beads)), RowPass)


def test_metadata_absent_is_warning_finding(*, tmp_path: Path) -> None:
    ctx = _ctx(checkout=_with_beads(tmp_path=tmp_path))
    outcome = reconcile_beads_metadata_present(ctx=ctx)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "metadata.json" in outcome.message
