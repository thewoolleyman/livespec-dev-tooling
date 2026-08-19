"""justfile_canonical_reconcile — reconcile a consumer justfile's canonical check wiring.

Extracted (per the guard-fix below) from the embedded Python heredoc in
`.github/actions/bump-pin-rewrite/action.yml`'s "Reconcile canonical check
wiring" step. Per `SPECIFICATION/contracts.md` section "Cross-repo coordination
automation surface", when a bumped livespec-dev-tooling release adds a new
module under `livespec_dev_tooling/checks/`, the live canonical-check slug set
grows; a consumer that already runs `check-aggregate-completeness` MUST adopt
the new slug in the same bump commit, or its bump PR fails before the new check
can propagate. This module carries the two reconciliations that make that
adoption atomic:

- insert every canonical slug missing from the consumer's RESOLVED slug
  inventory (preserving canonical order and any existing indent); and
- append a zero-arg `check-<slug>:` recipe for each missing slug that has NO
  recipe header yet.

RESOLVED means what `aggregate_completeness` itself reads, and the resolution
order matters: a committed `check-targets.txt` is PRIMARY, and the justfile's
`targets=(...)` array is consulted only when that file is absent. Reconciling
the array alone left three of the fleet's eight Python consumers untouched --
`livespec-driver-codex` and `livespec-driver-pi`, whose `check:` recipe
delegates to a shell script, and `livespec-runtime` -- so their bump PRs failed
`check-aggregate-completeness` on the very bump meant to wire them, and each had
to be wired by hand. A consumer carrying BOTH sources has both updated: the file
because it is what the gate reads, the array because such a repo may also
enforce a literal mirror between the two.

The extraction fixes ONE latent bug in the recipe-presence guard. The
pre-extraction guard recognized a canonical slug's recipe ONLY when it was
defined as the BARE header `check-<slug>:`. Both Driver repos
(`livespec-driver-claude`, `livespec-driver-codex`) hand-define
`check-red-green-replay` in PARAMETERIZED form — `check-red-green-replay *args:`
(the aggregate calls it with no args; the pre-commit hook passes a message
path). The bare-only guard missed that form, so it appended a SECOND
`check-red-green-replay:` recipe; `just` then refused to parse the redefinition
and every `just check-*` failed in the consumer's CI. `recipe_header_present`
now recognizes any recipe-header form for the slug.

Output discipline mirrors the sibling `pin_autodiscovery` supervisor entry
point: the pure `reconcile_justfile_text` / `_reconcile` core does no I/O, and
`main()` owns the file read/write plus the GitHub Actions `::notice::`
annotations on stdout (declared in `pyproject.toml` `supervisor_entry_files`,
the surface `no_write_direct` exempts).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

# `returns` is VENDORED, not installed, so this module must put `_vendor/` on
# the path ITSELF. It is a `python -m` ENTRY POINT in the reusable bump-pin
# workflow, where nothing imports before it — a bare import worked in every
# test and killed the fan-out for seven of eight members.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.canonical_checks import canonical_check_renames  # noqa: E402
from livespec_dev_tooling.cross_repo._canonical_reconcile_parse import (  # noqa: E402
    check_recipe_bounds,
    insert_missing_targets,
    inventory_slugs,
    missing_recipe_chunks,
    reconcile_inventory_text,
    rewrite_renamed_references,
    targets_array_bounds,
    token_for,
)

__all__: list[str] = ["reconcile_inventory_text", "reconcile_justfile_text", "reconcile_sources"]


_JUSTFILE_NAME = "justfile"
# The consumer's committed canonical-slug inventory. `aggregate_completeness`
# reads THIS FIRST and only parses the justfile's `targets=(...)` array when the
# file is absent, so on a repo carrying both, the FILE is what the gate is
# actually gated on.
_INVENTORY_NAME = "check-targets.txt"
_AGGREGATE_SLUG = "check-aggregate-completeness"

# Skip-reason → GitHub Actions `::notice::` message, byte-identical to the
# pre-extraction embedded step's `print("::notice::...")` calls so the
# workflow-log annotations are unchanged.
_SKIP_NOTICES: dict[str, str] = {
    "no_aggregate": (
        "consumer does not carry check-aggregate-completeness; "
        "skipping canonical check wiring reconcile"
    ),
    "no_check_header": (
        "justfile has no bare check: recipe; skipping canonical check wiring reconcile"
    ),
    "no_targets_array": (
        "check: recipe has no targets=(...) array; skipping canonical check wiring reconcile"
    ),
    "unterminated_targets": (
        "check: recipe targets=(...) array is unterminated; "
        "skipping canonical check wiring reconcile"
    ),
}


@dataclass(frozen=True, kw_only=True)
class _ReconcileResult:
    """Outcome of one reconcile pass: reconciled text plus diagnostics.

    `text` is the reconciled justfile text (identical to the input when no
    change applies). `missing` lists the canonical slugs that were absent from
    the `targets=(...)` array (empty when none). `skipped_reason` names the
    early-exit branch when the justfile does not carry the reconcilable shape
    (None when a full reconcile ran). The two diagnostic fields let `main()`
    emit the right `::notice::` without re-deriving them.
    """

    text: str
    missing: tuple[str, ...]
    skipped_reason: str | None


def _reconcile(
    *,
    justfile_text: str,
    canonical_slugs: Sequence[str],
    renames: Sequence[tuple[str, str]] = (),
) -> _ReconcileResult:
    """Pure core — reconcile the consumer justfile text against the canonical slug set.

    First rewrites any wired slug the `renames` map strands (see
    `rewrite_renamed_references`), then inserts every canonical slug missing
    from the `check:` aggregate's `targets=(...)` array, then appends a
    zero-arg `check-<slug>:` recipe for each missing slug that has NO recipe
    header in any form. Returns the input unchanged with a `skipped_reason`
    when the justfile does not carry the reconcilable shape.
    """
    canonical = tuple(canonical_slugs)
    canonical_set = set(canonical)
    if _AGGREGATE_SLUG not in justfile_text:
        return _ReconcileResult(text=justfile_text, missing=(), skipped_reason="no_aggregate")

    justfile_text = rewrite_renamed_references(
        justfile_text=justfile_text, renames=renames, canonical_set=canonical_set
    )

    lines = justfile_text.splitlines(keepends=True)
    block = check_recipe_bounds(lines=lines)
    if block is None:
        return _ReconcileResult(text=justfile_text, missing=(), skipped_reason="no_check_header")
    check_header, recipe_end = block

    bounds = targets_array_bounds(lines=lines, check_header=check_header, recipe_end=recipe_end)
    if isinstance(bounds, str):
        return _ReconcileResult(text=justfile_text, missing=(), skipped_reason=bounds)
    targets_start, targets_end = bounds

    wired = {
        token
        for token in (token_for(line=line) for line in lines[targets_start + 1 : targets_end])
        if token is not None
    }
    missing = tuple(slug for slug in canonical if slug not in wired)

    insert_missing_targets(
        lines=lines,
        canonical_set=canonical_set,
        missing=missing,
        targets_start=targets_start,
        targets_end=targets_end,
    )
    reconstructed = "".join(lines)
    chunks = missing_recipe_chunks(justfile_text=reconstructed, missing=missing)
    return _ReconcileResult(
        text=reconstructed + "".join(chunks),
        missing=missing,
        skipped_reason=None,
    )


@dataclass(frozen=True, kw_only=True)
class _SourcesResult:
    """Outcome of reconciling BOTH canonical-slug sources a consumer may carry.

    `inventory_text` is None when the consumer has no `check-targets.txt` (the
    reconcile then concerns the justfile alone). `skipped_reason` is None when
    at least one source was reconcilable.
    """

    justfile_text: str
    inventory_text: str | None
    missing: tuple[str, ...]
    skipped_reason: str | None


def reconcile_sources(
    *,
    justfile_text: str,
    inventory_text: str | None,
    canonical_slugs: Sequence[str],
    renames: Sequence[tuple[str, str]] = (),
) -> _SourcesResult:
    """Reconcile every canonical-slug source the consumer carries.

    Resolution mirrors `aggregate_completeness` EXACTLY, which is the property
    that keeps writer and gate from drifting: `check-targets.txt` is PRIMARY
    when present, and the justfile's `targets=(...)` array is consulted only in
    its absence. A consumer carrying BOTH has both updated -- the file because
    it is what the gate reads, the array because a repo carrying both may also
    enforce a literal mirror between them.

    Recipes are appended for every missing slug lacking a recipe header, driven
    by the RESOLVED missing set, so a consumer whose aggregate delegates to a
    shell script still gains the recipes its inventory now names.
    """
    canonical = tuple(canonical_slugs)
    canonical_set = set(canonical)
    if inventory_text is None:
        result = _reconcile(justfile_text=justfile_text, canonical_slugs=canonical, renames=renames)
        return _SourcesResult(
            justfile_text=result.text,
            inventory_text=None,
            missing=result.missing,
            skipped_reason=result.skipped_reason,
        )

    if _AGGREGATE_SLUG not in justfile_text and _AGGREGATE_SLUG not in inventory_text:
        return _SourcesResult(
            justfile_text=justfile_text,
            inventory_text=inventory_text,
            missing=(),
            skipped_reason="no_aggregate",
        )

    justfile_text = rewrite_renamed_references(
        justfile_text=justfile_text, renames=renames, canonical_set=canonical_set
    )
    missing = tuple(
        slug for slug in canonical if slug not in inventory_slugs(inventory_text=inventory_text)
    )
    reconciled_inventory = reconcile_inventory_text(
        inventory_text=inventory_text, canonical_slugs=canonical
    )

    lines = justfile_text.splitlines(keepends=True)
    block = check_recipe_bounds(lines=lines)
    if block is not None:
        bounds = targets_array_bounds(lines=lines, check_header=block[0], recipe_end=block[1])
        if not isinstance(bounds, str):
            insert_missing_targets(
                lines=lines,
                canonical_set=canonical_set,
                missing=tuple(
                    slug
                    for slug in missing
                    if slug
                    not in {
                        token
                        for token in (
                            token_for(line=line) for line in lines[bounds[0] + 1 : bounds[1]]
                        )
                        if token is not None
                    }
                ),
                targets_start=bounds[0],
                targets_end=bounds[1],
            )
    reconstructed = "".join(lines)
    chunks = missing_recipe_chunks(justfile_text=reconstructed, missing=missing)
    return _SourcesResult(
        justfile_text=reconstructed + "".join(chunks),
        inventory_text=reconciled_inventory,
        missing=missing,
        skipped_reason=None,
    )


def reconcile_justfile_text(
    *,
    justfile_text: str,
    canonical_slugs: Sequence[str],
    renames: Sequence[tuple[str, str]] = (),
) -> str:
    """Reconcile `justfile_text` against `canonical_slugs`, returning the new text.

    Pure (no I/O). See `_reconcile` for the algorithm; this is the public
    text-in / text-out entry point the workflow step's `main()` and the test
    suite call. Returns the input unchanged when no reconcile applies. `renames`
    is the `canonical_checks.canonical_check_renames()` old->new map; defaults
    to empty so existing callers are unaffected.
    """
    return _reconcile(
        justfile_text=justfile_text, canonical_slugs=canonical_slugs, renames=renames
    ).text


def _emit_notice(*, message: str) -> None:
    """Write a GitHub Actions `::notice::` annotation to stdout."""
    _ = sys.stdout.write(f"::notice::{message}\n")


def _emit_warning(*, message: str) -> None:
    """Write a GitHub Actions `::warning::` annotation to stdout.

    A skip on a consumer that DOES carry the aggregate is the failure mode this
    module was blind to: it exited 0 with a `::notice::` nobody reads, and the
    consequence surfaced later as a red bump PR whose diagnosis named the
    symptom (`missing_canonical_slug`) rather than the cause. A warning makes
    the skip visible in the bump run itself.
    """
    _ = sys.stdout.write(f"::warning::{message}\n")


def _slugs_from_env() -> tuple[str, ...]:
    """Parse the `CANONICAL_JSON` env payload into a canonical-slug tuple.

    The payload is the `{"slugs": [...]}` JSON the workflow step captures from
    `python -m livespec_dev_tooling.canonical_checks --json`. A non-dict payload
    or a missing / non-list `slugs` field yields an empty tuple, and a non-`str`
    list element is dropped — mirroring the pre-extraction embedded step's
    defensive parse.
    """
    parsed = json.loads(os.environ["CANONICAL_JSON"])
    mapping = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None
    slug_field = mapping.get("slugs") if mapping is not None else None
    if not isinstance(slug_field, list):
        return ()
    return tuple(str(s) for s in cast("list[object]", slug_field) if isinstance(s, str))


def main() -> int:
    """IO entry point — reconcile the cwd justfile against `$CANONICAL_JSON` in place.

    Emits the same `::notice::` annotations the pre-extraction embedded step
    wrote: a per-skip-reason notice when the justfile is not reconcilable, a
    `reconciled ... for: <slugs>` notice when it rewrote the file, or a
    `canonical check wiring already current` notice when nothing changed.
    """
    justfile = Path.cwd() / _JUSTFILE_NAME
    if not justfile.is_file():
        _emit_notice(message="no justfile found; skipping canonical check wiring reconcile")
        return 0

    slugs = _slugs_from_env()
    justfile_text = justfile.read_text(encoding="utf-8")
    inventory = Path.cwd() / _INVENTORY_NAME
    inventory_text = inventory.read_text(encoding="utf-8") if inventory.is_file() else None
    result = reconcile_sources(
        justfile_text=justfile_text,
        inventory_text=inventory_text,
        canonical_slugs=slugs,
        renames=unsafe_perform_io(canonical_check_renames().unwrap()),
    )

    if result.skipped_reason is not None:
        _emit_notice(message=_SKIP_NOTICES[result.skipped_reason])
        if result.skipped_reason != "no_aggregate":
            _emit_warning(
                message=(
                    f"canonical check wiring NOT reconciled ({result.skipped_reason}); "
                    "this consumer carries check-aggregate-completeness and will fail it "
                    "until wired by hand"
                )
            )
        return 0

    changed = False
    if result.justfile_text != justfile_text:
        _ = justfile.write_text(result.justfile_text, encoding="utf-8")
        changed = True
    if result.inventory_text is not None and result.inventory_text != inventory_text:
        _ = inventory.write_text(result.inventory_text, encoding="utf-8")
        changed = True
    if changed:
        _emit_notice(message=f"reconciled canonical check wiring for: {', '.join(result.missing)}")
    else:
        _emit_notice(message="canonical check wiring already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
