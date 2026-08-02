"""_ci_matrix_parse — justfile + ci.yml parsers for `ci_matrix_completeness`.

Extracted from `ci_matrix_completeness.py` so the parent check's LLOC stays
under the 200-line ceiling — the same LLOC-reduction split as
`_red_green_replay_modes`. The leading underscore marks this a private
sibling module: entry-point check scripts under
`livespec_dev_tooling/checks/` carry no underscore prefix, so this file is
neither a canonical slug (`canonical_check_slugs` skips `_`-prefixed
modules) nor a mirror-paired module.

The parsers are regex-based and PURE — no IO, no logging — so the parent
owns every diagnostic. The `justfile` `check:` recipe / `targets=(...)`
anchors mirror `aggregate_completeness`; the `matrix.target` anchors
mirror `branch_protection_alignment`.

Parser-duplication convention — BOUNDED (maintainer decision on
work-item livespec-dev-tooling-6cf). This package's convention used to
read, unqualified, "each check duplicates small self-contained parsers
rather than sharing one". That unbounded form caused the
livespec-dev-tooling-ahg defect: the fleet surface carried its own copy
of the ci.yml parser, the copy never learned the spec's
top-level-gate-job acceptance rule, and the drifted copy reported eight
false positives against a correctly configured fleet. The convention is
therefore bounded:

- Duplication REMAINS PERMITTED for mechanical-extraction parsers
  ("give me the job names"): a copy is cheap, and two copies that
  disagree produce an obvious, quickly-caught bug.
- Duplication is FORBIDDEN for any parser that encodes a rule
  originating in the spec (e.g. "a top-level gate job counts as a
  valid required check even though it is not a matrix leg"): such a
  parser MUST live in a shared module imported by every consumer. Two
  copies of a rule-encoding parser can silently disagree about WHAT
  THE SPEC SAYS while the wrong copy still reads as a faithful
  implementation; derived from ONE parser, its consumers cannot
  drift.
- The mechanical marker for "rule-encoding": a parser whose docstring
  or comments cite a livespec SPECIFICATION section (the house
  citation style, e.g. `Per
  livespec/SPECIFICATION/non-functional-requirements.md section "CI as a
  merge gate (branch protection)"`) is by definition rule-encoding
  and MUST be shared, never duplicated per check.

Precedent for the sharing half: `_ci_job_names.py`, the shared home
extracted by the livespec-dev-tooling-ahg fix for the
branch-protection name grammar, imported by BOTH
`branch_protection_alignment` and the fleet `assert_branch_protection`
row — the pair whose previously independent copies drifted. A
duplicate that STAYS: `_tool_backed_surfaces.py`'s
`_parse_ci_matrix_targets` is a mechanical extractor carrying no spec
citation, so it is PERMITTED under the bound — do not consolidate it
reflexively.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

# Carried even though this module is only ever reached BY IMPORT today: it
# resolves only because each of its importers happens to carry the preamble,
# which is a property of the callers rather than of this file. The module that
# broke the fan-out was in exactly this state until it became an entry point.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.canonical_checks import canonical_check_slugs  # noqa: E402
from livespec_dev_tooling.checks._check_aggregate_failures import (  # noqa: E402
    CanonicalOverrideFailure,
    CanonicalOverrideUnparseable,
    CanonicalOverrideUnreadable,
    CheckRecipeAbsent,
    TargetsArrayAbsent,
    TargetsArrayFailure,
    TargetsArrayUnterminated,
)

# Names in `__all__` mark this private sibling's public surface to its two
# importers — `ci_matrix_completeness.py` (the gate) and
# `cross_repo/ci_yaml_canonical_reconcile.py` (the bump-time reconcile that
# WRITES what the gate then demands) — so pyright's per-file analysis does not
# flag them unused across the package boundary. The reconcile shares these
# parsers per the bounded parser-duplication convention in the module
# docstring: the matrix it writes and the matrix the gate requires are
# derived from ONE parser and cannot drift into a red-by-construction
# bump PR.
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

# A BROADENED `just <target>` invocation — any target, canonical or not —
# used only for the (b) gating classification (`livespec-dev-tooling-o6b`). A
# job that runs a non-canonical gating target (`just e2e-cli`, `just
# acceptance`, `just check-doctor-static`) contributes no canonical slug, so
# `_JUST_RUN_INVOCATION` (canonical-only, feeding assertion (a)) misses it —
# yet (b) must still require it in `ci-green.needs`. The matrix leg `just ${{
# matrix.target }}` cannot match (`${{` is not a `[\w-]` token), so a matrix
# job is classified gating via its `strategy.matrix.target` list instead (see
# `_build_job`). `export-telemetry`/`enable-auto-merge`/`setup` run no `just`
# target and carry no matrix, so they are excluded with no hardcoded denylist.
_JUST_RUN_ANY = re.compile(r"\bjust\s+([\w-]+)\b")

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
    """One top-level ci.yml job: its name, `needs:`, check slugs, and gating flag.

    `contributed_check_slugs` (the CANONICAL slugs the job runs) feeds
    assertion (a). `gating` — whether the job runs any `just <target>`
    command or carries a `strategy.matrix.target` list — feeds the BROADER
    assertion (b): a `ci-green` gate must fan in every gating job, canonical
    or not (`livespec-dev-tooling-o6b`).
    """

    name: str
    needs: frozenset[str]
    contributed_check_slugs: frozenset[str]
    gating: bool


def load_canonical(
    *, canonical_from: str | None, cwd: Path
) -> IOResult[tuple[str, ...], CanonicalOverrideFailure]:
    """Resolve the canonical-slug tuple from an override file or live discovery.

    Both reads of the override file used to be UNGUARDED, so a missing or
    malformed `--canonical-from` raised `FileNotFoundError` / `JSONDecodeError`
    out of a check. Unreadable and unparseable stay apart on the pin walkers'
    ground: a can't-read may be environmental and may not reproduce, a
    can't-parse is a definitive property of the file's committed bytes.

    ⛔ THE EMPTY TUPLE IS STILL AN ANSWER AND IS DELIBERATELY UNCHANGED. A
    readable, parseable override whose `slugs` is not a list answers
    `IOSuccess(())`, exactly as before. That tuple is load-bearing, and it is
    also what a legitimately-empty `slugs: []` yields — two SUCCESS-track
    meanings that are a real second question and not this conversion's to
    settle. What the conversion removes is a READ failure being spelled the
    same way as either of them.
    """
    if canonical_from is None:
        # `unsafe_perform_io(...unwrap())` is FAIL-CLOSED and deliberate.
        # `canonical_check_slugs` is `IOResult` since `livespec-dev-tooling-vzwa`,
        # and its failure means the installed `checks/` package is unreadable — a
        # broken install, not a reachable state for a check running out of that same
        # package. A `match` arm here could never be covered under this repo's
        # 100%-per-file gate, so raising beats a dead branch (`#846`'s precedent).
        # ⛔ NOT `value_or(())`: this function's OTHER early return is already `()`
        # for a malformed override, and an empty canonical set is read downstream as
        # "no canonical checks" and PASSES — the exact fail-open vzwa removed. The
        # two must stay distinguishable.
        return IOSuccess(unsafe_perform_io(canonical_check_slugs().unwrap()))
    path = (cwd / canonical_from).resolve()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as unreadable:
        return IOFailure(CanonicalOverrideUnreadable(path=str(path), detail=str(unreadable)))
    try:
        parsed = cast("object", json.loads(text))
    except ValueError as undecodable:
        return IOFailure(CanonicalOverrideUnparseable(path=str(path), detail=str(undecodable)))
    override = cast("_SlugOverride", parsed) if isinstance(parsed, dict) else None
    slug_field: list[object] | None = override.get("slugs") if override is not None else None
    if not isinstance(slug_field, list):
        return IOSuccess(())
    return IOSuccess(tuple(s for s in slug_field if isinstance(s, str)))


def extract_check_recipe_body(*, justfile_text: str) -> Result[str, CheckRecipeAbsent]:
    """The text body of the bare `check:` recipe.

    An absent recipe is a FAILURE rather than an answer because every caller
    reports it as its OWN inability — `check_recipe_not_found`, "cannot
    verify" — which is §4d-BIS's caller test for CONVERT over DECLARE.
    """
    header_match = _CHECK_RECIPE_HEADER.search(justfile_text)
    if header_match is None:
        return Failure(CheckRecipeAbsent())
    body_lines: list[str] = []
    for raw in justfile_text[header_match.end() :].splitlines():
        if raw and not raw.startswith((" ", "\t")) and ":" in raw:
            break
        body_lines.append(raw)
    return Success("\n".join(body_lines))


def extract_targets_array_tokens(*, recipe_body: str) -> Result[list[str], TargetsArrayFailure]:
    """The `check-*` slugs inside `targets=(...)`.

    TWO failure types, and the split is the defect this conversion fixes. An
    absent array and an UNTERMINATED one returned the same `None`, and every
    caller reported only the absent case — so a recipe whose array is merely
    unclosed sent the operator to add an array already present. The `closed`
    flag the old body needed disappears with the collapse.
    """
    start_match = _TARGETS_ARRAY_START.search(recipe_body)
    if start_match is None:
        return Failure(TargetsArrayAbsent())
    collected: list[str] = []
    for raw in recipe_body[start_match.end() :].splitlines():
        if _TARGETS_ARRAY_END.match(raw):
            return Success(collected)
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split("#", 1)[0].strip()
        if token.startswith(_CHECK_PREFIX):
            collected.append(token)
    return Failure(TargetsArrayUnterminated())


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


def _runs_any_just(*, body_lines: list[str]) -> bool:
    """Whether a job invokes any `just <target>` command in a non-comment line."""
    for raw in body_lines:
        if raw.strip().startswith("#"):
            continue
        if _JUST_RUN_ANY.search(raw) is not None:
            return True
    return False


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
    gating = bool(matrix_targets) or _runs_any_just(body_lines=body_lines)
    return CiJob(
        name=name,
        needs=_parse_job_needs(body_lines=body_lines),
        contributed_check_slugs=frozenset(contributed),
        gating=gating,
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
