"""_canonical_waivers — the one reader of a consumer's `canonical_check_waivers`.

The "Canonical-check waivers" paragraph of `SPECIFICATION/contracts.md`
(ratified v099 over livespec core v233) lets a consumer waive a canonical
check, with a reason, from its own `pyproject.toml`:

    [tool.livespec_dev_tooling]
    canonical_check_waivers = [{ slug = "check-x", reason = "why" }]

Two gates read that key and MUST agree about it: `check-aggregate-completeness`
(inside the consumer) and the fleet-conformance row `canonical-check-slugs-wired`
(from the fleet vantage, over a member's master tree). Both import this module
so the declaration is parsed, and judged stale or malformed, in exactly one
place. Neither reads a waiver from any other surface.

SETTLED WHERE THE SPEC LEFT IT OPEN.

- A waiver that is both stale and malformed is reported as MALFORMED only. A
  malformed entry is not a reliable declaration, so it is not asked whether the
  aggregate selects its slug; fixing it then surfaces the stale finding.
- A slug declared twice is malformed on its SECOND appearance; the first entry
  stands and is judged on its own merits.
- A waiver of `check-aggregate-completeness` itself is an ordinary waiver. The
  spec admits no exception, and a member that waives its own detector is still
  reported by the separate `aggregate-gate-wired` row.

An absent key declares no waiver. An unparseable file is a FAILURE, never an
absent key, because a caller that took it for "no waiver" would read an
unreadable declaration as a clean one. What each caller does on that failure
differs by spec and lives in the caller: the in-repo check applies no waiver, the
fleet row skips the member.
"""

from __future__ import annotations

import sys
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

# stdlib `tomllib` lands in 3.11; the repo floor is 3.10 (per
# `SPECIFICATION/constraints.md` section "Runtime"), so fall back to the
# vendored `tomli`, which exposes an identical `loads(text) -> dict`. The 3.11
# branch is never taken under the 3.10 test run, so it is coverage-exempt.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

if sys.version_info >= (3, 11):  # pragma: no cover — 3.11 path unused on the 3.10 floor.
    import tomllib as _toml
else:
    import tomli as _toml

from returns.io import impure_safe  # noqa: E402 — vendor-path-aware import.
from returns.result import Failure, Result, Success  # noqa: E402 — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402 — vendor-path-aware import.

__all__: list[str] = [
    "WAIVERS_KEY",
    "CanonicalWaiver",
    "DeclaredWaivers",
    "PyprojectUnparseable",
    "WaiverProblem",
    "WaiverVerdict",
    "consumer_waiver_verdict",
    "declared_waivers",
    "judge_waivers",
]


WAIVERS_KEY = "canonical_check_waivers"
_TABLE_KEY = "livespec_dev_tooling"
_ENTRY_KEYS = frozenset({"slug", "reason"})
_PYPROJECT_NAME = "pyproject.toml"


@dataclass(frozen=True, kw_only=True)
class CanonicalWaiver:
    """One well-formed waiver whose slug the aggregate does not select."""

    slug: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class WaiverProblem:
    """One stale or malformed waiver, named by slug or by array position."""

    kind: str
    subject: str
    detail: str

    def render(self) -> str:
        """The finding text: which waiver, and whether stale or malformed."""
        return f"{self.kind} canonical-check waiver for {self.subject}: {self.detail}"

    def fields(self, *, check_id: str) -> dict[str, str]:
        """The structured-log fields that accompany `render()` in a check's finding."""
        return {
            "check_id": check_id,
            "failure_mode": f"{self.kind}_canonical_waiver",
            "waiver": self.subject,
            "status": "fail",
        }


@dataclass(frozen=True, kw_only=True)
class WaiverVerdict:
    """What a consumer's declaration amounts to against one aggregate."""

    honoured: tuple[CanonicalWaiver, ...]
    problems: tuple[WaiverProblem, ...]


@dataclass(frozen=True, kw_only=True)
class DeclaredWaivers:
    """The raw `canonical_check_waivers` value; `[]` when the key is absent."""

    value: object


@dataclass(frozen=True, kw_only=True)
class PyprojectUnparseable:
    """The `pyproject.toml` text is not valid TOML."""

    detail: str


def declared_waivers(*, pyproject_text: str) -> Result[DeclaredWaivers, PyprojectUnparseable]:
    """The waiver value `[tool.livespec_dev_tooling]` carries, or why it is unreadable."""
    try:
        document = _toml.loads(pyproject_text)
    except (_toml.TOMLDecodeError, ValueError) as exc:
        return Failure(PyprojectUnparseable(detail=str(exc)))
    tool = document.get("tool")
    table = cast("dict[str, Any]", tool).get(_TABLE_KEY) if isinstance(tool, dict) else None
    if not isinstance(table, dict):
        return Success(DeclaredWaivers(value=[]))
    return Success(DeclaredWaivers(value=cast("dict[str, Any]", table).get(WAIVERS_KEY, [])))


def _malformed(*, subject: str, detail: str) -> WaiverProblem:
    return WaiverProblem(kind="malformed", subject=subject, detail=detail)


def _shape_defect(*, entry: dict[str, Any], canonical: Collection[str]) -> str | None:
    """Why one entry is malformed, or None when it is a well-formed table."""
    missing = sorted(_ENTRY_KEYS - entry.keys())
    extra = sorted(entry.keys() - _ENTRY_KEYS)
    if missing or extra:
        return f"expected exactly `slug` and `reason` (missing {missing}, unexpected {extra})"
    slug, reason = entry["slug"], entry["reason"]
    if not isinstance(slug, str) or not isinstance(reason, str):
        return "`slug` and `reason` must both be strings"
    if not reason.strip():
        return "`reason` is empty"
    if slug not in canonical:
        return "`slug` is not a canonical check slug"
    return None


def _judge_entry(
    *,
    position: int,
    entry: object,
    canonical: Collection[str],
    selected: Collection[str],
    seen: set[str],
) -> CanonicalWaiver | WaiverProblem:
    """One entry's verdict; records its slug in `seen` once it is well formed."""
    where = f"entry at position {position}"
    if not isinstance(entry, dict):
        return _malformed(subject=where, detail="the entry is not a table")
    table = cast("dict[str, Any]", entry)
    named = table.get("slug")
    subject = named if isinstance(named, str) else where
    defect = _shape_defect(entry=table, canonical=canonical)
    if defect is not None:
        return _malformed(subject=subject, detail=defect)
    slug, reason = cast("str", named), cast("str", table["reason"])
    if slug in seen:
        return _malformed(subject=slug, detail="the slug is waived by an earlier entry too")
    seen.add(slug)
    if slug in selected:
        return WaiverProblem(
            kind="stale",
            subject=slug,
            detail="the `just check` aggregate selects this check, so the waiver is unused",
        )
    return CanonicalWaiver(slug=slug, reason=reason)


def judge_waivers(
    *, declared: object, canonical: Collection[str], selected: Collection[str]
) -> WaiverVerdict:
    """Judge a declaration against the canonical set and the aggregate's selection."""
    if not isinstance(declared, list):
        return WaiverVerdict(
            honoured=(),
            problems=(
                _malformed(subject=WAIVERS_KEY, detail="the value is not an array of tables"),
            ),
        )
    seen: set[str] = set()
    judged = [
        _judge_entry(
            position=position, entry=entry, canonical=canonical, selected=selected, seen=seen
        )
        for position, entry in enumerate(cast("list[object]", declared))
    ]
    return WaiverVerdict(
        honoured=tuple(one for one in judged if isinstance(one, CanonicalWaiver)),
        problems=tuple(one for one in judged if isinstance(one, WaiverProblem)),
    )


@impure_safe(exceptions=(OSError,))
def _read_pyproject(*, path: Path) -> str:
    """The `pyproject.toml` text; undecodable bytes are replaced, not raised."""
    return path.read_text(encoding="utf-8", errors="replace")


def consumer_waiver_verdict(
    *, root: Path, canonical: Collection[str], selected: Collection[str]
) -> WaiverVerdict:
    """Judge the waivers `root/pyproject.toml` declares; an unreadable file applies none.

    The in-repo reading, as opposed to the fleet row's. A file that cannot be read
    or parsed collapses to an empty declaration on purpose: the spec requires that
    every omitted canonical slug is then still reported, which is exactly what an
    empty declaration yields. The fleet row cannot take that shortcut and skips.
    """
    text = unsafe_perform_io(_read_pyproject(path=root / _PYPROJECT_NAME).value_or(""))
    declared = declared_waivers(pyproject_text=text).map(lambda found: found.value).value_or([])
    return judge_waivers(declared=declared, canonical=canonical, selected=selected)
