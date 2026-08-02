"""LOCAL-vantage `.livespec.jsonc` completeness row for the fleet contract.

The local first-touch reconcile guarantees a `harnesses`-bearing
`.livespec.jsonc` and machine-fills the beads tenant `connection` block
from `.beads/config.yaml` on a target checkout (livespec-zs22.8 M6). It
walks one row's worth of semantics, in order:

1. `.livespec.jsonc` absent → a WARNING-severity finding guiding the
   operator to author a `harnesses`-bearing config. The `harnesses`
   statuses are a human-judgment seam the verb NEVER fabricates.
2. The file is unparseable as JSONC, or its root is not a JSON object →
   a WARNING-severity "fix by hand" finding NAMING which of the two it
   was (the verb never auto-edits a broken config).
3. No non-empty top-level `harnesses` object → a WARNING-severity
   finding guiding the operator to author `harnesses` (human-judgment
   seam).
4. `harnesses` present but the checkout carries no `.beads/config.yaml`
   → PASS (config complete; nothing to fill — the repo is not
   beads-backed).
5. `.beads/config.yaml` present but carries none of the five `dolt.*`
   connection keys → PASS (config complete; no connection to fill).
6. beads-backed and the impl-plugin `connection` block is ABSENT →
   machine-fill it from `.beads/config.yaml` and PASS. Three separately
   worded WARNING-severity "author by hand" findings stand in front of
   that fill, one per way it can be unsafe: the `implementation.plugin`
   link is broken, the block it names is not usable (including a
   `connection` that is PRESENT and not an object), or the block key has
   no line-anchor in the raw text. Those three shared one sentinel before
   the railway conversion, and the middle one was a fail-WRONG: a
   malformed `connection` read as an absence, so the fill wrote a SECOND
   `connection` key into the block.
7. The `connection` block is PRESENT but one or more of the five fields
   disagree with `.beads/config.yaml` → a WARNING-severity drift finding
   (never auto-edit a possibly-customized existing block; the central
   `assert_tenant_connection_consistency` governs agreement).
8. The `connection` block is present and all five fields agree → PASS.

The connection block is NON-SECRET (host/port/user/database/prefix); the
tenant PASSWORD is never touched (it stays the beads-tenant-secret
warning row). The fill is a TARGETED raw-text insertion, never a
re-serialize: `jsoncomment` only READS (strips comments), so re-emitting
the document with `json.dumps` would destroy the heavily-commented
config. The insertion is line-anchored on the impl-plugin block's
opening brace so it cannot match a `//`-comment line, preserves the
file's 2-space indentation, and re-parses cleanly.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._connection import (  # noqa: E402
    BEADS_CONFIG_PATH,
    CONNECTION_FIELD_PAIRS,
    LIVESPEC_JSONC_PATH,
    impl_plugin_name,
    mismatched_keys,
    named_plugin_connection,
    parse_beads_config,
    parse_document,
)
from livespec_dev_tooling.fleet._context import (  # noqa: E402
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._local_context import LocalContext  # noqa: E402

__all__: list[str] = ["reconcile_livespec_jsonc_complete"]


# An integer literal renders as a bare JSON number (the port); everything
# else (host, user, database, prefix) renders as a quoted JSON string.
_INT_LITERAL = re.compile(r"-?\d+")
# One indentation level in the canonical 2-space `.livespec.jsonc` style.
_INDENT_STEP = "  "


def _has_harnesses(*, document: dict[str, object]) -> bool:
    """True when the document carries a non-empty top-level `harnesses` object."""
    harnesses = document.get("harnesses")
    return isinstance(harnesses, dict) and len(cast("dict[str, object]", harnesses)) > 0


def _render_value(*, value: str) -> str:
    """Render a `.beads/config.yaml` string value as JSON: int-literal bare, else quoted."""
    if _INT_LITERAL.fullmatch(value):
        return json.dumps(int(value))
    return json.dumps(value)


def _fill_connection(*, text: str, plugin: str, beads: dict[str, str]) -> str | None:
    """Insert a `connection` block into the impl-plugin block, returning new text or None.

    None when the ALREADY-RESOLVED block key is not found by the
    line-anchored regex — ONE condition, down from two. The caller resolves
    `implementation.plugin` on the railway now and passes the name in, so
    an unresolvable link never reaches here and is never spelled the same
    way as a raw-text miss. The regex anchors on line-start + indentation +
    the block key + `: {`, so it cannot match a `//`-comment line. The
    anchor is LINE-START, not brace adjacency — `\\s*` spans newlines, so a
    block key and its `{` on separate lines still match; what misses is a
    block key with anything else before it on its line, which is what a
    compact one-line config produces. The inserted `connection` object
    becomes the block's FIRST
    member, indented one level deeper than the block key, with only the
    fields `.beads/config.yaml` actually carries.
    """
    pattern = re.compile(r'^(?P<indent>[ \t]*)"' + re.escape(plugin) + r'"\s*:\s*\{', re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        return None
    member_indent = match.group("indent") + _INDENT_STEP
    inner_indent = member_indent + _INDENT_STEP
    fields = [
        f"{inner_indent}{json.dumps(connection_key)}: {_render_value(value=beads[beads_key])}"
        for beads_key, connection_key in CONNECTION_FIELD_PAIRS
        if beads_key in beads
    ]
    block = f'\n{member_indent}"connection": {{\n' + ",\n".join(fields) + f"\n{member_indent}}},"
    insert_at = match.end()
    return text[:insert_at] + block + text[insert_at:]


def reconcile_livespec_jsonc_complete(*, ctx: LocalContext) -> RowOutcome:
    """Guarantee a `harnesses`-bearing `.livespec.jsonc` and fill the beads connection.

    Detect-and-guides an absent / unparseable / `harnesses`-less config
    (human-judgment seams the verb never fabricates) and machine-fills an
    absent impl-plugin `connection` block from `.beads/config.yaml`; an
    existing connection block is left untouched (consistent → pass;
    drifted → a warning that defers to the central consistency row).
    """
    jsonc_path = ctx.checkout / LIVESPEC_JSONC_PATH
    read = ctx.file_text(path=jsonc_path)
    if isinstance(read, IOFailure):
        # can't-read is not absent. The `exists()` pre-check this replaces
        # returned True for a DIRECTORY, so the read below raised
        # `IsADirectoryError` uncaught and aborted the whole reconcile
        # partway through (livespec-dev-tooling-a6et).
        return RowSkip(
            reason=f".livespec.jsonc unreadable ({unsafe_perform_io(read.failure()).kind})"
        )
    text = unsafe_perform_io(read.unwrap())
    if text is None:
        return RowFinding(
            severity="warning",
            message=(
                ".livespec.jsonc absent: author a harnesses-bearing .livespec.jsonc — declare a "
                "non-empty top-level `harnesses` object (a human-judgment seam the verb never "
                "fabricates), plus the impl-plugin block the beads connection is filled into"
            ),
        )
    parsed = parse_document(text=text)
    if isinstance(parsed, Failure):
        return RowFinding(
            severity="warning",
            message=(
                f".livespec.jsonc does not yield a JSON object map ({parsed.failure().detail}): "
                "fix it by hand (the verb never auto-edits a broken config)"
            ),
        )
    document = parsed.unwrap()
    if not _has_harnesses(document=document):
        return RowFinding(
            severity="warning",
            message=(
                ".livespec.jsonc declares no `harnesses` object: author a non-empty top-level "
                "`harnesses` object (Conformance Pattern concern #2 cross-harness "
                "plugin-resolution; a human-judgment seam the verb never fabricates)"
            ),
        )
    return _beads_stage(ctx=ctx, jsonc_path=jsonc_path, text=text, document=document)


def _beads_stage(
    *, ctx: LocalContext, jsonc_path: Path, text: str, document: dict[str, object]
) -> RowOutcome:
    """Resolve `.beads/config.yaml` and reconcile the connection from it.

    Extracted when the second file read pushed
    `reconcile_livespec_jsonc_complete` past PLR0911's six-return cap. The
    cap was PAID rather than routed around, and the split earns its keep:
    the caller now reads as "validate the document", this reads as "apply
    the beads config", and the row's two file reads sit one per function
    instead of two in one.
    """
    beads_read = ctx.file_text(path=ctx.checkout / BEADS_CONFIG_PATH)
    if isinstance(beads_read, IOFailure):
        # The SECOND instance of the same pre-check pair in this one row, and
        # the same crash: `exists()` is True for a directory, so the read
        # raised uncaught. Absent stays a PASS below; unreadable is a skip.
        return RowSkip(
            reason=f".beads/config.yaml unreadable ({unsafe_perform_io(beads_read.failure()).kind})"
        )
    beads_text = unsafe_perform_io(beads_read.unwrap())
    if beads_text is None:
        return RowPass(note="config complete; not beads-backed")
    beads = parse_beads_config(text=beads_text)
    if not any(beads_key in beads for beads_key, _ in CONNECTION_FIELD_PAIRS):
        return RowPass(note="config complete; no dolt.* connection keys")
    return _reconcile_connection(jsonc_path=jsonc_path, text=text, document=document, beads=beads)


def _reconcile_connection(
    *, jsonc_path: Path, text: str, document: dict[str, object], beads: dict[str, str]
) -> RowOutcome:
    """Machine-fill an absent connection block, or report drift / consistency.

    An ABSENT impl-plugin connection block is machine-filled from
    `.beads/config.yaml` and the file rewritten (or a warning when the
    impl-plugin block cannot be located). An EXISTING block is never
    auto-edited: it passes when all five fields agree and warns (deferring
    to the central consistency row) when one or more disagree.
    """
    plugin = impl_plugin_name(document=document)
    if isinstance(plugin, Failure):
        return RowFinding(
            severity="warning",
            message=(
                f".livespec.jsonc impl-plugin link is broken ({plugin.failure().detail}), so the "
                "block to insert a connection into cannot be identified: author the connection "
                "block by hand"
            ),
        )
    found = named_plugin_connection(document=document)
    if isinstance(found, Failure):
        return RowFinding(
            severity="warning",
            message=(
                f".livespec.jsonc impl-plugin block is not usable ({found.failure().detail}): "
                "author the connection block by hand"
            ),
        )
    connection = found.unwrap()
    if connection is None:
        filled = _fill_connection(text=text, plugin=plugin.unwrap(), beads=beads)
        if filled is None:
            return RowFinding(
                severity="warning",
                message=(
                    ".livespec.jsonc impl-plugin block key was not found in the raw text, so the "
                    "connection insertion has no anchor: author the connection block by hand"
                ),
            )
        _ = jsonc_path.write_text(filled, encoding="utf-8")
        return RowPass(note="machine-filled connection block from .beads/config.yaml")
    drifted = mismatched_keys(beads=beads, connection=connection)
    if drifted:
        return RowFinding(
            severity="warning",
            message=(
                f"connection drift on {', '.join(drifted)} — fix by hand; the central "
                "assert_tenant_connection_consistency governs agreement"
            ),
        )
    return RowPass(note="config complete; connection consistent")
