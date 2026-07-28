"""Fleet row asserting every union role key carries a blessed declared-absent spelling.

Phase 3 of `livespec-dev-tooling-8o8e.1`. The five keys in `UNION_ROLE_KEYS`
are the ones whose declared value IS a consuming check's scan universe, so an
empty declaration made that check scan NOTHING and exit 0. This row reads each
member's committed `pyproject.toml` from the central fleet vantage and fails
when any of those keys still carries the retired ambiguous empty spelling.

It exists because the fleet's migrated state is otherwise only a hand-gathered
measurement — true at the moment someone ran it. This row is what makes it keep
being true, and it is the mechanical form of the maintainer's stated closure
evidence: PER-REPO proof that each consumer declares a correct variant. The
finding names the member, never an aggregate — "the fleet is clean" is exactly
the shape of summary that hid the original defect for nine repos.

## What this row does NOT verify — stated so it is not over-read

It checks the SPELLING of a declared-absent value, not the TRUTH of its
payload. In particular an `unarmed_until` payload is verified to be a non-empty
string and NOTHING MORE: this row does not resolve the identifier, so it cannot
tell a live work item from a nonexistent or already-closed one. That liveness
property is real and wanted — a closed id asserts pending work that is finished,
which is the emptiness-means-consent shape wearing a blessed name — but it needs
a ledger the central vantage cannot reach, and every declared id may live in a
DIFFERENT tenant from the repo declaring it. Resolving it is therefore a
separate, differently-vantaged obligation, not something to bolt on here and
have silently skip.

A check that overclaims its coverage is the defect this epic is about, so the
boundary is documented rather than implied.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.config import BLESSED_ROLE_SPELLINGS, UNION_ROLE_KEYS
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
    TreeState,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import tomli  # noqa: E402  -- vendor-path-aware import after sys.path insert.

__all__: list[str] = ["assert_role_key_spellings_conformant"]

_PYPROJECT = "pyproject.toml"
_TOOL_TABLE = "livespec_dev_tooling"

# The remediation every finding ends with. It names all four spellings inline
# rather than referring to them, for the same reason the loader's own hint does:
# a rejection that does not say what IS legal only relocates the confusion.
_REMEDIATION = (
    "declare a populated value, or exactly one of the four declared-absent "
    f"spellings ({', '.join(BLESSED_ROLE_SPELLINGS)}), each carrying a non-empty "
    "payload so the reason lives in the parsed value rather than in a comment no "
    "checker can read"
)


def _tool_table(*, pyproject_text: str) -> dict[str, object] | None:
    """The member's `[tool.livespec_dev_tooling]` table, or None when TOML is malformed."""
    try:
        data: dict[str, object] = tomli.loads(pyproject_text)
    except tomli.TOMLDecodeError:
        return None
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}
    table = cast("dict[str, object]", tool).get(_TOOL_TABLE)
    if not isinstance(table, dict):
        return {}
    return cast("dict[str, object]", table)


def _is_blessed_declaration(*, value: dict[str, object]) -> bool:
    """True when the inline table is exactly one blessed spelling with a non-empty payload."""
    names = [name for name in value if name in BLESSED_ROLE_SPELLINGS]
    if len(names) != 1 or len(value) != 1:
        return False
    payload = value[names[0]]
    return isinstance(payload, str) and bool(payload.strip())


def _is_conformant(*, value: object) -> bool:
    """True when a union role key's declared value is NOT the ambiguous empty spelling."""
    if isinstance(value, dict):
        return _is_blessed_declaration(value=cast("dict[str, object]", value))
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, list):
        return bool(cast("list[object]", value))
    # Any other TOML type is not a spelling this schema recognizes.
    return False


def _offending_keys(*, table: dict[str, object]) -> tuple[str, ...]:
    """The union role keys this member declares with a non-conformant spelling."""
    return tuple(
        sorted(
            key for key in UNION_ROLE_KEYS if key in table and not _is_conformant(value=table[key])
        )
    )


def _pyproject_text(*, ctx: FleetContext, member: FleetMember, tree: TreeState) -> str | RowOutcome:
    """The member's pyproject.toml text, or the conclusive row outcome when it is unreadable."""
    if _PYPROJECT not in tree.paths:
        if tree.truncated:
            return RowSkip(
                reason=f"{member.repo}: tree truncated; {_PYPROJECT} absence not definitive"
            )
        return RowPass(note=f"excluded-with-reason: {_PYPROJECT} not found; not a config consumer")
    text = ctx.file_text(repo=member.repo, path=_PYPROJECT)
    if text is None:
        return RowSkip(reason=f"{member.repo}: {_PYPROJECT} unreadable")
    return text


def _spelling_outcome(*, pyproject_text: str, member: FleetMember) -> RowOutcome:
    """Classify one member's declared union role keys into a row outcome."""
    table = _tool_table(pyproject_text=pyproject_text)
    if table is None:
        return RowFinding(message=f"{member.repo}: malformed {_PYPROJECT}")
    if not table:
        return RowPass(
            note=(
                f"excluded-with-reason: no [tool.{_TOOL_TABLE}] block; not a layout-config consumer"
            )
        )
    offenders = _offending_keys(table=table)
    if not offenders:
        return RowPass()
    return RowFinding(
        message=(
            f"{member.repo}: role key(s) still carrying the retired ambiguous empty "
            f"spelling: {', '.join(offenders)} -- {_REMEDIATION}"
        )
    )


def assert_role_key_spellings_conformant(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Every declared union role key uses a blessed spelling, never the ambiguous empty one."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    text = _pyproject_text(ctx=ctx, member=member, tree=tree)
    if isinstance(text, str):
        return _spelling_outcome(pyproject_text=text, member=member)
    return text
