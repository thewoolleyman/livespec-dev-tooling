"""aggregate_completeness — every consumer's `just check` wires the full canonical-check set.

Per epic `li-univck` Phase 1.3 (work-item `li-aggchk`), this check
is the in-repo gate of the three-layer forever-forward enforcement
of universal check propagation. It parses the consumer's `justfile`
`check:` recipe, extracts the `targets=(...)` array, filters to
`check-*`-prefixed slugs, and compares against the canonical-check
slug tuple emitted by `livespec_dev_tooling.canonical_checks`.

Rules:

1. Every canonical slug MUST appear in the wired targets (missing
   slugs fail).
2. The canonical subset MUST appear in alphabetical order (the
   relative ordering of canonical slugs in the wired targets must
   match the canonical-set ordering).
3. Extras (repo-private slugs not in the canonical set) are allowed
   ONLY AFTER the canonical block — placing them before or
   interleaved with the canonical slugs breaks the canonical-subset
   ordering and fails.

Algorithm:

1. Resolve the canonical-slug tuple. Default: live discovery via
   `canonical_check_slugs()`. Override via `--canonical-from <path>`
   pointing to a JSON file with shape `{"slugs": [...]}` — used by
   tests to inject hermetic synthetic sets.
2. Resolve `justfile` location (cwd-relative). Failure → exit 4 with
   `justfile_not_found` finding.
3. Locate the `check:` recipe. Failure → exit 4 with
   `check_recipe_not_found` finding.
4. Locate the `targets=(...)` array within the recipe. Failure →
   exit 4 with `targets_array_not_found` finding.
5. Filter array contents to `check-*`-prefixed slugs (strips blanks,
   comments, non-canonical-prefix targets like `bootstrap`, `fmt`).
6. Walk the canonical tuple and the wired-targets list in parallel.
   - Missing slugs → `missing_canonical_slug` findings.
   - Wrong-order slugs (set match but ordering differs) →
     single `out_of_order_canonical_slugs` finding with both
     orderings.

Exit codes:

- `0` — canonical subset is fully present and in canonical order.
- `2` — usage error (bad CLI invocation).
- `4` — one or more rule violations; structured findings on stderr.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path`
at module import time so the check works equally well via
`python -m` and via direct script invocation.

Self-bootstrapping property: because this module lives under
`livespec_dev_tooling/checks/`, its own slug
(`check-aggregate-completeness`) is included in the canonical set
discovered by `canonical_check_slugs`. Once consumers wire this
slug into their `just check` aggregate (Phase 1.4+), running it
forces them to also wire every other canonical slug. The gate is
self-bootstrapping.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware.

from livespec_dev_tooling.canonical_checks import (  # noqa: E402
    canonical_check_slugs,
)

__all__: list[str] = []


_JUSTFILE_NAME = "justfile"
_CHECK_PREFIX = "check-"
_EXIT_VIOLATIONS = 4

# Matches a `check:` recipe header at column 0. Just recipes are
# defined as `<name>:` (optionally with arguments) at the start of
# a line; we match the literal `check:` (no recipe args) since the
# canonical aggregate name is `check`.
_CHECK_RECIPE_HEADER = re.compile(r"^check:\s*$", re.MULTILINE)
_TARGETS_ARRAY_START = re.compile(r"^\s*targets=\(\s*$", re.MULTILINE)
_TARGETS_ARRAY_END = re.compile(r"^\s*\)\s*$")


class _CanonicalOverride(TypedDict, total=False):
    """Shape of the `--canonical-from` JSON override file: `{"slugs": [...]}`.

    `total=False` mirrors the defensive `.get("slugs")` access — the key is
    optional, so the typed boundary matches runtime semantics exactly (no
    behavior change vs. the prior `Any` annotation). `slugs` is typed as a
    list of `object` (not `str`) so the per-element `isinstance(s, str)`
    filter in `_load_canonical` stays a load-bearing runtime guard against a
    malformed override file rather than a statically-redundant check.
    """

    slugs: list[object]


@dataclass(frozen=True, kw_only=True)
class _LoadedCanonical:
    """Canonical-slug tuple plus the source label used in diagnostics."""

    slugs: tuple[str, ...]
    source: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aggregate-completeness",
        description=(
            "Enforce that the consumer's `just check` aggregate wires the full "
            "canonical-check slug set in alphabetical order. Extras allowed "
            "only AFTER the canonical block. In-repo gate of epic li-univck "
            "Phase 1.3."
        ),
    )
    _ = parser.add_argument(
        "--canonical-from",
        type=str,
        default=None,
        help=(
            'Path to a JSON file with shape `{"slugs": [...]}` overriding '
            "the live canonical-set discovery. Reserved for hermetic test "
            "fixtures; production callers omit this flag."
        ),
    )
    return parser


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("aggregate_completeness")


def _load_canonical(*, canonical_from: str | None, cwd: Path) -> _LoadedCanonical:
    """Resolve the canonical-slug tuple from either an override file or live discovery."""
    # `unsafe_perform_io(...unwrap())` is FAIL-CLOSED and deliberate.
    # `canonical_check_slugs` is `IOResult` since `livespec-dev-tooling-vzwa`,
    # and its failure means the installed `checks/` package is unreadable — a
    # broken install, not a reachable state for a check running out of that same
    # package. A `match` arm here could never be covered under this repo's
    # 100%-per-file gate, so raising beats a dead branch (`#846`'s precedent).
    # ⛔ NOT `value_or(())`: an empty slug set is read as 'no canonical checks'
    # and PASSES — the exact fail-open vzwa removed.
    if canonical_from is None:
        return _LoadedCanonical(
            slugs=unsafe_perform_io(canonical_check_slugs().unwrap()), source="live"
        )
    path = (cwd / canonical_from).resolve()
    text = path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    # The `cast` is the single typed parse boundary: `json.loads` yields
    # `Any`, the `isinstance` guard narrows to `dict`, and the cast then
    # asserts the validated shape so `.get("slugs")` and the comprehension
    # over its elements are typed.
    override = cast("_CanonicalOverride", parsed) if isinstance(parsed, dict) else None
    slug_field: list[object] | None = override.get("slugs") if override is not None else None
    if not isinstance(slug_field, list):
        return _LoadedCanonical(slugs=(), source=str(path))
    slugs: list[str] = [s for s in slug_field if isinstance(s, str)]
    return _LoadedCanonical(slugs=tuple(slugs), source=str(path))


def _extract_check_recipe_body(*, justfile_text: str) -> str | None:
    """Return the text body of the `check:` recipe, or None when absent.

    A just recipe body extends from the recipe header to the next
    recipe header (a non-indented line ending in `:`) or to EOF. We
    scan line-by-line after the matched header.
    """
    header_match = _CHECK_RECIPE_HEADER.search(justfile_text)
    if header_match is None:
        return None
    body_start = header_match.end()
    lines = justfile_text[body_start:].splitlines()
    body_lines: list[str] = []
    for raw in lines:
        # A new recipe header is a non-indented line that ends with
        # `:` (possibly followed by args). We stop the body at that
        # line, NOT including it.
        if raw and not raw.startswith((" ", "\t")) and ":" in raw:
            break
        body_lines.append(raw)
    return "\n".join(body_lines)


def _extract_targets_array_lines(*, recipe_body: str) -> list[str] | None:
    """Return the raw lines inside `targets=(...)`, or None when absent.

    Lines are returned WITH leading/trailing whitespace stripped but
    BEFORE comment / blank filtering — slug filtering happens in the
    caller so this helper stays single-purpose.
    """
    start_match = _TARGETS_ARRAY_START.search(recipe_body)
    if start_match is None:
        return None
    after_start = recipe_body[start_match.end() :]
    lines = after_start.splitlines()
    collected: list[str] = []
    closed = False
    for raw in lines:
        if _TARGETS_ARRAY_END.match(raw):
            closed = True
            break
        collected.append(raw.strip())
    if not closed:
        return None
    return collected


def _filter_to_check_slugs(*, raw_lines: list[str]) -> list[str]:
    """Filter raw `targets=(...)` lines to `check-*`-prefixed slugs.

    Drops blank lines, full-line comments (`# ...`), and any token
    that doesn't start with `check-` — this matches the spec's
    "filter to slugs starting with `check-`" rule, which deliberately
    skips justfile aggregate sub-targets like `bootstrap` or `fmt`.
    """
    out: list[str] = []
    for line in raw_lines:
        if not line or line.startswith("#"):
            continue
        # Strip any trailing inline comment. The pre-strip in
        # `_extract_targets_array_lines` guarantees `line` has no
        # leading whitespace, so any line reaching here that does
        # NOT start with `#` has at least one non-`#` leading
        # character — the post-`split` token is therefore non-empty.
        token = line.split("#", 1)[0].strip()
        if not token.startswith(_CHECK_PREFIX):
            continue
        out.append(token)
    return out


@dataclass(frozen=True, kw_only=True)
class _ComparisonResult:
    """Outcome of the canonical-subset comparison against the wired targets."""

    missing: tuple[str, ...]
    out_of_order: bool


def _compare_canonical_subset(
    *,
    canonical: tuple[str, ...],
    wired: list[str],
) -> _ComparisonResult:
    """Compare wired targets against canonical slugs.

    - Missing: canonical minus wired (preserves canonical ordering).
    - Out-of-order: any of three conditions
      a. the canonical subset within `wired` (i.e. just the wired
         items that are canonical, in their wired order) does NOT
         equal the canonical tuple itself; OR
      b. any extra (non-canonical) wired slug appears BEFORE the
         last canonical slug — this catches extras-before /
         extras-interleaved arrangements that the per-subset check
         would otherwise accept.
    """
    canonical_set = set(canonical)
    wired_set = set(wired)
    missing = tuple(s for s in canonical if s not in wired_set)
    # When any canonical slug is absent the canonical-subset within
    # wired is necessarily shorter than the canonical tuple and would
    # also flag as "out of order"; that's noisy. The "missing" failure
    # mode carries the diagnostic — skip the ordering check entirely
    # and return early with `out_of_order=False`.
    if missing:
        return _ComparisonResult(missing=missing, out_of_order=False)
    canonical_subset_in_wired = [s for s in wired if s in canonical_set]
    subset_misordered = canonical_subset_in_wired != list(canonical)
    # Position-of-last-canonical guard: any non-canonical wired slug
    # whose index is less than the last canonical slug's index is an
    # extra placed before or interleaved with the canonical block.
    last_canonical_index = -1
    for i, slug in enumerate(wired):
        if slug in canonical_set:
            last_canonical_index = i
    extras_before_or_interleaved = any(
        i < last_canonical_index and slug not in canonical_set for i, slug in enumerate(wired)
    )
    out_of_order = subset_misordered or extras_before_or_interleaved
    return _ComparisonResult(missing=missing, out_of_order=out_of_order)


def _emit_missing(*, log: structlog.stdlib.BoundLogger, slug: str) -> None:
    log.error(
        "canonical check slug is not wired in the consumer's `just check` aggregate",
        check_id="aggregate_completeness",
        failure_mode="missing_canonical_slug",
        slug=slug,
        status="fail",
    )


def _emit_out_of_order(
    *,
    log: structlog.stdlib.BoundLogger,
    canonical: tuple[str, ...],
    observed: list[str],
) -> None:
    log.error(
        (
            "canonical check slugs in the consumer's `just check` aggregate are not in "
            "alphabetical order (or extras are interleaved with the canonical block)"
        ),
        check_id="aggregate_completeness",
        failure_mode="out_of_order_canonical_slugs",
        canonical_order=list(canonical),
        observed_order=list(observed),
        status="fail",
    )


def _emit_absence(
    *,
    log: structlog.stdlib.BoundLogger,
    failure_mode: str,
    message: str,
    path: str,
) -> None:
    log.error(
        message,
        check_id="aggregate_completeness",
        failure_mode=failure_mode,
        path=path,
        status="fail",
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    canonical_from: str | None = args.canonical_from
    log = _configure_logger()
    cwd = Path.cwd()
    loaded = _load_canonical(canonical_from=canonical_from, cwd=cwd)
    justfile_path = cwd / _JUSTFILE_NAME
    if not justfile_path.is_file():
        _emit_absence(
            log=log,
            failure_mode="justfile_not_found",
            message=f"justfile not found at {justfile_path}",
            path=str(justfile_path),
        )
        return _EXIT_VIOLATIONS
    justfile_text = justfile_path.read_text(encoding="utf-8")
    recipe_body = _extract_check_recipe_body(justfile_text=justfile_text)
    if recipe_body is None:
        _emit_absence(
            log=log,
            failure_mode="check_recipe_not_found",
            message="justfile has no `check:` recipe — cannot verify canonical aggregate",
            path=str(justfile_path),
        )
        return _EXIT_VIOLATIONS
    raw_targets = _extract_targets_array_lines(recipe_body=recipe_body)
    if raw_targets is None:
        _emit_absence(
            log=log,
            failure_mode="targets_array_not_found",
            message=(
                "`check:` recipe does not declare a `targets=(...)` array — "
                "cannot verify canonical aggregate"
            ),
            path=str(justfile_path),
        )
        return _EXIT_VIOLATIONS
    wired = _filter_to_check_slugs(raw_lines=raw_targets)
    result = _compare_canonical_subset(canonical=loaded.slugs, wired=wired)
    if not result.missing and not result.out_of_order:
        return 0
    for slug in result.missing:
        _emit_missing(log=log, slug=slug)
    if result.out_of_order:
        _emit_out_of_order(log=log, canonical=loaded.slugs, observed=wired)
    return _EXIT_VIOLATIONS


if __name__ == "__main__":
    raise SystemExit(main())
