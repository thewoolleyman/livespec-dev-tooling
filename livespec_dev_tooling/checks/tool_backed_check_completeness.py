"""tool_backed_check_completeness — every tool-backed check is wired on BOTH surfaces.

Per epic `li-pyright-gate` (work-item `li-pyright-gate-wi3`), this
meta-check closes the gating gap that let the four tool-backed
checks (lint, format, types, coverage) silently fall out of one
enforcement surface without the other noticing. A tool-backed check
that is wired into the local `just check` aggregate but NOT into the
CI matrix (or vice versa) gives a false sense of coverage: a
contributor sees green locally while CI never runs the check, or CI
gates while local `just check` skips it.

The check uses the **literal-membership** design settled for
`li-pyright-gate-wi3`: each tool-backed check MUST appear as a
LITERAL token in BOTH

1. the consumer's `justfile` `check:` recipe's `targets=(...)` array, AND
2. at least one CI workflow's `matrix.target` list under
   `.github/workflows/*.yml`.

"Literal" means the slug text itself is present — transitive
reachability (a recipe that internally shells another recipe) does
NOT count. Literal membership is what makes the two surfaces
mechanically comparable and is what this check enforces.

The tool-backed slug set is fixed policy: `check-lint`,
`check-format`, `check-types`, `check-coverage`. These are the
ruff / pyright / coverage gates that are NOT canonical-aggregate
slugs (they live as helper recipes, not under
`livespec_dev_tooling/checks/`), so `aggregate_completeness` does
not enforce them. This meta-check is their dedicated guard.

Algorithm:

1. Resolve the tool-backed slug set. Default: the fixed policy
   tuple. Override via `--tool-backed-from <path>` pointing to a
   JSON file with shape `{"slugs": [...]}` — used by tests to inject
   hermetic synthetic sets.
2. Resolve the `justfile` (cwd-relative). Failure → exit 4 with
   `justfile_not_found` finding.
3. Locate the `check:` recipe, then its `targets=(...)` array.
   Failure → exit 4 with `check_recipe_not_found` /
   `targets_array_not_found` finding.
4. Resolve the workflows directory (`.github/workflows`). Absence →
   exit 4 with `workflows_dir_not_found` finding (a consumer that
   gates locally but has no CI cannot satisfy the both-surfaces
   invariant).
5. Collect every `matrix.target` slug across all `*.yml` / `*.yaml`
   workflow files.
6. For each tool-backed slug, emit a `missing_from_justfile` finding
   when it is absent from the targets array, and a `missing_from_ci`
   finding when it is absent from every CI matrix. Any finding → exit 4.

Exit codes:

- `0` — every tool-backed slug is a literal member of BOTH surfaces.
- `2` — usage error (bad CLI invocation; argparse-driven).
- `4` — one or more rule violations, or a graceful-absence
  precondition failure; structured findings on stderr.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at
module import time so the check works via `python -m` and via direct
script invocation.

Self-bootstrapping property: because this module lives under
`livespec_dev_tooling/checks/`, its own slug
(`check-tool-backed-check-completeness`) is a canonical slug
discovered by `canonical_check_slugs`, so `aggregate_completeness`
forces it into the consumer's `just check` aggregate. This check in
turn forces the four tool-backed slugs onto BOTH surfaces.
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

__all__: list[str] = []


_JUSTFILE_NAME = "justfile"
_WORKFLOWS_DIR = Path(".github") / "workflows"
_EXIT_VIOLATIONS = 4

# Fixed policy: the four tool-backed checks (ruff lint, ruff format,
# pyright types, coverage) that are NOT canonical-aggregate slugs and
# therefore are not guarded by aggregate_completeness. Each MUST be a
# literal member of BOTH the `just check` targets array and a CI
# matrix.
_DEFAULT_TOOL_BACKED_SLUGS: tuple[str, ...] = (
    "check-lint",
    "check-format",
    "check-types",
    "check-coverage",
)

# justfile `check:` recipe + `targets=(...)` array anchors (mirrors
# aggregate_completeness's parser so the two checks agree on what
# "literal targets-array membership" means).
_CHECK_RECIPE_HEADER = re.compile(r"^check:\s*$", re.MULTILINE)
_TARGETS_ARRAY_START = re.compile(r"^\s*targets=\(\s*$", re.MULTILINE)
_TARGETS_ARRAY_END = re.compile(r"^\s*\)\s*$")

# CI matrix anchors (mirrors branch_protection_alignment's parser).
_MATRIX_HEADER = re.compile(r"^\s*matrix:\s*$")
_MATRIX_TARGET_KEY = re.compile(r"^\s*target:\s*$")
_MATRIX_TARGET_LINE = re.compile(r"^\s*-\s*([\w-]+)\s*$")


class _SlugOverride(TypedDict, total=False):
    """Shape of the `--tool-backed-from` JSON override file: `{"slugs": [...]}`.

    `total=False` mirrors the defensive `.get("slugs")` access — the key is
    optional, so the typed boundary matches runtime semantics exactly. `slugs`
    is typed as a list of `object` (not `str`) so the per-element
    `isinstance(s, str)` filter in `_load_tool_backed_slugs` stays a
    load-bearing runtime guard against a malformed override file.
    """

    slugs: list[object]


@dataclass(frozen=True, kw_only=True)
class _SurfacePresence:
    """Whether one tool-backed slug is present on each enforcement surface."""

    slug: str
    in_justfile: bool
    in_ci: bool


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tool-backed-check-completeness",
        description=(
            "Enforce that every tool-backed check (lint, format, types, "
            "coverage) is a LITERAL member of BOTH the `just check` targets "
            "array AND a CI matrix. Dedicated guard for the tool-backed slugs "
            "that aggregate-completeness does not cover (epic li-pyright-gate)."
        ),
    )
    _ = parser.add_argument(
        "--tool-backed-from",
        type=str,
        default=None,
        help=(
            'Path to a JSON file with shape `{"slugs": [...]}` overriding '
            "the fixed tool-backed slug set. Reserved for hermetic test "
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
    return structlog.get_logger("tool_backed_check_completeness")


def _load_tool_backed_slugs(*, tool_backed_from: str | None, cwd: Path) -> tuple[str, ...]:
    """Resolve the tool-backed slug tuple from either an override file or the policy default."""
    if tool_backed_from is None:
        return _DEFAULT_TOOL_BACKED_SLUGS
    path = (cwd / tool_backed_from).resolve()
    text = path.read_text(encoding="utf-8")
    # The `cast` is the single typed parse boundary: `json.loads` yields
    # `Any`, the `isinstance` guard narrows to `dict`, and the cast then
    # asserts the validated shape so `.get("slugs")` and the comprehension
    # over its elements are typed.
    parsed = json.loads(text)
    override = cast("_SlugOverride", parsed) if isinstance(parsed, dict) else None
    slug_field: list[object] | None = override.get("slugs") if override is not None else None
    if not isinstance(slug_field, list):
        return ()
    return tuple(s for s in slug_field if isinstance(s, str))


def _extract_check_recipe_body(*, justfile_text: str) -> str | None:
    """Return the text body of the `check:` recipe, or None when absent.

    A just recipe body extends from the recipe header to the next
    recipe header (a non-indented line ending in `:`) or to EOF.
    """
    header_match = _CHECK_RECIPE_HEADER.search(justfile_text)
    if header_match is None:
        return None
    body_start = header_match.end()
    lines = justfile_text[body_start:].splitlines()
    body_lines: list[str] = []
    for raw in lines:
        if raw and not raw.startswith((" ", "\t")) and ":" in raw:
            break
        body_lines.append(raw)
    return "\n".join(body_lines)


def _extract_targets_array_tokens(*, recipe_body: str) -> list[str] | None:
    """Return the `check-*` slugs inside `targets=(...)`, or None when absent.

    Blank lines, full-line comments, inline trailing comments, and any
    token that does not start with `check-` are dropped — matching
    aggregate_completeness's filtering so the two checks agree on what
    counts as a literal targets-array slug.
    """
    start_match = _TARGETS_ARRAY_START.search(recipe_body)
    if start_match is None:
        return None
    after_start = recipe_body[start_match.end() :]
    collected: list[str] = []
    closed = False
    for raw in after_start.splitlines():
        if _TARGETS_ARRAY_END.match(raw):
            closed = True
            break
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split("#", 1)[0].strip()
        if token.startswith("check-"):
            collected.append(token)
    if not closed:
        return None
    return collected


def _parse_ci_matrix_targets(*, source: str) -> set[str]:
    """Extract every `matrix.target` job slug from one workflow file's text.

    Walks the file line-by-line: enters the `matrix:` table, then the
    `target:` key, then collects `- check-foo` bullet entries until a
    non-bullet line ends the list.
    """
    targets: set[str] = set()
    in_matrix = False
    in_target_list = False
    for raw in source.splitlines():
        if _MATRIX_HEADER.match(raw):
            in_matrix = True
            in_target_list = False
            continue
        if not in_matrix:
            continue
        if _MATRIX_TARGET_KEY.match(raw):
            in_target_list = True
            continue
        if in_target_list:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _MATRIX_TARGET_LINE.match(raw)
            if match is None:
                in_target_list = False
                continue
            targets.add(match.group(1))
    return targets


def _collect_ci_matrix_targets(*, workflows_dir: Path) -> set[str]:
    """Union the `matrix.target` slugs across every workflow file in the dir."""
    targets: set[str] = set()
    for path in sorted(workflows_dir.glob("*.yml")):
        targets |= _parse_ci_matrix_targets(source=path.read_text(encoding="utf-8"))
    for path in sorted(workflows_dir.glob("*.yaml")):
        targets |= _parse_ci_matrix_targets(source=path.read_text(encoding="utf-8"))
    return targets


def _emit_absence(
    *,
    log: structlog.stdlib.BoundLogger,
    failure_mode: str,
    message: str,
    path: str,
) -> None:
    log.error(
        message,
        check_id="tool_backed_check_completeness",
        failure_mode=failure_mode,
        path=path,
        status="fail",
    )


def _emit_missing(
    *,
    log: structlog.stdlib.BoundLogger,
    failure_mode: str,
    message: str,
    slug: str,
) -> None:
    log.error(
        message,
        check_id="tool_backed_check_completeness",
        failure_mode=failure_mode,
        slug=slug,
        status="fail",
    )


def _evaluate(
    *,
    tool_backed: tuple[str, ...],
    justfile_targets: list[str],
    ci_targets: set[str],
) -> list[_SurfacePresence]:
    """Compute per-slug presence on each surface, in the tool-backed order."""
    justfile_set = set(justfile_targets)
    return [
        _SurfacePresence(
            slug=slug,
            in_justfile=slug in justfile_set,
            in_ci=slug in ci_targets,
        )
        for slug in tool_backed
    ]


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    tool_backed_from: str | None = args.tool_backed_from
    log = _configure_logger()
    cwd = Path.cwd()
    tool_backed = _load_tool_backed_slugs(tool_backed_from=tool_backed_from, cwd=cwd)

    justfile_path = cwd / _JUSTFILE_NAME
    if not justfile_path.is_file():
        _emit_absence(
            log=log,
            failure_mode="justfile_not_found",
            message=f"justfile not found at {justfile_path}",
            path=str(justfile_path),
        )
        return _EXIT_VIOLATIONS
    recipe_body = _extract_check_recipe_body(
        justfile_text=justfile_path.read_text(encoding="utf-8")
    )
    if recipe_body is None:
        _emit_absence(
            log=log,
            failure_mode="check_recipe_not_found",
            message="justfile has no `check:` recipe — cannot verify tool-backed wiring",
            path=str(justfile_path),
        )
        return _EXIT_VIOLATIONS
    justfile_targets = _extract_targets_array_tokens(recipe_body=recipe_body)
    if justfile_targets is None:
        _emit_absence(
            log=log,
            failure_mode="targets_array_not_found",
            message=(
                "`check:` recipe does not declare a `targets=(...)` array — "
                "cannot verify tool-backed wiring"
            ),
            path=str(justfile_path),
        )
        return _EXIT_VIOLATIONS

    workflows_dir = cwd / _WORKFLOWS_DIR
    if not workflows_dir.is_dir():
        _emit_absence(
            log=log,
            failure_mode="workflows_dir_not_found",
            message=(
                "no `.github/workflows` directory — a consumer that gates "
                "tool-backed checks locally MUST also gate them in CI"
            ),
            path=str(workflows_dir),
        )
        return _EXIT_VIOLATIONS
    ci_targets = _collect_ci_matrix_targets(workflows_dir=workflows_dir)

    presences = _evaluate(
        tool_backed=tool_backed,
        justfile_targets=justfile_targets,
        ci_targets=ci_targets,
    )
    violated = False
    for presence in presences:
        if not presence.in_justfile:
            violated = True
            _emit_missing(
                log=log,
                failure_mode="missing_from_justfile",
                message=(
                    "tool-backed check is not a literal member of the `just check` " "targets array"
                ),
                slug=presence.slug,
            )
        if not presence.in_ci:
            violated = True
            _emit_missing(
                log=log,
                failure_mode="missing_from_ci",
                message="tool-backed check is not a literal member of any CI matrix",
                slug=presence.slug,
            )
    if violated:
        return _EXIT_VIOLATIONS
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
