"""LOCAL-vantage `.livespec.jsonc` completeness row for the fleet contract.

The local first-touch reconcile guarantees a `harnesses`-bearing
`.livespec.jsonc` and machine-fills the beads tenant `connection` block
from `.beads/config.yaml` on a target checkout (livespec-zs22.8 M6). It
walks one row's worth of semantics, in order:

1. `.livespec.jsonc` absent → a WARNING-severity finding guiding the
   operator to author a `harnesses`-bearing config. The `harnesses`
   statuses are a human-judgment seam the verb NEVER fabricates.
2. The file is unparseable as JSONC, or its root is not a JSON object →
   a WARNING-severity "fix by hand" finding (the verb never auto-edits a
   broken config).
3. No non-empty top-level `harnesses` object → a WARNING-severity
   finding guiding the operator to author `harnesses` (human-judgment
   seam).
4. `harnesses` present but the checkout carries no `.beads/config.yaml`
   → PASS (config complete; nothing to fill — the repo is not
   beads-backed).
5. `.beads/config.yaml` present but carries none of the five `dolt.*`
   connection keys → PASS (config complete; no connection to fill).
6. beads-backed and the impl-plugin `connection` block is ABSENT →
   machine-fill it from `.beads/config.yaml` and PASS. When the
   impl-plugin block cannot be located for the targeted insertion
   (`implementation.plugin` missing/not a string, or its block key not
   found in the raw text) → a WARNING-severity "author by hand" finding.
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
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._connection import (
    BEADS_CONFIG_PATH,
    CONNECTION_FIELD_PAIRS,
    LIVESPEC_JSONC_PATH,
    impl_plugin_name,
    mismatched_keys,
    named_plugin_connection,
    parse_beads_config,
    parse_document,
)
from livespec_dev_tooling.fleet._context import RowFinding, RowOutcome, RowPass
from livespec_dev_tooling.fleet._local_context import LocalContext

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


def _fill_connection(
    *, text: str, document: dict[str, object], beads: dict[str, str]
) -> str | None:
    """Insert a `connection` block into the impl-plugin block, returning new text or None.

    None when the impl-plugin block cannot be located for the targeted
    raw-text insertion: `implementation.plugin` missing/not a string, or
    its block key not found by the line-anchored regex. The regex anchors
    on line-start + indentation + the block key + `: {`, so it cannot
    match a `//`-comment line. The inserted `connection` object becomes
    the block's FIRST member, indented one level deeper than the block
    key, with only the fields `.beads/config.yaml` actually carries.
    """
    plugin = impl_plugin_name(document=document)
    if plugin is None:
        return None
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
    if not jsonc_path.exists():
        return RowFinding(
            severity="warning",
            message=(
                ".livespec.jsonc absent: author a harnesses-bearing .livespec.jsonc — declare a "
                "non-empty top-level `harnesses` object (a human-judgment seam the verb never "
                "fabricates), plus the impl-plugin block the beads connection is filled into"
            ),
        )
    text = jsonc_path.read_text(encoding="utf-8")
    document = parse_document(text=text)
    if document is None:
        return RowFinding(
            severity="warning",
            message=(
                ".livespec.jsonc is unparseable as JSONC or its root is not a JSON object: fix it "
                "by hand (the verb never auto-edits a broken config)"
            ),
        )
    if not _has_harnesses(document=document):
        return RowFinding(
            severity="warning",
            message=(
                ".livespec.jsonc declares no `harnesses` object: author a non-empty top-level "
                "`harnesses` object (Conformance Pattern concern #2 cross-harness "
                "plugin-resolution; a human-judgment seam the verb never fabricates)"
            ),
        )
    beads_path = ctx.checkout / BEADS_CONFIG_PATH
    if not beads_path.exists():
        return RowPass(note="config complete; not beads-backed")
    beads = parse_beads_config(text=beads_path.read_text(encoding="utf-8"))
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
    connection = named_plugin_connection(document=document)
    if connection is None:
        filled = _fill_connection(text=text, document=document, beads=beads)
        if filled is None:
            return RowFinding(
                severity="warning",
                message=(
                    ".livespec.jsonc impl-plugin block could not be located for connection "
                    "insertion (implementation.plugin missing/not a string, or its block key not "
                    "found in the raw text): author the connection block by hand"
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
