"""Beads tenant-connection obligation row for the fleet-membership contract.

A beads-backed member duplicates its per-repo Dolt tenant connection in
TWO committed files: `.beads/config.yaml` (read by the `bd` CLI; flat
dotted keys `dolt.server-host`, `dolt.server-port`, `dolt.server-user`,
`dolt.database`, `dolt.prefix`) AND `.livespec.jsonc`'s impl-plugin
`connection` block (read by the plugin; keys `server_host`,
`server_port`, `server_user`, `database`, `prefix`). The two are
authored independently, so they can silently drift (they did during the
orchestrator rename). This row asserts the five pairs agree from the
central fleet vantage point, making any drift un-mergeable.

Per the fleet contract's can't-read-is-not-absent discipline: a member
that lacks either file, or whose `.livespec.jsonc` carries no
`connection` block, is not beads-backed (or not yet wired) and yields a
skip — never a false red. Only a member with BOTH connection sources
present and a definite disagreement yields a finding.

`.beads/config.yaml` is flat dotted-key YAML (`dolt.server-host:
127.0.0.1`), so it is parsed with the same line-walk approach the
sibling `_rows_github.parse_ci_matrix` uses for ci.yml rather than
pulling in a YAML dependency (none is vendored). `.livespec.jsonc` is
parsed with the vendored `jsoncomment`, mirroring `contract.py` and
`workflow_checks/no_stale_revise_branches.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "BEADS_CONFIG_PATH",
    "CONNECTION_FIELD_PAIRS",
    "LIVESPEC_JSONC_PATH",
    "assert_tenant_connection_consistency",
]


BEADS_CONFIG_PATH = ".beads/config.yaml"
LIVESPEC_JSONC_PATH = ".livespec.jsonc"

# The five load-bearing tenant-connection fields, each as
# (`.beads/config.yaml` dotted key, `.livespec.jsonc` connection key).
# Both sources are normalized to strings before comparison so an int
# port in JSON and a bare-number port in YAML compare equal.
CONNECTION_FIELD_PAIRS: tuple[tuple[str, str], ...] = (
    ("dolt.server-host", "server_host"),
    ("dolt.server-port", "server_port"),
    ("dolt.server-user", "server_user"),
    ("dolt.database", "database"),
    ("dolt.prefix", "prefix"),
)

# A value must be at least an opening + closing quote to carry a quoted
# string worth stripping (the `_unquote` minimum length).
_MIN_QUOTED_LEN = 2


def _parse_beads_config(*, text: str) -> dict[str, str]:
    """Parse flat dotted-key YAML (`dolt.server-host: 127.0.0.1`) into a map.

    Only top-level `key: value` lines are read; comments (`#`) and blank
    lines are ignored. Values are stripped of surrounding whitespace and
    of a single layer of matching quotes so a quoted host compares equal
    to a bare one.
    """
    parsed: dict[str, str] = {}
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        parsed[key.strip()] = _unquote(value=value.strip())
    return parsed


def _unquote(*, value: str) -> str:
    """Strip one layer of matching single/double quotes from `value`."""
    if len(value) >= _MIN_QUOTED_LEN and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _connection_block(*, text: str) -> dict[str, object] | None:
    """The `connection` dict from a member's `.livespec.jsonc`, or None.

    Finds the impl-plugin block named by `implementation.plugin` and
    returns its `connection` dict; falls back to scanning every
    top-level block for one carrying a `connection` dict. None when the
    document is unparseable, not an object, or carries no connection
    block (the member is not beads-backed).
    """
    try:
        raw = cast("object", jsoncomment.loads(text))
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    document = cast("dict[str, object]", raw)
    named = _named_plugin_connection(document=document)
    if named is not None:
        return named
    for value in document.values():
        if isinstance(value, dict):
            connection = cast("dict[str, object]", value).get("connection")
            if isinstance(connection, dict):
                return cast("dict[str, object]", connection)
    return None


def _named_plugin_connection(*, document: dict[str, object]) -> dict[str, object] | None:
    """The `connection` dict of the `implementation.plugin`-named block, or None."""
    implementation = document.get("implementation")
    if not isinstance(implementation, dict):
        return None
    plugin = cast("dict[str, object]", implementation).get("plugin")
    if not isinstance(plugin, str):
        return None
    block = document.get(plugin)
    if not isinstance(block, dict):
        return None
    connection = cast("dict[str, object]", block).get("connection")
    if not isinstance(connection, dict):
        return None
    return cast("dict[str, object]", connection)


def _mismatched_keys(*, beads: dict[str, str], connection: dict[str, object]) -> list[str]:
    """The `.livespec.jsonc` keys whose value disagrees with `.beads/config.yaml`.

    Each side is normalized to a string before comparison so an int port
    in JSON and a bare-number port in YAML compare equal. A field absent
    from EITHER source counts as a disagreement (a half-declared
    connection is itself drift to surface).
    """
    mismatched: list[str] = []
    for beads_key, connection_key in CONNECTION_FIELD_PAIRS:
        beads_value = beads.get(beads_key)
        connection_raw = connection.get(connection_key)
        connection_value = None if connection_raw is None else str(connection_raw)
        if beads_value != connection_value:
            mismatched.append(connection_key)
    return mismatched


def assert_tenant_connection_consistency(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member's `.beads/config.yaml` and `.livespec.jsonc` connection agree.

    Skips a member lacking either file, lacking a `.livespec.jsonc`
    connection block, or whose `.beads/config.yaml` carries none of the
    `dolt.*` connection keys (not beads-backed / can't-read is not
    absent). Findings name every mismatched key.
    """
    beads_text = ctx.file_text(repo=member.repo, path=BEADS_CONFIG_PATH)
    if beads_text is None:
        return RowSkip(reason=f"{member.repo}: {BEADS_CONFIG_PATH} unreadable or absent")
    jsonc_text = ctx.file_text(repo=member.repo, path=LIVESPEC_JSONC_PATH)
    if jsonc_text is None:
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} unreadable or absent")
    beads = _parse_beads_config(text=beads_text)
    if not any(beads_key in beads for beads_key, _ in CONNECTION_FIELD_PAIRS):
        return RowSkip(
            reason=f"{member.repo}: {BEADS_CONFIG_PATH} carries no dolt.* connection keys"
        )
    connection = _connection_block(text=jsonc_text)
    if connection is None:
        return RowSkip(
            reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} carries no impl-plugin connection block"
        )
    mismatched = _mismatched_keys(beads=beads, connection=connection)
    if mismatched:
        return RowFinding(
            message=(
                f"{member.repo}: tenant connection drift between {BEADS_CONFIG_PATH} and "
                f"{LIVESPEC_JSONC_PATH} on key(s): {', '.join(mismatched)}"
            )
        )
    return RowPass()
