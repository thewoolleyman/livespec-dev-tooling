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
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "BEADS_CONFIG_PATH",
    "CONNECTION_FIELD_PAIRS",
    "LIVESPEC_JSONC_PATH",
    "DocumentDefect",
    "ImplPluginUnresolved",
    "connection_block",
    "impl_plugin_name",
    "mismatched_keys",
    "named_plugin_connection",
    "parse_beads_config",
    "parse_document",
]


@dataclass(frozen=True, kw_only=True)
class DocumentDefect:
    """`.livespec.jsonc` text that does not yield a top-level object map.

    Two shapes: bytes that are not parseable as JSONC, and a document that
    parses but whose root is not a JSON object. ONE type rather than two
    because no caller BRANCHES on the difference — both are "fix it by
    hand, the verb never auto-edits a broken config" — and the two are
    told apart by `detail`, which the caller renders. Contrast
    `PinFileUnreadable` / `PinFileUnparseable`, which ARE two types
    precisely because their rows render them as a skip and a finding
    respectively (livespec-dev-tooling-2j2l).
    """

    detail: str


@dataclass(frozen=True, kw_only=True)
class ImplPluginUnresolved:
    """The `implementation.plugin` link, or the block it names, is broken.

    Seven distinct conditions reach here, and before the conversion all
    seven shared one `None` with a legitimate absence. `_rows_baseline`
    already wanted them apart — its `_UNREACHABLE` marker exists so the
    operator learns "WHICH link broke" — and could not have them, because
    the information died at this module's boundary. `detail` names the
    broken link.
    """

    detail: str


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


def parse_document(*, text: str) -> Result[dict[str, object], DocumentDefect]:
    """Parse JSONC `text` into its top-level object map.

    Both "fix by hand" shapes a writer must never auto-edit leave on the
    FAILURE track, named apart: text that is not parseable as JSONC, and a
    document whose root is not a JSON object. They shared one `None`
    before the conversion, so the caller sent the operator to two possible
    edits in one message.
    """
    try:
        raw = cast("object", jsoncomment.loads(text))
    except ValueError as undecodable:
        return Failure(DocumentDefect(detail=f"not parseable as JSONC: {undecodable}"))
    if not isinstance(raw, dict):
        return Failure(
            DocumentDefect(detail=f"the document root is {type(raw).__name__}, not a JSON object")
        )
    return Success(cast("dict[str, object]", raw))


def impl_plugin_name(*, document: dict[str, object]) -> Result[str, ImplPluginUnresolved]:
    """The `implementation.plugin` block name from a parsed document.

    FOUR distinct broken links, each named rather than collapsed onto one
    sentinel: `implementation` absent, `implementation` not an object,
    `plugin` absent, `plugin` not a string.
    """
    implementation = document.get("implementation")
    if implementation is None:
        return Failure(
            ImplPluginUnresolved(detail="the document declares no `implementation` block")
        )
    if not isinstance(implementation, dict):
        return Failure(
            ImplPluginUnresolved(
                detail=f"`implementation` is {type(implementation).__name__}, not an object"
            )
        )
    plugin = cast("dict[str, object]", implementation).get("plugin")
    if plugin is None:
        return Failure(ImplPluginUnresolved(detail="`implementation` declares no `plugin` key"))
    if not isinstance(plugin, str):
        return Failure(
            ImplPluginUnresolved(
                detail=f"`implementation.plugin` is {type(plugin).__name__}, not a string"
            )
        )
    return Success(plugin)


def named_plugin_connection(
    *, document: dict[str, object]
) -> Result[dict[str, object] | None, ImplPluginUnresolved]:
    """The `connection` dict of the `implementation.plugin`-named block.

    `Success(None)` is an ANSWER carrying exactly ONE condition — the
    resolved block declares no `connection` — and it is the state the
    local reconcile row machine-fills from `.beads/config.yaml`. Every
    other condition is a broken link on the failure track: the four
    `impl_plugin_name` propagates, plus the named block being absent or
    not an object, plus a `connection` that is PRESENT and not an object.

    That last one was a fail-WRONG rather than a fail-open. It read as
    "no connection block", so the reconcile row machine-filled one into a
    block that already had a `connection` key and wrote a SECOND.
    """
    plugin = impl_plugin_name(document=document)
    if isinstance(plugin, Failure):
        return Failure(plugin.failure())
    name = plugin.unwrap()
    block = document.get(name)
    if block is None:
        return Failure(
            ImplPluginUnresolved(
                detail=f"`implementation.plugin` names `{name}`, which is not a top-level block"
            )
        )
    if not isinstance(block, dict):
        return Failure(
            ImplPluginUnresolved(
                detail=f"top-level `{name}` is {type(block).__name__}, not an object"
            )
        )
    connection = cast("dict[str, object]", block).get("connection")
    if connection is None:
        return Success(None)
    if not isinstance(connection, dict):
        return Failure(
            ImplPluginUnresolved(
                detail=f"`{name}.connection` is {type(connection).__name__}, not an object"
            )
        )
    return Success(cast("dict[str, object]", connection))


def connection_block(*, text: str) -> Result[dict[str, object] | None, DocumentDefect]:
    """The `connection` dict from a member's `.livespec.jsonc`.

    Finds the impl-plugin block named by `implementation.plugin` and
    returns its `connection` dict; falls back to scanning every top-level
    block for one carrying a `connection` dict.

    ⛔ THE FALLBACK IS AN ANSWER, NOT A SWALLOWED FAILURE. A broken
    `implementation.plugin` link is exactly what the scan exists for — a
    document with no well-formed impl-plugin declaration may still carry a
    connection block — so `named_plugin_connection`'s failure is answered
    by scanning rather than propagated, and the scan then answers
    definitively. Only an UNUSABLE DOCUMENT fails here: nothing can be
    concluded from bytes that do not parse.

    `Success(None)` means the walk completed and genuinely found no
    connection block — the member is not beads-backed.
    """
    document = parse_document(text=text)
    if isinstance(document, Failure):
        return Failure(document.failure())
    parsed = document.unwrap()
    named = named_plugin_connection(document=parsed)
    if isinstance(named, Success) and named.unwrap() is not None:
        return Success(named.unwrap())
    for value in parsed.values():
        if isinstance(value, dict):
            connection = cast("dict[str, object]", value).get("connection")
            if isinstance(connection, dict):
                return Success(cast("dict[str, object]", connection))
    return Success(None)


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
