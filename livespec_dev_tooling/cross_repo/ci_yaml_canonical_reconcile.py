"""ci_yaml_canonical_reconcile — reconcile a consumer ci.yml's canonical check matrix.

The ci.yml sibling of `justfile_canonical_reconcile`, dispatched from the
`bump-pin-rewrite` composite Action's "Reconcile canonical CI matrix wiring"
step. Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", when a bumped livespec-dev-tooling release adds a new module under
`livespec_dev_tooling/checks/`, the live canonical-check slug set grows and the
consumer's `justfile` `check:` aggregate adopts it (the justfile reconcile, run
one step earlier). `check-ci-matrix-completeness` then asserts the canonical
slugs CI RUNS are a SUPERSET of the canonical slugs that aggregate WIRES — so a
bump that reconciled the justfile ALONE left CI's hand-maintained
`strategy.matrix.target` list short the new entry, and the bump PR was red by
construction on a check whose diagnosis was correct. This module closes that
half of the reconcile: it inserts each newly-adopted canonical slug, in
alphabetical position, into the consumer's `.github/workflows/ci.yml` matrix
target list that ALREADY carries `check-aggregate-completeness`.

Correct-by-construction with the gate it feeds: the slug arithmetic mirrors
`ci_matrix_completeness._evaluate` and SHARES that check's `_ci_matrix_parse`
parsers, so what this module writes and what the check demands cannot drift. A
slug is REQUIRED when the justfile aggregate wires it AND it is canonical AND it
is not a WORLD GATE (`canonical_checks.world_gate_check_slugs` —
`check-master-ci-green` / `check-branch-protection-alignment`, which verify the
WORLD the change lands on, enforce at pre-push under an admin-scoped token, and
are deliberately excluded from the CI-mirror requirement). A required slug is
already COVERED when any job runs it — via that job's own `matrix.target` list
OR via a `just check-<slug>` run line (the shape of a dedicated full-history
`check-red-green-replay` job), so a slug covered outside the anchor matrix is
never duplicated into it.

Version-skew discipline (the defect that deadlocked the fan-out): the CANONICAL
set is a FILESYSTEM WALK of whatever `livespec_dev_tooling.checks` is running,
so resolving it from a checkout at a different version than the consumer's pin
injects slugs the consumer's own gate does not recognize. It is therefore
supplied as DATA, via `$CANONICAL_JSON`, captured by the composite Action from
the CONSUMER's own environment. The WORLD-GATE set is different in kind: a
curated, hand-maintained static registry (not filesystem-derived), unchanged
since it landed — so it is read from this module's own `canonical_checks`
import and then intersected with the consumer's canonical set, which cannot name
a check the consumer does not carry.

Failure discipline: when a consumer has canonical slugs to adopt but carries NO
matrix target list to adopt them into, this module emits a GitHub Actions
`::error::` naming the exact YAML lines to add and exits NON-ZERO — failing the
bump job rather than opening a PR that is knowably red by construction.

Output discipline mirrors the sibling `justfile_canonical_reconcile`: the pure
`reconcile_ci_yaml_text` / `_reconcile` core does no I/O, and `main()` owns the
file read/write plus the GitHub Actions annotations on stdout (declared in
`pyproject.toml` `supervisor_entry_files`, the surface `no_write_direct`
exempts).
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

from returns.result import Failure  # noqa: E402  — vendor-path-aware.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling import canonical_checks  # noqa: E402
from livespec_dev_tooling.checks._check_aggregate_failures import (  # noqa: E402
    TargetsArrayUnterminated,
)
from livespec_dev_tooling.checks._ci_matrix_parse import (  # noqa: E402
    extract_check_recipe_body,
    extract_targets_array_tokens,
    parse_ci_jobs,
)
from livespec_dev_tooling.cross_repo._ci_yaml_reconcile_parse import (  # noqa: E402
    AGGREGATE_SLUG,
    batch_anchor,
    batch_insert_index,
    batch_line_for,
    insert_index,
    matrix_anchor,
    rewrite_renamed_bullets,
)

__all__: list[str] = ["reconcile_ci_yaml_text"]


_JUSTFILE_NAME = "justfile"
# The consumer's committed slug inventory. `ci_matrix_completeness` resolves
# THIS FIRST and parses the justfile array only in its absence, so a reconciler
# that reads the array alone disagrees with its own gate on every consumer that
# carries the file.
_INVENTORY_NAME = "check-targets.txt"
_CHECK_PREFIX = "check-"
_CI_YML_PATH = Path(".github") / "workflows" / "ci.yml"
_CI_GREEN_JOB = "ci-green"

# `strategy.matrix.target:` anchors. The bullet regex mirrors
# `_ci_matrix_parse._MATRIX_TARGET_LINE` so this module recognizes exactly the
# entries the gate counts, and captures the bullet's own indent so an inserted
# entry lands at the list's existing depth.

# Skip-reason → GitHub Actions `::notice::` message. Each names a consumer shape
# for which `check-ci-matrix-completeness` emits a PRECONDITION finding rather
# than a missing-slug finding, so no slug exists that this module could
# correctly add.
_SKIP_NOTICES: dict[str, str] = {
    "no_aggregate": (
        "consumer does not carry check-aggregate-completeness; "
        "skipping canonical CI matrix reconcile"
    ),
    "no_check_recipe": (
        "justfile has no bare check: recipe; skipping canonical CI matrix reconcile"
    ),
    "no_targets_array": (
        "check: recipe has no targets=(...) array; skipping canonical CI matrix reconcile"
    ),
    # Reachable only since the railway conversion. This condition used to
    # arrive as `no_targets_array` and told the operator to add an array that
    # is already there.
    "unterminated_targets_array": (
        "check: recipe opens a targets=(...) array and never closes it; "
        "skipping canonical CI matrix reconcile"
    ),
}

_ERROR_NO_ANCHOR = (
    ".github/workflows/ci.yml carries no `strategy.matrix.target:` list containing "
    "`{aggregate}`, so the canonical check slug(s) this bump adopts into the `just check` "
    "aggregate cannot be mirrored into CI. `check-ci-matrix-completeness` will fail this "
    "consumer until CI runs them. Add these entries to the matrix that mirrors the "
    "aggregate:{lines}"
)


@dataclass(frozen=True, kw_only=True)
class _ReconcileResult:
    """Outcome of one reconcile pass: reconciled text plus diagnostics.

    `text` is the reconciled ci.yml text (identical to the input when no change
    applies). `missing` lists the canonical slugs CI must adopt (empty when
    none). `skipped_reason` names the early-exit branch when the consumer does
    not carry the reconcilable shape. `unreconcilable` is True when slugs must be
    adopted but no anchor matrix exists to adopt them into — the state `main()`
    turns into an `::error::` and a non-zero exit.
    """

    text: str
    missing: tuple[str, ...]
    skipped_reason: str | None
    unreconcilable: bool


def _wired_targets(*, justfile_text: str, inventory_text: str | None) -> list[str] | str:
    """Return the aggregate's wired slugs, or a `_SKIP_NOTICES` key.

    Resolution mirrors `ci_matrix_completeness` EXACTLY, which is what keeps the
    wired set this module reconciles against byte-for-byte identical to the set
    the gate compares CI to: a committed `check-targets.txt` is PRIMARY, and the
    justfile's `targets=(...)` array is parsed only in its absence.

    Reading the array alone — as this did — made the writer disagree with its own
    gate on every consumer carrying the inventory file: the gate demanded slugs
    from the file while the reconciler reported `no_targets_array` and skipped
    with a notice. Three fleet consumers are in that shape.
    """
    if inventory_text is not None:
        slugs = [
            token
            for token in (line.split("#", 1)[0].strip() for line in inventory_text.splitlines())
            if token.startswith(_CHECK_PREFIX)
        ]
        return slugs if AGGREGATE_SLUG in slugs else "no_aggregate"
    if AGGREGATE_SLUG not in justfile_text:
        return "no_aggregate"
    recipe_body = extract_check_recipe_body(justfile_text=justfile_text)
    if isinstance(recipe_body, Failure):
        return "no_check_recipe"
    targets = extract_targets_array_tokens(recipe_body=recipe_body.unwrap())
    if isinstance(targets, Failure):
        if isinstance(targets.failure(), TargetsArrayUnterminated):
            return "unterminated_targets_array"
        return "no_targets_array"
    return targets.unwrap()


def _ci_covered_slugs(*, ci_yaml_text: str, canonical_set: set[str]) -> set[str]:
    """Return the canonical slugs CI already runs, across every job but `ci-green`.

    Mirrors `ci_matrix_completeness._evaluate`'s coverage union: a job contributes
    the canonical slugs of its `strategy.matrix.target` list AND of its
    `just check-<slug>` run lines.
    """
    covered: set[str] = set()
    for job in parse_ci_jobs(source=ci_yaml_text):
        if job.name == _CI_GREEN_JOB:
            continue
        covered |= job.contributed_check_slugs & canonical_set
    return covered


def _reconcile_batched(
    *,
    ci_yaml_text: str,
    lines: list[str],
    canonical_set: set[str],
    missing: tuple[str, ...],
) -> _ReconcileResult:
    """Mirror `missing` into the consumer's BATCHED aggregate section.

    Reached when the consumer runs the aggregate from `run:` lines rather than a
    `matrix.target:` list. The gate has always counted that shape as coverage;
    only the writer was blind to it, which aborted the bump job outright and
    left the consumer's pin frozen. A consumer carrying neither shape is
    genuinely unreconcilable and still escalates.
    """
    anchor = batch_anchor(lines=lines)
    if anchor is None:
        return _ReconcileResult(
            text=ci_yaml_text, missing=missing, skipped_reason=None, unreconcilable=True
        )
    plan = [
        (batch_insert_index(anchor=anchor, canonical_set=canonical_set, slug=slug), slug)
        for slug in missing
    ]
    for index, slug in sorted(plan, reverse=True):
        lines.insert(index, batch_line_for(anchor=anchor, slug=slug))
    return _ReconcileResult(
        text="".join(lines), missing=missing, skipped_reason=None, unreconcilable=False
    )


def _reconcile(
    *,
    ci_yaml_text: str,
    justfile_text: str,
    inventory_text: str | None = None,
    canonical_slugs: Sequence[str],
    world_gates: Sequence[str],
    renames: Sequence[tuple[str, str]] = (),
) -> _ReconcileResult:
    """Pure core — reconcile the consumer ci.yml against the canonical slug set."""
    canonical_set = set(canonical_slugs)
    ci_yaml_text = rewrite_renamed_bullets(
        ci_yaml_text=ci_yaml_text, renames=renames, canonical_set=canonical_set
    )
    targets = _wired_targets(justfile_text=justfile_text, inventory_text=inventory_text)
    if isinstance(targets, str):
        return _ReconcileResult(
            text=ci_yaml_text, missing=(), skipped_reason=targets, unreconcilable=False
        )

    gates = set(world_gates)
    required = {slug for slug in targets if slug in canonical_set and slug not in gates}
    covered = _ci_covered_slugs(ci_yaml_text=ci_yaml_text, canonical_set=canonical_set)
    missing = tuple(sorted(required - covered))
    if not missing:
        return _ReconcileResult(
            text=ci_yaml_text, missing=(), skipped_reason=None, unreconcilable=False
        )

    lines = ci_yaml_text.splitlines(keepends=True)
    anchor = matrix_anchor(lines=lines)
    if anchor is None:
        return _reconcile_batched(
            ci_yaml_text=ci_yaml_text, lines=lines, canonical_set=canonical_set, missing=missing
        )

    plan = [
        (insert_index(lines=lines, anchor=anchor, canonical_set=canonical_set, slug=slug), slug)
        for slug in missing
    ]
    # Applying the inserts in DESCENDING (index, slug) order keeps every planned
    # index valid against the growing list, and leaves two slugs planned at the
    # same index in ascending order in the result.
    for index, slug in sorted(plan, reverse=True):
        lines.insert(index, f"{anchor.indent}- {slug}\n")
    return _ReconcileResult(
        text="".join(lines), missing=missing, skipped_reason=None, unreconcilable=False
    )


def reconcile_ci_yaml_text(
    *,
    ci_yaml_text: str,
    justfile_text: str,
    inventory_text: str | None = None,
    canonical_slugs: Sequence[str],
    world_gates: Sequence[str],
    renames: Sequence[tuple[str, str]] = (),
) -> str:
    """Reconcile `ci_yaml_text` against `canonical_slugs`, returning the new text.

    Pure (no I/O). See `_reconcile` for the algorithm; this is the public
    text-in / text-out entry point the test suite calls. Returns the input
    unchanged when no reconcile applies — including when slugs must be adopted
    but no anchor matrix exists, which `main()` alone escalates to an `::error::`
    rather than guessing where the entries belong. `renames` is the
    `canonical_checks.canonical_check_renames()` old->new map; defaults to
    empty so existing callers are unaffected.
    """
    return _reconcile(
        ci_yaml_text=ci_yaml_text,
        justfile_text=justfile_text,
        inventory_text=inventory_text,
        canonical_slugs=canonical_slugs,
        world_gates=world_gates,
        renames=renames,
    ).text


def _emit(*, annotation: str, message: str) -> None:
    """Write a GitHub Actions annotation (`notice` / `error`) to stdout."""
    _ = sys.stdout.write(f"::{annotation}::{message}\n")


def _slugs_from_env() -> tuple[str, ...]:
    """Parse the `CANONICAL_JSON` env payload into a canonical-slug tuple.

    The payload is the `{"slugs": [...]}` JSON the composite Action captures from
    `python -m livespec_dev_tooling.canonical_checks --json` run in the CONSUMER's
    environment — the pinned version whose gate this reconcile must satisfy. A
    non-dict payload or a missing / non-list `slugs` field yields an empty tuple,
    and a non-`str` list element is dropped, mirroring the sibling justfile
    reconcile's defensive parse.
    """
    parsed = json.loads(os.environ["CANONICAL_JSON"])
    mapping = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None
    slug_field = mapping.get("slugs") if mapping is not None else None
    if not isinstance(slug_field, list):
        return ()
    return tuple(str(s) for s in cast("list[object]", slug_field) if isinstance(s, str))


def main() -> int:
    """IO entry point — reconcile the cwd ci.yml against `$CANONICAL_JSON` in place.

    Exits 0 having rewritten the ci.yml (or having emitted a skip / already-current
    notice), or 1 with an `::error::` naming the exact YAML lines to add when the
    consumer has canonical slugs to adopt but no matrix to adopt them into.
    """
    justfile = Path.cwd() / _JUSTFILE_NAME
    if not justfile.is_file():
        _emit(
            annotation="notice", message="no justfile found; skipping canonical CI matrix reconcile"
        )
        return 0
    ci_yaml = Path.cwd() / _CI_YML_PATH
    if not ci_yaml.is_file():
        _emit(
            annotation="notice",
            message=(
                "no .github/workflows/ci.yml found; the consumer runs no CI to mirror the "
                "aggregate into"
            ),
        )
        return 0

    ci_yaml_text = ci_yaml.read_text(encoding="utf-8")
    result = _reconcile(
        ci_yaml_text=ci_yaml_text,
        justfile_text=justfile.read_text(encoding="utf-8"),
        inventory_text=(
            inventory.read_text(encoding="utf-8")
            if (inventory := Path.cwd() / _INVENTORY_NAME).is_file()
            else None
        ),
        canonical_slugs=_slugs_from_env(),
        world_gates=unsafe_perform_io(canonical_checks.world_gate_check_slugs().unwrap()),
        renames=unsafe_perform_io(canonical_checks.canonical_check_renames().unwrap()),
    )

    if result.skipped_reason is not None:
        _emit(annotation="notice", message=_SKIP_NOTICES[result.skipped_reason])
        return 0
    if result.unreconcilable:
        lines = "".join(f"%0A{' ' * 10}- {slug}" for slug in result.missing)
        _emit(
            annotation="error",
            message=_ERROR_NO_ANCHOR.format(aggregate=AGGREGATE_SLUG, lines=lines),
        )
        return 1
    if not result.missing:
        _emit(annotation="notice", message="canonical CI matrix wiring already current")
        return 0

    _ = ci_yaml.write_text(result.text, encoding="utf-8")
    _emit(
        annotation="notice",
        message=f"reconciled canonical CI matrix wiring for: {', '.join(result.missing)}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
