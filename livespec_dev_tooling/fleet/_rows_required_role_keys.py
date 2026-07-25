"""Fleet row enforcing declared role keys for layout-dependent check consumers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.checks.required_role_keys_declared import (
    MISSING_KEYS_EVENT,
    classify_role_key_declarations,
)
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

__all__: list[str] = ["assert_required_role_keys_declared"]


def _declared_role_keys_from_pyproject(*, pyproject_text: str) -> frozenset[str] | None:
    """Declared `[tool.livespec_dev_tooling]` keys, or None when TOML is malformed."""
    try:
        data: dict[str, object] = tomli.loads(pyproject_text)
    except tomli.TOMLDecodeError:
        return None
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return frozenset()
    table = cast("dict[str, object]", tool).get("livespec_dev_tooling")
    if not isinstance(table, dict):
        return frozenset()
    return frozenset(cast("dict[str, object]", table))


def _required_role_justfile_text(
    *, ctx: FleetContext, member: FleetMember, tree: TreeState
) -> tuple[str | None, RowOutcome | None]:
    """Read the member justfile or return the conclusive row outcome."""
    if "justfile" not in tree.paths:
        if tree.truncated:
            return None, RowSkip(
                reason=f"{member.repo}: tree truncated; justfile absence not definitive"
            )
        return None, RowPass(
            note="excluded-with-reason: justfile not found; no check aggregate wired"
        )
    justfile_text = ctx.file_text(repo=member.repo, path="justfile")
    if justfile_text is None:
        return None, RowSkip(reason=f"{member.repo}: justfile unreadable")
    return justfile_text, None


def _required_role_declared_keys(
    *, ctx: FleetContext, member: FleetMember, tree: TreeState
) -> tuple[frozenset[str], RowOutcome | None]:
    """Read declared role keys, or return the conclusive row outcome."""
    if "pyproject.toml" not in tree.paths:
        if tree.truncated:
            return frozenset(), RowSkip(
                reason=f"{member.repo}: tree truncated; pyproject.toml absence not definitive"
            )
        return frozenset(), None
    pyproject_text = ctx.file_text(repo=member.repo, path="pyproject.toml")
    if pyproject_text is None:
        return frozenset(), RowSkip(reason=f"{member.repo}: pyproject.toml unreadable")
    parsed_keys = _declared_role_keys_from_pyproject(pyproject_text=pyproject_text)
    if parsed_keys is None:
        return frozenset(), RowFinding(message=f"{member.repo}: malformed pyproject.toml")
    return parsed_keys, None


def _required_role_status_outcome(
    *, justfile_text: str, declared_keys: frozenset[str], member: FleetMember
) -> RowOutcome:
    """Map the reusable declaration classifier onto a fleet row outcome."""
    status = classify_role_key_declarations(
        justfile_text=justfile_text, declared_keys=declared_keys
    )
    if status.is_excluded():
        return RowPass(note=f"excluded-with-reason: {status.excluded_reason}")
    if not status.missing_keys:
        return RowPass()
    return RowFinding(
        message=(
            f"{member.repo}: required role key(s) missing from "
            f"[tool.livespec_dev_tooling]: {', '.join(status.missing_keys)} -- "
            f"{MISSING_KEYS_EVENT}"
        )
    )


def assert_required_role_keys_declared(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Layout-dependent check consumers declare every required role key."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    justfile_text, justfile_outcome = _required_role_justfile_text(
        ctx=ctx, member=member, tree=tree
    )
    if justfile_outcome is not None:
        return justfile_outcome
    declared_keys, declared_keys_outcome = _required_role_declared_keys(
        ctx=ctx, member=member, tree=tree
    )
    if declared_keys_outcome is not None:
        return declared_keys_outcome
    if justfile_text is None:
        return RowSkip(reason=f"{member.repo}: justfile unreadable")
    return _required_role_status_outcome(
        justfile_text=justfile_text, declared_keys=declared_keys, member=member
    )
