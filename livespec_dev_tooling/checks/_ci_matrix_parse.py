"""_ci_matrix_parse — justfile + ci.yml parsers for `ci_matrix_completeness`.

Extracted from `ci_matrix_completeness.py` so the parent check's LLOC stays
under the 200-line ceiling — the same LLOC-reduction split as
`_red_green_replay_modes`. The leading underscore marks this a private
sibling module: entry-point check scripts under
`livespec_dev_tooling/checks/` carry no underscore prefix, so this file is
neither a canonical slug (`canonical_check_slugs` skips `_`-prefixed
modules) nor a mirror-paired module.

The parsers are regex-based per the package convention (each check
duplicates small self-contained parsers rather than sharing one) and are
PURE — no IO, no logging — so the parent owns every diagnostic. The
`justfile` `check:` recipe / `targets=(...)` anchors mirror
`aggregate_completeness`; the `matrix.target` anchors mirror
`branch_protection_alignment`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from livespec_dev_tooling.canonical_checks import canonical_check_slugs

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `ci_matrix_completeness.py`, so pyright's per-file analysis does
# not flag them unused across the package boundary.
__all__: list[str] = [
    "CiJob",
    "extract_check_recipe_body",
    "extract_targets_array_tokens",
    "load_canonical",
    "parse_ci_jobs",
]

_CHECK_PREFIX = "check-"

# justfile `check:` recipe + `targets=(...)` array anchors.
_CHECK_RECIPE_HEADER = re.compile(r"^check:\s*$", re.MULTILINE)
_TARGETS_ARRAY_START = re.compile(r"^\s*targets=\(\s*$", re.MULTILINE)
_TARGETS_ARRAY_END = re.compile(r"^\s*\)\s*$")

# ci.yml `matrix.target` anchors (applied per-job so targets attribute to the
# owning job) + the top-level `jobs:` table anchor + a `just <check-slug>`
# run-line invocation. The matrix leg reads `just ${{ matrix.target }}`, whose
# `${{` cannot match `check-...`, so matrix targets are counted only via the
# matrix parser and never double-counted from run lines.
_MATRIX_HEADER = re.compile(r"^\s*matrix:\s*$")
_MATRIX_TARGET_KEY = re.compile(r"^\s*target:\s*$")
_MATRIX_TARGET_LINE = re.compile(r"^\s*-\s*([\w-]+)\s*$")
_JOBS_HEADER = re.compile(r"^jobs:\s*$")
_JUST_RUN_INVOCATION = re.compile(r"\bjust\s+(check-[\w-]+)\b")

# `needs:` in its three YAML shapes: inline scalar (`needs: setup`), inline
# flow list (`needs: [a, b]`), and a block list (`needs:` then `- a` bullets).
_NEEDS_BLOCK_KEY = re.compile(r"^\s*needs:\s*$")
_NEEDS_INLINE = re.compile(r"^\s*needs:\s*(\S.*?)\s*$")
_NEEDS_BULLET = re.compile(r"^\s*-\s*([\w-]+)\s*$")


class _SlugOverride(TypedDict, total=False):
    """Shape of the `--canonical-from` JSON override file: `{"slugs": [...]}`."""

    slugs: list[object]


@dataclass(frozen=True, kw_only=True)
class CiJob:
    """One top-level ci.yml job: its name, its `needs:`, and its check slugs."""

    name: str
    needs: frozenset[str]
    contributed_check_slugs: frozenset[str]


def load_canonical(*, canonical_from: str | None, cwd: Path) -> tuple[str, ...]:
    """Resolve the canonical-slug tuple from an override file or live discovery."""
    if canonical_from is None:
        return canonical_check_slugs()
    parsed = json.loads((cwd / canonical_from).resolve().read_text(encoding="utf-8"))
    override = cast("_SlugOverride", parsed) if isinstance(parsed, dict) else None
    slug_field: list[object] | None = override.get("slugs") if override is not None else None
    if not isinstance(slug_field, list):
        return ()
    return tuple(s for s in slug_field if isinstance(s, str))


def extract_check_recipe_body(*, justfile_text: str) -> str | None:
    """Return the text body of the `check:` recipe, or None when absent."""
    header_match = _CHECK_RECIPE_HEADER.search(justfile_text)
    if header_match is None:
        return None
    body_lines: list[str] = []
    for raw in justfile_text[header_match.end() :].splitlines():
        if raw and not raw.startswith((" ", "\t")) and ":" in raw:
            break
        body_lines.append(raw)
    return "\n".join(body_lines)


def extract_targets_array_tokens(*, recipe_body: str) -> list[str] | None:
    """Return the `check-*` slugs inside `targets=(...)`, or None when absent."""
    start_match = _TARGETS_ARRAY_START.search(recipe_body)
    if start_match is None:
        return None
    collected: list[str] = []
    closed = False
    for raw in recipe_body[start_match.end() :].splitlines():
        if _TARGETS_ARRAY_END.match(raw):
            closed = True
            break
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split("#", 1)[0].strip()
        if token.startswith(_CHECK_PREFIX):
            collected.append(token)
    return collected if closed else None


def _parse_matrix_targets(*, body_lines: list[str]) -> set[str]:
    """Extract a job's `strategy.matrix.target` slugs from its body lines."""
    targets: set[str] = set()
    in_matrix = False
    in_target_list = False
    for raw in body_lines:
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


def _parse_run_slugs(*, body_lines: list[str]) -> set[str]:
    """Extract every `just <check-slug>` invocation from a job's `run:` lines."""
    slugs: set[str] = set()
    for raw in body_lines:
        if raw.strip().startswith("#"):
            continue
        for match in _JUST_RUN_INVOCATION.finditer(raw):
            slugs.add(match.group(1))
    return slugs


def _parse_needs_value(*, value: str) -> set[str]:
    """Parse a scalar (`setup`) or flow-list (`[a, b]`) `needs:` value."""
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return set()
        return {token.strip() for token in inner.split(",")}
    return {text}


def _parse_job_needs(*, body_lines: list[str]) -> frozenset[str]:
    """Extract a job's `needs:` job names across the scalar/flow/block shapes."""
    needs: set[str] = set()
    in_block = False
    for raw in body_lines:
        if in_block:
            bullet = _NEEDS_BULLET.match(raw)
            if bullet is not None:
                needs.add(bullet.group(1))
                continue
            in_block = False
        if _NEEDS_BLOCK_KEY.match(raw):
            in_block = True
            continue
        inline = _NEEDS_INLINE.match(raw)
        if inline is not None:
            needs |= _parse_needs_value(value=inline.group(1))
    return frozenset(needs)


def _build_job(*, name: str, body_lines: list[str]) -> CiJob:
    """Assemble a `CiJob` from its name and body lines."""
    matrix_targets = _parse_matrix_targets(body_lines=body_lines)
    run_slugs = _parse_run_slugs(body_lines=body_lines)
    contributed = {t for t in matrix_targets if t.startswith(_CHECK_PREFIX)} | run_slugs
    return CiJob(
        name=name,
        needs=_parse_job_needs(body_lines=body_lines),
        contributed_check_slugs=frozenset(contributed),
    )


def _detect_job_indent(*, lines: list[str]) -> int | None:
    """Return the leading-space count of the first job key under `jobs:`."""
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return len(raw) - len(raw.lstrip())
    return None


def _find_jobs_body(*, lines: list[str]) -> list[str] | None:
    """Return the lines under the top-level `jobs:` key, or None when absent."""
    for i, raw in enumerate(lines):
        if _JOBS_HEADER.match(raw):
            return lines[i + 1 :]
    return None


def _split_job_blocks(*, body: list[str], job_indent: int) -> list[tuple[str, list[str]]]:
    """Split the jobs-table body into (job-name, body-lines) blocks.

    A job header is a key at exactly `job_indent`; its block extends to the
    next such header or to the first line dedented below `job_indent` (a
    following top-level workflow key). Lines before the first header (e.g. a
    leading comment) belong to no block and are dropped.
    """
    header_re = re.compile(rf"^ {{{job_indent}}}([A-Za-z0-9_-]+):\s*$")
    blocks: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for raw in body:
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if stripped and not stripped.startswith("#") and indent < job_indent:
            break
        header = header_re.match(raw)
        if header is not None:
            current = (header.group(1), [])
            blocks.append(current)
            continue
        if current is not None:
            current[1].append(raw)
    return blocks


def parse_ci_jobs(*, source: str) -> list[CiJob]:
    """Split a ci.yml into its top-level jobs (name, needs, contributed slugs)."""
    body = _find_jobs_body(lines=source.splitlines())
    if body is None:
        return []
    job_indent = _detect_job_indent(lines=body)
    if job_indent is None:
        return []
    return [
        _build_job(name=name, body_lines=block)
        for name, block in _split_job_blocks(body=body, job_indent=job_indent)
    ]
