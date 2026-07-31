"""Tests for `livespec_dev_tooling/fleet/_rows_local_jsonc.py`.

The `livespec-jsonc-complete` local row is exercised across all eight
semantic branches — absent file (warning), unparseable / non-object root
(warning), no `harnesses` object (warning), not beads-backed (pass), no
`dolt.*` keys (pass), connection-absent → machine-fill (pass),
impl-plugin block unlocatable (warning), connection drift (warning), and
connection consistent (pass) — plus the comment-preserving writer. Each
runs against a real `tmp_path` checkout carrying real `.livespec.jsonc` +
`.beads/config.yaml` fixtures and a no-op command runner (the row reaches
only the filesystem under `ctx.checkout`, never a subprocess). The
machine-fill branch additionally proves the written bytes re-parse as
JSONC, carry the five connection keys with the `.beads/config.yaml`
values, preserve the file's comment, and satisfy the central
`assert_tenant_connection_consistency`.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from _gh_railway import lift_gh
from returns.result import Success

from livespec_dev_tooling.fleet._connection import named_plugin_connection, parse_document
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
)
from livespec_dev_tooling.fleet._local_context import LocalContext, default_command_runner
from livespec_dev_tooling.fleet._rows_beads import assert_tenant_connection_consistency
from livespec_dev_tooling.fleet._rows_local_jsonc import reconcile_livespec_jsonc_complete

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_BEADS_FULL = textwrap.dedent(
    """\
    # Beads Configuration File
    dolt.mode: server
    dolt.server-host: 127.0.0.1
    dolt.server-port: 3307
    dolt.server-user: widget
    dolt.database: widget
    dolt.prefix: widget
    """
)
# A beads config with no `dolt.*` connection keys (branch 5).
_BEADS_NO_DOLT_KEYS = "# Beads Configuration File\ndolt.mode: server\n"
# A beads config missing `dolt.prefix` — exercises the writer's "render only
# the keys actually present" filter.
_BEADS_MISSING_PREFIX = textwrap.dedent(
    """\
    dolt.server-host: 127.0.0.1
    dolt.server-port: 3307
    dolt.server-user: widget
    dolt.database: widget
    """
)

# A harnesses-bearing config whose impl-plugin block carries NO connection.
_CONFIG_NO_CONNECTION = textwrap.dedent(
    """\
    // hermetic test config
    {
      "harnesses": {
        "claude": { "status": "supported", "canonical_command": "/livespec:doctor" }
      },
      "implementation": { "plugin": "widget-impl" },
      "widget-impl": {
        "format": "beads"
      }
    }
    """
)
# Harnesses present, impl-plugin block carries a CONSISTENT connection.
_CONFIG_CONSISTENT = textwrap.dedent(
    """\
    // hermetic test config
    {
      "harnesses": {
        "claude": { "status": "supported", "canonical_command": "/livespec:doctor" }
      },
      "implementation": { "plugin": "widget-impl" },
      "widget-impl": {
        "connection": {
          "server_host": "127.0.0.1",
          "server_port": 3307,
          "server_user": "widget",
          "database": "widget",
          "prefix": "widget"
        },
        "format": "beads"
      }
    }
    """
)
# Harnesses present, impl-plugin connection DISAGREES on server_port.
_CONFIG_DRIFT = _CONFIG_CONSISTENT.replace('"server_port": 3307', '"server_port": 9999')
# No top-level harnesses object (branch 3).
_CONFIG_NO_HARNESSES = textwrap.dedent(
    """\
    {
      "implementation": { "plugin": "widget-impl" },
      "widget-impl": { "format": "beads" }
    }
    """
)
# An EMPTY harnesses object is also "no non-empty harnesses" (branch 3).
_CONFIG_EMPTY_HARNESSES = textwrap.dedent(
    """\
    {
      "harnesses": {},
      "implementation": { "plugin": "widget-impl" },
      "widget-impl": { "format": "beads" }
    }
    """
)
# Harnesses present but NO `implementation` block — the impl-plugin block is
# unlocatable, so the connection cannot be machine-filled (branch 6 failure).
_CONFIG_NO_IMPLEMENTATION = textwrap.dedent(
    """\
    {
      "harnesses": {
        "claude": { "status": "supported" }
      },
      "widget-impl": { "format": "beads" }
    }
    """
)
# `implementation.plugin` names a block that does not exist as a raw-text key —
# the line-anchored regex finds no opening brace (branch 6 failure).
_CONFIG_GHOST_PLUGIN = textwrap.dedent(
    """\
    {
      "harnesses": {
        "claude": { "status": "supported" }
      },
      "implementation": { "plugin": "ghost-impl" },
      "widget-impl": { "format": "beads" }
    }
    """
)


def _local_ctx(*, checkout: Path) -> LocalContext:
    """A `LocalContext` for the row, which reaches only the filesystem under `checkout`.

    The row never issues a subprocess, so the real `default_command_runner`
    is wired in but never invoked (no dead canned-runner closure to cover).
    """
    return LocalContext(checkout=checkout, home=checkout / "home", run=default_command_runner)


def _write_checkout(*, tmp_path: Path, jsonc: str, beads: str | None = None) -> Path:
    """Materialize `.livespec.jsonc` (and optionally `.beads/config.yaml`) into the checkout."""
    (tmp_path / ".livespec.jsonc").write_text(jsonc, encoding="utf-8")
    if beads is not None:
        (tmp_path / ".beads").mkdir(exist_ok=True)
        (tmp_path / ".beads" / "config.yaml").write_text(beads, encoding="utf-8")
    return tmp_path


def _fleet_ctx(*, jsonc_text: str, beads_text: str) -> FleetContext:
    """A canned-response `FleetContext` serving the two connection sources for `widget`."""
    accept = ("-H", "Accept: application/vnd.github.raw")
    beads_args = ("api", "repos/acme/widget/contents/.beads/config.yaml?ref=master", *accept)
    jsonc_args = ("api", "repos/acme/widget/contents/.livespec.jsonc?ref=master", *accept)
    table = {
        beads_args: GhResult(returncode=0, stdout=beads_text, stderr=""),
        jsonc_args: GhResult(returncode=0, stdout=jsonc_text, stderr=""),
    }

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def test_absent_config_is_warning(*, tmp_path: Path) -> None:
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "harnesses" in outcome.message


def test_unparseable_config_is_warning(*, tmp_path: Path) -> None:
    checkout = _write_checkout(tmp_path=tmp_path, jsonc="{ this is not valid json ::: ")
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "fix it by hand" in outcome.message


def test_non_object_root_is_warning(*, tmp_path: Path) -> None:
    checkout = _write_checkout(tmp_path=tmp_path, jsonc="[1, 2, 3]\n")
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"


def test_no_harnesses_is_warning(*, tmp_path: Path) -> None:
    checkout = _write_checkout(tmp_path=tmp_path, jsonc=_CONFIG_NO_HARNESSES)
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "harnesses" in outcome.message


def test_empty_harnesses_is_warning(*, tmp_path: Path) -> None:
    checkout = _write_checkout(tmp_path=tmp_path, jsonc=_CONFIG_EMPTY_HARNESSES)
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"


def test_not_beads_backed_passes(*, tmp_path: Path) -> None:
    checkout = _write_checkout(tmp_path=tmp_path, jsonc=_CONFIG_NO_CONNECTION)
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowPass)
    assert "not beads-backed" in outcome.note


def test_no_dolt_keys_passes(*, tmp_path: Path) -> None:
    checkout = _write_checkout(
        tmp_path=tmp_path, jsonc=_CONFIG_NO_CONNECTION, beads=_BEADS_NO_DOLT_KEYS
    )
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowPass)
    assert "no dolt.* connection keys" in outcome.note


def test_connection_absent_is_machine_filled(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    checkout = _write_checkout(tmp_path=tmp_path, jsonc=_CONFIG_NO_CONNECTION, beads=_BEADS_FULL)
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowPass)
    assert "machine-filled" in outcome.note

    written = (checkout / ".livespec.jsonc").read_text(encoding="utf-8")
    # The comment-bearing config is preserved (a re-serialize would have lost it).
    assert "// hermetic test config" in written
    # The written bytes re-parse cleanly as JSONC.
    document = parse_document(text=written)
    assert isinstance(document, Success)
    # The five connection keys carry the `.beads/config.yaml` values (port a number).
    connection = named_plugin_connection(document=document.unwrap())
    assert connection == Success(
        {
            "server_host": "127.0.0.1",
            "server_port": 3307,
            "server_user": "widget",
            "database": "widget",
            "prefix": "widget",
        }
    )
    # And the central consistency assert passes on the written result.
    member = FleetMember(repo="widget", repo_class="impl-plugin")
    ctx = _fleet_ctx(jsonc_text=written, beads_text=_BEADS_FULL)
    assert assert_tenant_connection_consistency(ctx=ctx, member=member) == RowPass()


def test_fill_renders_only_beads_keys_present(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    checkout = _write_checkout(
        tmp_path=tmp_path, jsonc=_CONFIG_NO_CONNECTION, beads=_BEADS_MISSING_PREFIX
    )
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowPass)

    written = (checkout / ".livespec.jsonc").read_text(encoding="utf-8")
    document = parse_document(text=written)
    assert isinstance(document, Success)
    connection = named_plugin_connection(document=document.unwrap())
    assert isinstance(connection, Success)
    filled = connection.unwrap()
    assert filled is not None
    # `dolt.prefix` was absent from the beads config, so it is NOT fabricated.
    assert set(filled) == {"server_host", "server_port", "server_user", "database"}


def test_impl_block_unlocatable_no_implementation_is_warning(*, tmp_path: Path) -> None:
    checkout = _write_checkout(
        tmp_path=tmp_path, jsonc=_CONFIG_NO_IMPLEMENTATION, beads=_BEADS_FULL
    )
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "author the connection block by hand" in outcome.message


def test_impl_block_unlocatable_ghost_plugin_is_warning(*, tmp_path: Path) -> None:
    checkout = _write_checkout(tmp_path=tmp_path, jsonc=_CONFIG_GHOST_PLUGIN, beads=_BEADS_FULL)
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "author the connection block by hand" in outcome.message


def test_connection_drift_is_warning(*, tmp_path: Path) -> None:
    checkout = _write_checkout(tmp_path=tmp_path, jsonc=_CONFIG_DRIFT, beads=_BEADS_FULL)
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "server_port" in outcome.message
    assert "assert_tenant_connection_consistency" in outcome.message
    # An existing (possibly customized) connection block is never auto-edited.
    assert (checkout / ".livespec.jsonc").read_text(encoding="utf-8") == _CONFIG_DRIFT


def test_connection_consistent_passes(*, tmp_path: Path) -> None:
    checkout = _write_checkout(tmp_path=tmp_path, jsonc=_CONFIG_CONSISTENT, beads=_BEADS_FULL)
    outcome = reconcile_livespec_jsonc_complete(ctx=_local_ctx(checkout=checkout))
    assert isinstance(outcome, RowPass)
    assert "connection consistent" in outcome.note
