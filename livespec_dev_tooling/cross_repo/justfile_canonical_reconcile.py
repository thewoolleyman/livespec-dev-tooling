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

- insert every canonical slug missing from the consumer's `check:` aggregate
  `targets=(...)` array (preserving canonical order and the array's existing
  indent); and
- append a zero-arg `check-<slug>:` recipe for each missing slug that has NO
  recipe header yet.

The extraction fixes ONE latent bug in the recipe-presence guard. The
pre-extraction guard recognized a canonical slug's recipe ONLY when it was
defined as the BARE header `check-<slug>:`. Both Driver repos
(`livespec-driver-claude`, `livespec-driver-codex`) hand-define
`check-red-green-replay` in PARAMETERIZED form — `check-red-green-replay *args:`
(the aggregate calls it with no args; the pre-commit hook passes a message
path). The bare-only guard missed that form, so it appended a SECOND
`check-red-green-replay:` recipe; `just` then refused to parse the redefinition
and every `just check-*` failed in the consumer's CI. `_recipe_header_present`
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
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling.canonical_checks import canonical_check_renames

__all__: list[str] = ["reconcile_justfile_text"]


_JUSTFILE_NAME = "justfile"
_AGGREGATE_SLUG = "check-aggregate-completeness"
_CHECK_PREFIX = "check-"
_DEFAULT_TARGET_INDENT = "        "
_RECIPE_MODULE_STEM = "uv run python -m livespec_dev_tooling.checks."

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


def _token_for(*, line: str) -> str | None:
    """Return the `check-<slug>` token a targets-array line names, else None.

    A blank line, a `#` comment line, or a non-`check-`-prefixed entry names no
    canonical target token. A trailing inline `# ...` comment is stripped.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    token = stripped.split("#", 1)[0].strip()
    return token if token.startswith(_CHECK_PREFIX) else None


def _recipe_header_present(*, justfile_text: str, slug: str) -> bool:
    r"""Return True when `justfile_text` already defines a `<slug>` recipe header.

    A just recipe header sits at column 0 (no leading whitespace): the recipe
    name, then optional parameters/dependencies, then `:`. The lookahead
    `(?=[ \t:])` requires the character immediately after the slug to be
    whitespace or the colon — never `-` — so a `<slug>` lookup does NOT match a
    longer `<slug>-<suffix>:` header (prefix-collision guard). This recognizes
    EVERY recipe-header form for the slug:

    - bare `check-foo:`
    - variadic `check-foo *args:`
    - named / defaulted params `check-foo msg_path:` / `check-foo a b:` /
      `check-foo p="x":`

    The pre-extraction guard matched only the bare `check-foo:` header, so it
    re-appended a duplicate recipe when a consumer hand-defined the check in a
    PARAMETERIZED form (both Driver repos define `check-red-green-replay *args:`
    that way) — the redefinition then broke the consumer's `just` parse.
    Matching any header form is the fix.
    """
    header = re.compile(rf"^{re.escape(slug)}(?=[ \t:])[^\n]*?:", re.MULTILINE)
    return header.search(justfile_text) is not None


def _bare_check_recipe_bounds(*, lines: list[str]) -> tuple[int, int] | None:
    """Return (check_header_index, recipe_end_index) for the bare `check:` recipe, or None.

    `recipe_end` is the index of the next column-0 recipe header after `check:`
    (or `len(lines)` when `check:` is the file's last recipe). None means the
    justfile carries no bare `check:` aggregate recipe.
    """
    check_header = next(
        (i for i, line in enumerate(lines) if line in ("check:\n", "check:")),
        None,
    )
    if check_header is None:
        return None
    recipe_end = len(lines)
    for i in range(check_header + 1, len(lines)):
        line = lines[i]
        if line and not line.startswith((" ", "\t")) and ":" in line:
            recipe_end = i
            break
    return check_header, recipe_end


def _targets_array_bounds(
    *, lines: list[str], check_header: int, recipe_end: int
) -> tuple[int, int] | str:
    """Return (targets_start, targets_end) or a skip-reason string.

    The `targets=(` opener and its `)` closer must both sit inside the `check:`
    recipe body (before `recipe_end`). A missing opener yields `no_targets_array`;
    a missing closer yields `unterminated_targets` — both keys into
    `_SKIP_NOTICES`.
    """
    targets_start = next(
        (i for i in range(check_header + 1, recipe_end) if lines[i].strip() == "targets=("),
        None,
    )
    if targets_start is None:
        return "no_targets_array"
    targets_end = next(
        (i for i in range(targets_start + 1, recipe_end) if lines[i].strip() == ")"),
        None,
    )
    if targets_end is None:
        return "unterminated_targets"
    return targets_start, targets_end


def _target_indent(*, lines: list[str], targets_start: int, targets_end: int) -> str:
    """Return the leading-whitespace indent of the first token line in the array.

    Falls back to the eight-space default when the array carries no token line
    (an empty array, or one holding only comments/blanks).
    """
    for line in lines[targets_start + 1 : targets_end]:
        if _token_for(line=line) is not None:
            return line[: len(line) - len(line.lstrip())]
    return _DEFAULT_TARGET_INDENT


def _insert_missing_targets(
    *,
    lines: list[str],
    canonical_set: set[str],
    missing: tuple[str, ...],
    targets_start: int,
    targets_end: int,
) -> None:
    """Insert each missing slug into the `targets=(...)` array in `lines`, in place.

    Each slug lands before the first EXISTING canonical token that sorts after
    it (keeping the canonical block alphabetically ordered), or after the last
    canonical token when it sorts last, or at the array head when the array
    holds no canonical token. Non-canonical (consumer-local) tokens are not
    used as sort anchors, matching the pre-extraction behavior.
    """
    indent = _target_indent(lines=lines, targets_start=targets_start, targets_end=targets_end)
    end = targets_end
    for slug in missing:
        insert_at: int | None = None
        last_canonical: int | None = None
        for i in range(targets_start + 1, end):
            token = _token_for(line=lines[i])
            if token in canonical_set:
                last_canonical = i
                if token > slug:
                    insert_at = i
                    break
        if insert_at is None:
            insert_at = targets_start + 1 if last_canonical is None else last_canonical + 1
        lines.insert(insert_at, f"{indent}{slug}\n")
        end += 1


def _missing_recipe_chunks(*, justfile_text: str, missing: tuple[str, ...]) -> list[str]:
    """Return a zero-arg `check-<slug>:` recipe chunk for each missing slug lacking a recipe.

    A slug whose recipe header is already defined in ANY form (bare, variadic,
    or named-param — see `_recipe_header_present`) gets NO chunk, so a
    parameterized hand-defined recipe is never duplicated.
    """
    chunks: list[str] = []
    for slug in missing:
        if _recipe_header_present(justfile_text=justfile_text, slug=slug):
            continue
        module = slug.removeprefix(_CHECK_PREFIX).replace("-", "_")
        chunks.append(f"\n{slug}:\n    {_RECIPE_MODULE_STEM}{module}\n")
    return chunks


def _rewrite_renamed_references(
    *, justfile_text: str, renames: Sequence[tuple[str, str]], canonical_set: set[str]
) -> str:
    """Rewrite a wired OLD canonical slug (and its auto-generated recipe) to its NEW name.

    A canonical check rename (`canonical_checks.canonical_check_renames()`)
    drops the OLD slug from the canonical set with no trace of the rename — the
    canonical set is a filesystem walk, so a renamed `checks/<old>.py` module
    simply stops existing under that name. A consumer whose justfile still
    wires the OLD slug is left stranded: its bump PR's CI runs `just
    check-<old-slug>`, which imports a module that no longer exists
    (`ModuleNotFoundError`, livespec-dev-tooling-3gy1).

    For every rename whose `new` side is canonical, rewrites the OLD slug's
    wired target-array token to the NEW slug, then rewrites its
    auto-generated bare `check-<old>:` recipe to the NEW slug/module — ONLY
    when that recipe is in EXACTLY the auto-generated bare shape this module
    itself would append. A hand-authored or parameterized old recipe is left
    alone: this module never overwrites content it did not itself generate.
    A rename whose old slug is not actually wired is a no-op (`re.subn`
    reports zero replacements and the recipe rewrite is skipped).
    """
    text = justfile_text
    for old, new in renames:
        if new not in canonical_set:
            continue
        text, replaced = re.subn(
            rf"^([ \t]*){re.escape(old)}([ \t]*)$",
            rf"\g<1>{new}\g<2>",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if not replaced:
            continue
        old_module = old.removeprefix(_CHECK_PREFIX).replace("-", "_")
        new_module = new.removeprefix(_CHECK_PREFIX).replace("-", "_")
        old_recipe = f"{old}:\n    {_RECIPE_MODULE_STEM}{old_module}\n"
        if old_recipe in text:
            text = text.replace(old_recipe, f"{new}:\n    {_RECIPE_MODULE_STEM}{new_module}\n", 1)
    return text


def _reconcile(
    *,
    justfile_text: str,
    canonical_slugs: Sequence[str],
    renames: Sequence[tuple[str, str]] = (),
) -> _ReconcileResult:
    """Pure core — reconcile the consumer justfile text against the canonical slug set.

    First rewrites any wired slug the `renames` map strands (see
    `_rewrite_renamed_references`), then inserts every canonical slug missing
    from the `check:` aggregate's `targets=(...)` array, then appends a
    zero-arg `check-<slug>:` recipe for each missing slug that has NO recipe
    header in any form. Returns the input unchanged with a `skipped_reason`
    when the justfile does not carry the reconcilable shape.
    """
    canonical = tuple(canonical_slugs)
    canonical_set = set(canonical)
    if _AGGREGATE_SLUG not in justfile_text:
        return _ReconcileResult(text=justfile_text, missing=(), skipped_reason="no_aggregate")

    justfile_text = _rewrite_renamed_references(
        justfile_text=justfile_text, renames=renames, canonical_set=canonical_set
    )

    lines = justfile_text.splitlines(keepends=True)
    block = _bare_check_recipe_bounds(lines=lines)
    if block is None:
        return _ReconcileResult(text=justfile_text, missing=(), skipped_reason="no_check_header")
    check_header, recipe_end = block

    bounds = _targets_array_bounds(lines=lines, check_header=check_header, recipe_end=recipe_end)
    if isinstance(bounds, str):
        return _ReconcileResult(text=justfile_text, missing=(), skipped_reason=bounds)
    targets_start, targets_end = bounds

    wired = {
        token
        for token in (_token_for(line=line) for line in lines[targets_start + 1 : targets_end])
        if token is not None
    }
    missing = tuple(slug for slug in canonical if slug not in wired)

    _insert_missing_targets(
        lines=lines,
        canonical_set=canonical_set,
        missing=missing,
        targets_start=targets_start,
        targets_end=targets_end,
    )
    reconstructed = "".join(lines)
    chunks = _missing_recipe_chunks(justfile_text=reconstructed, missing=missing)
    return _ReconcileResult(
        text=reconstructed + "".join(chunks),
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
    result = _reconcile(
        justfile_text=justfile_text, canonical_slugs=slugs, renames=canonical_check_renames()
    )

    if result.skipped_reason is not None:
        _emit_notice(message=_SKIP_NOTICES[result.skipped_reason])
        return 0

    if result.text != justfile_text:
        _ = justfile.write_text(result.text, encoding="utf-8")
        _emit_notice(message=f"reconciled canonical check wiring for: {', '.join(result.missing)}")
    else:
        _emit_notice(message="canonical check wiring already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
