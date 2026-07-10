"""canonical_recipe_fidelity — every canonical `check-<slug>:` recipe invokes the shared module.

Anti-fork guard. `aggregate_completeness` verifies that every
canonical slug is PRESENT in the consumer's `just check`
`targets=(...)` array (membership + ordering); `tool_backed_check_completeness`
verifies the four tool slugs appear on both surfaces. NEITHER inspects
the recipe BODY, so a consumer can satisfy both while silently forking
a shared check: point the `check-<slug>:` recipe at a local script or
a strictly-weaker `bash …/fork.sh` copy instead of the pinned shared
module. That is exactly the "B1" incident — an `all_declared` x `wrapper_shape`
conflict resolved by creating a local `dev-tooling/checks/wrapper-shape-compat.sh`
fork and repointing `check-wrapper-shape:` from
`uv run python -m livespec_dev_tooling.checks.wrapper_shape` to
`bash dev-tooling/checks/wrapper-shape-compat.sh`. This check closes
that gap by inspecting the recipe body.

Rule: for every canonical check slug, the consumer's `justfile` MUST
declare a `check-<slug>:` recipe whose body invokes the pinned shared
module `python -m livespec_dev_tooling.checks.<module>`, where
`<module>` is the slug with the `check-` prefix stripped and
kebab-case mapped to snake_case (e.g. `check-wrapper-shape` →
`wrapper_shape`). The realistic consumer form is
`uv run python -m livespec_dev_tooling.checks.<module>` possibly
followed by trailing args, so the check asserts the substring
`python -m livespec_dev_tooling.checks.<module>` is PRESENT in the
recipe body — a repointed recipe (local script / bash fork / different
module) fails.

Algorithm:

1. Resolve the canonical-slug tuple. Default: live discovery via
   `canonical_check_slugs()`. Override via `--canonical-from <path>`
   pointing to a JSON file with shape `{"slugs": [...]}` — used by
   tests to inject hermetic synthetic sets. The check uses the
   consumer's OWN pinned `livespec_dev_tooling` canonical set (exactly
   like `aggregate_completeness`), so it is version-appropriate and
   never demands a recipe for a slug the consumer's pinned version has
   not shipped.
2. Resolve `justfile` location (cwd-relative). Absence → exit 4 with a
   `justfile_not_found` finding.
3. For each canonical slug, locate the `check-<slug>:` recipe body.
   - Recipe absent → `canonical_recipe_missing` finding.
   - Recipe present but body lacks the shared-module invocation →
     `recipe_not_pinned_to_shared_module` finding.
   - Recipe body carries the test-only `--canonical-from` override flag →
     `override_flag_in_recipe` finding. This scan is run over the LIVE
     canonical set (unioned with the loaded set), NOT the possibly-emptied
     `--canonical-from` set, so a recipe that passes `--canonical-from
     empty.json` to neuter the gate is still caught — the guard's own
     recipe (a live canonical slug) is always inspected.

Exit codes:

- `0` — every canonical recipe is present and invokes the shared module.
- `1` — one or more fidelity violations (missing recipe, repointed
  recipe, or a recipe carrying the `--canonical-from` override flag);
  structured findings on stderr.
- `2` — usage error (bad CLI invocation; argparse default).
- `4` — the `justfile` could not be found at cwd.

The `1` vs. `4` split mirrors the brief: a fidelity violation is a
hard-gate failure (`1`); a missing `justfile` is a structural-absence
condition (`4`, matching `aggregate_completeness`).

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path`
at module import time so the check works equally well via
`python -m` and via direct script invocation.

Self-bootstrapping property: because this module lives under
`livespec_dev_tooling/checks/`, its own slug
(`check-canonical-recipe-fidelity`) is included in the canonical set
discovered by `canonical_check_slugs`. Running it in a consumer
therefore also verifies the consumer's `check-canonical-recipe-fidelity:`
recipe itself invokes the shared module — the gate validates its own
wiring.
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

from livespec_dev_tooling.canonical_checks import (  # noqa: E402
    canonical_check_slugs,
)

__all__: list[str] = []


_JUSTFILE_NAME = "justfile"
_CHECK_PREFIX = "check-"
_SHARED_MODULE_STEM = "python -m livespec_dev_tooling.checks."
# The `--canonical-from` override flag is a TEST-ONLY fixture surface. It must
# never appear in a consumer's justfile recipe body: placed there it neuters
# this very gate (a recipe passing `--canonical-from empty.json` with
# `{"slugs": []}` empties the canonical set, so the per-slug fidelity loop runs
# over nothing and a co-resident fork passes). Banning the flag in canonical
# recipe bodies closes that bypass.
_CANONICAL_FROM_FLAG = "--canonical-from"
_EXIT_FIDELITY_VIOLATIONS = 1
_EXIT_JUSTFILE_ABSENT = 4


class _CanonicalOverride(TypedDict, total=False):
    """Shape of the `--canonical-from` JSON override file: `{"slugs": [...]}`.

    `total=False` mirrors the defensive `.get("slugs")` access — the key is
    optional, so the typed boundary matches runtime semantics exactly.
    `slugs` is typed as a list of `object` (not `str`) so the per-element
    `isinstance(s, str)` filter in `_load_canonical` stays a load-bearing
    runtime guard against a malformed override file.
    """

    slugs: list[object]


@dataclass(frozen=True, kw_only=True)
class _LoadedCanonical:
    """Canonical-slug tuple plus the source label used in diagnostics."""

    slugs: tuple[str, ...]
    source: str


@dataclass(frozen=True, kw_only=True)
class _Violation:
    """One recipe-fidelity violation for a canonical slug."""

    slug: str
    failure_mode: str
    module: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canonical-recipe-fidelity",
        description=(
            "Enforce that every canonical `check-<slug>:` recipe in the "
            "consumer's justfile invokes the pinned shared module "
            "`python -m livespec_dev_tooling.checks.<module>` — the anti-fork "
            "guard that stops a consumer repointing a shared check at a local "
            "script or bash fork."
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
    return structlog.get_logger("canonical_recipe_fidelity")


def _load_canonical(*, canonical_from: str | None, cwd: Path) -> _LoadedCanonical:
    """Resolve the canonical-slug tuple from either an override file or live discovery."""
    if canonical_from is None:
        return _LoadedCanonical(slugs=canonical_check_slugs(), source="live")
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


def _slug_to_module(*, slug: str) -> str:
    """Map a `check-<kebab>` slug to its `<snake>` shared-module name.

    Strips the `check-` prefix and rewrites kebab-case to snake_case,
    matching `canonical_checks`' inverse `snake → check-kebab` mapping.
    `check-wrapper-shape` → `wrapper_shape`.
    """
    return slug.removeprefix(_CHECK_PREFIX).replace("-", "_")


def _extract_recipe_body(*, justfile_text: str, slug: str) -> str | None:
    """Return the body text of the `check-<slug>:` recipe, or None when absent.

    A just recipe header is a non-indented line beginning with the
    recipe name, followed by optional parameters/dependencies, then a
    `:`. The lookahead `(?=[ \\t:])` requires the character immediately
    after the slug to be whitespace or the colon — never `-` — so a
    lookup for `check-foo` does NOT match a `check-foo-bar:` header
    (prefix-collision guard). The body extends from the header line to
    the next recipe header (a non-indented line containing `:`) or to
    EOF, matching `aggregate_completeness._extract_check_recipe_body`.
    """
    header = re.compile(rf"^{re.escape(slug)}(?=[ \t:])[^\n]*?:", re.MULTILINE)
    header_match = header.search(justfile_text)
    if header_match is None:
        return None
    after_header = justfile_text[header_match.end() :]
    lines = after_header.splitlines()
    body_lines: list[str] = []
    # `lines[0]` is the remainder of the header line (dependencies /
    # trailing content after the matched `:`), not a body line — skip it.
    for raw in lines[1:]:
        # A new recipe header is a non-indented line that contains a
        # `:`. Stop the body at that line, NOT including it.
        if raw and not raw.startswith((" ", "\t")) and ":" in raw:
            break
        body_lines.append(raw)
    return "\n".join(body_lines)


def _classify_slug(*, justfile_text: str, slug: str) -> _Violation | None:
    """Return a `_Violation` when the slug's recipe is missing or repointed, else None."""
    module = _slug_to_module(slug=slug)
    body = _extract_recipe_body(justfile_text=justfile_text, slug=slug)
    if body is None:
        return _Violation(slug=slug, failure_mode="canonical_recipe_missing", module=module)
    expected = _SHARED_MODULE_STEM + module
    if expected not in body:
        return _Violation(
            slug=slug,
            failure_mode="recipe_not_pinned_to_shared_module",
            module=module,
        )
    return None


def _recipe_carries_override_flag(*, justfile_text: str, slug: str) -> bool:
    """Return True when the slug's recipe exists and its body carries `--canonical-from`.

    The override-flag scan is deliberately INDEPENDENT of the (attacker-
    controllable) `--canonical-from` slug set: an emptied override must not
    be able to neuter it. `main()` runs this over the LIVE canonical set
    (unioned with the loaded set) so the guard's own recipe — the one the
    bypass has to modify — is always inspected even when the loaded set is
    empty.
    """
    body = _extract_recipe_body(justfile_text=justfile_text, slug=slug)
    return body is not None and _CANONICAL_FROM_FLAG in body


def _emit_missing(*, log: structlog.stdlib.BoundLogger, violation: _Violation) -> None:
    log.error(
        (
            "canonical check slug has no `check-<slug>:` recipe in the consumer's "
            "justfile — the shared check is not wired at all"
        ),
        check_id="canonical_recipe_fidelity",
        failure_mode=violation.failure_mode,
        slug=violation.slug,
        expected_invocation=_SHARED_MODULE_STEM + violation.module,
        status="fail",
    )


def _emit_repointed(*, log: structlog.stdlib.BoundLogger, violation: _Violation) -> None:
    log.error(
        (
            "canonical `check-<slug>:` recipe does not invoke the pinned shared module — "
            "it has been repointed to a local script / bash fork / different module"
        ),
        check_id="canonical_recipe_fidelity",
        failure_mode=violation.failure_mode,
        slug=violation.slug,
        expected_invocation=_SHARED_MODULE_STEM + violation.module,
        status="fail",
    )


def _emit_override(*, log: structlog.stdlib.BoundLogger, violation: _Violation) -> None:
    log.error(
        (
            "canonical `check-<slug>:` recipe carries the test-only `--canonical-from` "
            "override flag — placed in a recipe body it neuters this gate (an empty "
            "override set skips every per-slug fidelity check)"
        ),
        check_id="canonical_recipe_fidelity",
        failure_mode=violation.failure_mode,
        slug=violation.slug,
        banned_flag=_CANONICAL_FROM_FLAG,
        status="fail",
    )


def _emit_absence(*, log: structlog.stdlib.BoundLogger, message: str, path: str) -> None:
    log.error(
        message,
        check_id="canonical_recipe_fidelity",
        failure_mode="justfile_not_found",
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
            message=f"justfile not found at {justfile_path}",
            path=str(justfile_path),
        )
        return _EXIT_JUSTFILE_ABSENT
    justfile_text = justfile_path.read_text(encoding="utf-8")
    # Override-flag scan: INDEPENDENT of the (attacker-controllable) loaded
    # slug set. Scan the union of the LIVE canonical set and the loaded set so
    # the guard's own recipe (a live slug — the one the bypass must modify) is
    # inspected even when `--canonical-from` empties the loaded set, AND a
    # hermetic synthetic recipe (a loaded slug) is inspected in tests. Ordered
    # de-dupe via `dict.fromkeys`.
    scan_slugs = list(dict.fromkeys([*canonical_check_slugs(), *loaded.slugs]))
    override_slugs = {
        slug
        for slug in scan_slugs
        if _recipe_carries_override_flag(justfile_text=justfile_text, slug=slug)
    }
    violations: list[_Violation] = [
        _Violation(
            slug=slug, failure_mode="override_flag_in_recipe", module=_slug_to_module(slug=slug)
        )
        for slug in scan_slugs
        if slug in override_slugs
    ]
    # Per-slug fidelity check over the loaded set; a slug already reported for
    # the override flag is not double-reported.
    for slug in loaded.slugs:
        if slug in override_slugs:
            continue
        fidelity = _classify_slug(justfile_text=justfile_text, slug=slug)
        if fidelity is not None:
            violations.append(fidelity)
    if not violations:
        return 0
    for violation in violations:
        if violation.failure_mode == "override_flag_in_recipe":
            _emit_override(log=log, violation=violation)
        elif violation.failure_mode == "canonical_recipe_missing":
            _emit_missing(log=log, violation=violation)
        else:
            _emit_repointed(log=log, violation=violation)
    return _EXIT_FIDELITY_VIOLATIONS


if __name__ == "__main__":
    raise SystemExit(main())
