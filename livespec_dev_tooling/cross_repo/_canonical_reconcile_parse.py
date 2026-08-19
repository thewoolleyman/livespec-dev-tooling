"""_canonical_reconcile_parse — pure text transforms for justfile_canonical_reconcile.

Private sibling of `justfile_canonical_reconcile.py`, following the same pure/IO
plus LLOC-reduction split as `_ci_matrix_parse` / `ci_matrix_completeness` and
`_self_hosted_routing_parse` / `self_hosted_routing`: every function here is PURE
(no I/O, no logging, no environment) and the parent owns the file reads, writes,
and GitHub Actions annotations.

The module is private-NAMED but its functions are public-NAMED, the convention
its two siblings already use: the parent imports them by public name rather than
reaching into another module's underscore-prefixed surface.

Three of these transforms exist because the parent was blind to consumers whose
canonical-slug inventory is NOT the justfile's `targets=(...)` array.
`aggregate_completeness` reads a committed `check-targets.txt` FIRST and parses
the array only in its absence, so `inventory_slugs`,
`insert_missing_inventory_slugs`, and `reconcile_inventory_text` reconcile the
source the gate is actually gated on. Ordering is load-bearing in both the array
and the file: the gate fails an out-of-canonical-order inventory as well as an
incomplete one.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

__all__: list[str] = [
    "check_recipe_bounds",
    "insert_missing_inventory_slugs",
    "insert_missing_targets",
    "inventory_slugs",
    "missing_recipe_chunks",
    "recipe_header_present",
    "reconcile_inventory_text",
    "rewrite_renamed_references",
    "target_indent",
    "targets_array_bounds",
    "token_for",
]

_CHECK_PREFIX = "check-"
_DEFAULT_TARGET_INDENT = "        "
_RECIPE_MODULE_STEM = "uv run python -m livespec_dev_tooling.checks."
# The aggregate recipe header, bare (`check:`) or PARAMETERIZED
# (`check *skip_targets:`). Matching only the bare form is what made the parent
# skip `livespec-runtime` -- the same narrow-match bug it already records fixing
# for RECIPE headers, left unfixed for the AGGREGATE header.
_CHECK_HEADER_RE = re.compile(r"^check(?:\s+[^:\n]*)?:\s*$")


def token_for(*, line: str) -> str | None:
    """Return the `check-<slug>` token a targets-array line names, else None.

    A blank line, a `#` comment line, or a non-`check-`-prefixed entry names no
    canonical target token. A trailing inline `# ...` comment is stripped.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    token = stripped.split("#", 1)[0].strip()
    return token if token.startswith(_CHECK_PREFIX) else None


def recipe_header_present(*, justfile_text: str, slug: str) -> bool:
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


def rewrite_renamed_references(
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


def check_recipe_bounds(*, lines: list[str]) -> tuple[int, int] | None:
    """Return (check_header_index, recipe_end_index) for the `check` recipe, or None.

    Accepts the bare header (`check:`) AND a parameterized one
    (`check *skip_targets:`), because a consumer is free to declare arguments on
    its aggregate and `just` calls it with none. Matching only the bare form
    made this module report `no_check_header` and silently skip such a
    consumer, which then failed `check-aggregate-completeness` on the very bump
    that was supposed to wire it.

    `recipe_end` is the index of the next column-0 recipe header after the
    aggregate (or `len(lines)` when it is the file's last recipe). None means
    the justfile carries no `check` aggregate recipe at all.
    """
    check_header = next(
        (i for i, line in enumerate(lines) if _CHECK_HEADER_RE.match(line.rstrip("\n"))),
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


def targets_array_bounds(
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


def target_indent(*, lines: list[str], targets_start: int, targets_end: int) -> str:
    """Return the leading-whitespace indent of the first token line in the array.

    Falls back to the eight-space default when the array carries no token line
    (an empty array, or one holding only comments/blanks).
    """
    for line in lines[targets_start + 1 : targets_end]:
        if token_for(line=line) is not None:
            return line[: len(line) - len(line.lstrip())]
    return _DEFAULT_TARGET_INDENT


def insert_missing_targets(
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
    indent = target_indent(lines=lines, targets_start=targets_start, targets_end=targets_end)
    end = targets_end
    for slug in missing:
        insert_at: int | None = None
        last_canonical: int | None = None
        for i in range(targets_start + 1, end):
            token = token_for(line=lines[i])
            if token in canonical_set:
                last_canonical = i
                if token > slug:
                    insert_at = i
                    break
        if insert_at is None:
            insert_at = targets_start + 1 if last_canonical is None else last_canonical + 1
        lines.insert(insert_at, f"{indent}{slug}\n")
        end += 1


def missing_recipe_chunks(*, justfile_text: str, missing: tuple[str, ...]) -> list[str]:
    """Return a zero-arg `check-<slug>:` recipe chunk for each missing slug lacking a recipe.

    A slug whose recipe header is already defined in ANY form (bare, variadic,
    or named-param — see `recipe_header_present`) gets NO chunk, so a
    parameterized hand-defined recipe is never duplicated.
    """
    chunks: list[str] = []
    for slug in missing:
        if recipe_header_present(justfile_text=justfile_text, slug=slug):
            continue
        module = slug.removeprefix(_CHECK_PREFIX).replace("-", "_")
        chunks.append(f"\n{slug}:\n    {_RECIPE_MODULE_STEM}{module}\n")
    return chunks


def inventory_slugs(*, inventory_text: str) -> set[str]:
    """Return the `check-` slugs an inventory file declares, comments stripped."""
    return {
        token
        for token in (token_for(line=line) for line in inventory_text.splitlines())
        if token is not None
    }


def insert_missing_inventory_slugs(
    *, lines: list[str], canonical_set: set[str], missing: tuple[str, ...]
) -> None:
    """Insert each missing slug into inventory `lines`, in place, in canonical order.

    Mirrors `insert_missing_targets`: a slug lands before the first EXISTING
    canonical slug that sorts after it, after the last canonical slug when it
    sorts last, or at end-of-file when the inventory declares none. Ordering is
    load-bearing rather than cosmetic -- `aggregate_completeness` fails an
    out-of-canonical-order inventory as well as an incomplete one.
    """
    for slug in missing:
        insert_at: int | None = None
        last_canonical: int | None = None
        for i, line in enumerate(lines):
            token = token_for(line=line)
            if token in canonical_set:
                last_canonical = i
                if token > slug:
                    insert_at = i
                    break
        if insert_at is None:
            insert_at = len(lines) if last_canonical is None else last_canonical + 1
        lines.insert(insert_at, f"{slug}\n")


def reconcile_inventory_text(*, inventory_text: str, canonical_slugs: Sequence[str]) -> str:
    """Reconcile a `check-targets.txt` inventory against `canonical_slugs`.

    Pure (no I/O). Returns the input unchanged when every canonical slug is
    already declared.
    """
    canonical = tuple(canonical_slugs)
    canonical_set = set(canonical)
    declared = inventory_slugs(inventory_text=inventory_text)
    missing = tuple(slug for slug in canonical if slug not in declared)
    if not missing:
        return inventory_text
    lines = inventory_text.splitlines(keepends=True)
    insert_missing_inventory_slugs(lines=lines, canonical_set=canonical_set, missing=missing)
    return "".join(lines)
