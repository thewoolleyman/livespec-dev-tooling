"""Baseline `.livespec.jsonc` declaration obligation rows for the fleet contract.

Two rows, both asserting that a governed member DECLARES something in
`.livespec.jsonc` rather than leaving a reader to infer it: its agent-runtime
`harnesses`, and its `dispatcher.acceptance_mode`. They share this module
because they share the read and its failure taxonomy (`_absent_or_unreadable`),
and because they are the same kind of obligation — closing a hole where saying
nothing is indistinguishable from having decided.

The Conformance Pattern's cross-harness plugin-resolution concern
(concern #2) requires every governed repo to DECLARE its agent-runtime
harnesses in `.livespec.jsonc` under a top-level `harnesses` object —
each harness marked `supported` (with a `canonical_command`) or `exempt`
(with a `reason`). The per-repo `check-plugin-resolution` Verifier reads
that declaration at commit time; this fleet-time row reports, from the
central vantage point, whether a member carries the declaration at all,
so an un-backfilled member is surfaced across the whole fleet.

Reports at ERROR severity (the M6-g required-key flip, livespec-zs22.7.7):
every governed repo now declares `harnesses`, so an absent declaration is a
hard fleet-conformance failure (exit 4) rather than an advisory warning —
the fleet-conformance sweep and the release fan-out preflight both gate on
error-severity findings.

Per the fleet contract's can't-read-is-not-absent discipline, a member
whose `.livespec.jsonc` is transiently unreadable, unparseable, or not a
JSON object yields a skip rather than a false finding. A GENUINELY-absent
`.livespec.jsonc` is the exception: proven via the member's master tree (a
readable, non-truncated tree that does not list the file), it is an ERROR
finding — the vacuous-pass closure (livespec-zs22.8 M3), which stops a
config-less governed member from passing the conformance net vacuously.
`.livespec.jsonc` is parsed with the vendored `jsoncomment`, mirroring
`_rows_beads` and `contract`.

The acceptance-mode row closes the same shape of hole one level down.
`resolve_acceptance_mode` returns `ai-then-human` for an absent key, so a
member that declares nothing behaves identically to one that chose that
policy deliberately, and no reader can tell which happened. Five governed
repos drifted off the fleet standard exactly that way before 2026-07-29.
The row therefore requires the DECLARATION and not any particular value: a
deliberate `ai-then-human` passes, silence does not.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._connection import impl_plugin_name
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
    "ACCEPTANCE_MODES",
    "LIVESPEC_JSONC_PATH",
    "assert_acceptance_mode_declared",
    "assert_baseline_harnesses",
]


LIVESPEC_JSONC_PATH = ".livespec.jsonc"
# The three acceptance policies `resolve_acceptance_mode` recognizes
# (livespec-orchestrator-beads-fabro's `_dispatcher_policy_settings`
# `_ACCEPTANCE_POLICIES`). Held here as a literal rather than imported:
# dev-tooling is UPSTREAM of the orchestrator plugin and must not read
# into a downstream consumer. The lockstep is asserted by a test.
ACCEPTANCE_MODES = frozenset(("ai-only", "ai-then-human", "human-only"))
_ACCEPTANCE_MODE_KEY = "acceptance_mode"
# Distinguishes "the lookup path broke before the key" from "the key is
# absent", which a bare `None` cannot: `None` is also what an absent key
# yields, and the two need different operator guidance.
_UNREACHABLE = object()


def _declared_acceptance_mode(*, document: dict[str, object]) -> object:
    """The impl-plugin block's `dispatcher.acceptance_mode` value, or a marker.

    Returns `_UNREACHABLE` when the lookup cannot even get as far as the
    key — no `implementation.plugin`, no block of that name, or no
    `dispatcher` object inside it — so the caller can say WHICH link
    broke instead of reporting every shape as "no acceptance_mode". A
    reachable-but-absent key returns `None`, which is distinguishable
    because `None` is not a legal declared value.
    """
    plugin = impl_plugin_name(document=document)
    if plugin is None:
        return _UNREACHABLE
    block = document.get(plugin)
    if not isinstance(block, dict):
        return _UNREACHABLE
    dispatcher = cast("dict[str, object]", block).get("dispatcher")
    if not isinstance(dispatcher, dict):
        return _UNREACHABLE
    return cast("dict[str, object]", dispatcher).get(_ACCEPTANCE_MODE_KEY)


def _acceptance_finding(*, repo: str, declared: object) -> RowFinding | None:
    """The finding `declared` earns, or None when it is a legible declaration.

    Three distinct failures, deliberately worded apart so the operator is
    sent to the right edit: the lookup path never reached the key, the key
    is absent, or the key carries a value the resolver does not recognize.
    """
    if declared is _UNREACHABLE:
        return RowFinding(
            message=(
                f"{repo}: no `dispatcher.acceptance_mode` is reachable in {LIVESPEC_JSONC_PATH} "
                "— the `implementation.plugin` key, its named block, or that block's "
                "`dispatcher` object is missing, so the acceptance policy cannot be declared"
            ),
            severity="error",
        )
    if declared is None:
        return RowFinding(
            message=(
                f"{repo}: {LIVESPEC_JSONC_PATH} declares no `dispatcher.acceptance_mode` — the "
                "resolver would silently default to `ai-then-human`, making the omission "
                "indistinguishable from a deliberate choice"
            ),
            severity="error",
        )
    if declared not in ACCEPTANCE_MODES:
        return RowFinding(
            message=(
                f"{repo}: `dispatcher.acceptance_mode` is {declared!r}, which is not one of "
                f"{sorted(ACCEPTANCE_MODES)} — the resolver silently falls back to its default "
                "for an unrecognized value, so this reads as a declaration but behaves as an "
                "omission"
            ),
            severity="error",
        )
    return None


def assert_acceptance_mode_declared(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member declares `dispatcher.acceptance_mode` explicitly and legibly.

    The obligation is a DECLARATION, not a value: a member that
    deliberately declares `ai-then-human` passes. Only silence fails.
    That asymmetry is the point — `resolve_acceptance_mode` returns
    `ai-then-human` for an absent key, so an omission and a deliberate
    choice produce identical behavior and nothing distinguishes them.

    A value outside `ACCEPTANCE_MODES` is also a finding: the resolver
    silently falls back to its default for an unrecognized string, so a
    typo reads as a declaration while behaving as an omission.

    The block is located through the document's own `implementation.plugin`
    name, so this upstream check carries no downstream plugin string. A
    member that names no impl plugin is a FINDING rather than a skip:
    skipping would make deleting that key a way to buy exemption. The
    read-failure shapes (absent, unreadable, unparseable, non-object root)
    are handled exactly as for `assert_baseline_harnesses`.
    """
    text = ctx.file_text(repo=member.repo, path=LIVESPEC_JSONC_PATH)
    if text is None:
        return _absent_or_unreadable(ctx=ctx, member=member)
    try:
        raw = cast("object", jsoncomment.loads(text))
    except ValueError:
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} is not valid JSONC")
    if not isinstance(raw, dict):
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} root is not a JSON object")
    declared = _declared_acceptance_mode(document=cast("dict[str, object]", raw))
    finding = _acceptance_finding(repo=member.repo, declared=declared)
    return finding if finding is not None else RowPass()


def _absent_or_unreadable(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Resolve a `None` contents read into a genuine-absence finding or a skip.

    The contents API returned nothing — but `None` conflates "the file is
    genuinely absent on master" with "the read failed transiently". The
    member's recursive master tree disambiguates them: when the tree is
    READABLE, NOT truncated, and does NOT list `.livespec.jsonc`, the file is
    genuinely absent — a governed manifest member with no config, the
    vacuous-pass hole the conformance net used to skip past (livespec-zs22.8
    M3). That is an ERROR finding, not a skip. Every other shape (tree
    unreadable, tree truncated so absence is unprovable, or the file present
    but its contents read failed) is can't-read-is-not-absent → SKIP.
    """
    tree = ctx.tree(repo=member.repo)
    if tree.readable and not tree.truncated and LIVESPEC_JSONC_PATH not in tree.paths:
        return RowFinding(
            message=(
                f"{member.repo}: no {LIVESPEC_JSONC_PATH} (a governed member MUST carry a "
                "harnesses-bearing config; a config-less member passed the conformance net "
                "vacuously — vacuous-pass closure, livespec-zs22.8 M3)"
            ),
            severity="error",
        )
    return RowSkip(
        reason=(
            f"{member.repo}: {LIVESPEC_JSONC_PATH} unreadable or its absence is unprovable "
            "(can't-read is not absent)"
        )
    )


def assert_baseline_harnesses(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member declares a non-empty `harnesses` object in `.livespec.jsonc`.

    A GENUINELY-ABSENT `.livespec.jsonc` on a governed manifest member is an
    ERROR finding (the vacuous-pass closure, livespec-zs22.8 M3): the
    conformance net used to skip a config-less member, letting it pass
    vacuously. Genuine absence is proven via the member's master tree (a
    readable, non-truncated tree that does not list the file); a transiently
    unreadable read stays a skip (can't-read is not absent). A member whose
    `.livespec.jsonc` is unparseable or not a JSON object also skips. A
    readable document carrying a non-empty top-level `harnesses` object passes;
    one missing it yields an ERROR-severity finding (the declaration is
    required fleet-wide since M6).
    """
    text = ctx.file_text(repo=member.repo, path=LIVESPEC_JSONC_PATH)
    if text is None:
        return _absent_or_unreadable(ctx=ctx, member=member)
    try:
        raw = cast("object", jsoncomment.loads(text))
    except ValueError:
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} is not valid JSONC")
    if not isinstance(raw, dict):
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} root is not a JSON object")
    harnesses = cast("dict[str, object]", raw).get("harnesses")
    if isinstance(harnesses, dict) and harnesses:
        return RowPass()
    return RowFinding(
        message=(
            f"{member.repo}: {LIVESPEC_JSONC_PATH} declares no `harnesses` object "
            "(Conformance Pattern concern #2 — required fleet-wide since zs22.7.7 M6)"
        ),
        severity="error",
    )
