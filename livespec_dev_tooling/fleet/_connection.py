"""Shared tenant-connection helpers for the two `.beads`/`.livespec.jsonc` rows.

A beads-backed member duplicates its per-repo Dolt tenant connection in
TWO committed files: `.beads/config.yaml` (read by the `bd` CLI; flat
dotted keys `dolt.server-host`, `dolt.server-port`, `dolt.server-user`,
`dolt.database`, `dolt.prefix`) AND `.livespec.jsonc`'s impl-plugin
`connection` block (read by the plugin; keys `server_host`,
`server_port`, `server_user`, `database`, `prefix`). Two rows reason over
that pair from different vantages:

- The CENTRAL `assert_tenant_connection_consistency`
  (`_rows_beads`) asserts the five pairs agree across the fleet from the
  GitHub vantage, making drift un-mergeable.
- The LOCAL `reconcile_livespec_jsonc_complete` (`_rows_local_jsonc`)
  machine-fills an absent impl-plugin `connection` block from
  `.beads/config.yaml` on a target checkout.

Both consume the same parse/lookup/compare primitives, so they live here
as PUBLIC names a sibling module imports directly — no cross-module
`_`-prefixed call for the `check-private-calls` gate to flag.

`.beads/config.yaml` is flat dotted-key YAML (`dolt.server-host:
127.0.0.1`), so it is parsed with a line-walk rather than pulling in a
YAML dependency (none is vendored). `.livespec.jsonc` is parsed with the
vendored `jsoncomment`, mirroring `contract.py` and
`workflow_checks/no_stale_revise_branches.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "BEADS_CONFIG_PATH",
    "CONNECTION_FIELD_PAIRS",
    "LIVESPEC_JSONC_PATH",
    "connection_block",
    "impl_plugin_name",
    "mismatched_keys",
    "named_plugin_connection",
    "parse_beads_config",
    "parse_document",
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


def parse_beads_config(*, text: str) -> dict[str, str]:
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


def parse_document(*, text: str) -> dict[str, object] | None:
    """Parse JSONC `text` into its top-level object map, or None when invalid.

    None when the text is unparseable as JSONC or its root is not a JSON
    object — the two "fix by hand" shapes a writer must never auto-edit.
    """
    try:
        raw = cast("object", jsoncomment.loads(text))
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    return cast("dict[str, object]", raw)


def impl_plugin_name(*, document: dict[str, object]) -> str | None:
    """The `implementation.plugin` block name from a parsed document, or None."""
    implementation = document.get("implementation")
    if not isinstance(implementation, dict):
        return None
    plugin = cast("dict[str, object]", implementation).get("plugin")
    if not isinstance(plugin, str):
        return None
    return plugin


def named_plugin_connection(*, document: dict[str, object]) -> dict[str, object] | None:
    """The `connection` dict of the `implementation.plugin`-named block, or None."""
    plugin = impl_plugin_name(document=document)
    if plugin is None:
        return None
    block = document.get(plugin)
    if not isinstance(block, dict):
        return None
    connection = cast("dict[str, object]", block).get("connection")
    if not isinstance(connection, dict):
        return None
    return cast("dict[str, object]", connection)


def connection_block(*, text: str) -> dict[str, object] | None:
    """The `connection` dict from a member's `.livespec.jsonc`, or None.

    Finds the impl-plugin block named by `implementation.plugin` and
    returns its `connection` dict; falls back to scanning every
    top-level block for one carrying a `connection` dict. None when the
    document is unparseable, not an object, or carries no connection
    block (the member is not beads-backed).
    """
    document = parse_document(text=text)
    if document is None:
        return None
    named = named_plugin_connection(document=document)
    if named is not None:
        return named
    for value in document.values():
        if isinstance(value, dict):
            connection = cast("dict[str, object]", value).get("connection")
            if isinstance(connection, dict):
                return cast("dict[str, object]", connection)
    return None


def mismatched_keys(*, beads: dict[str, str], connection: dict[str, object]) -> list[str]:
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
