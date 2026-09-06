"""The `worktree-pack-wired` obligation row over a member's committed master.

The central-vantage HALF of the worktree-pack wiring obligation: it reads the
four committed files from the member's `master` tree and hands their texts to
the pure predicate in `worktree_pack_wiring.py`, which decides what is
missing. The split is the concern boundary — READING a member (a vantage,
a credential, a tree that may be truncated or unreadable) is a different job
from DECIDING whether four texts carry the wiring, and only the second half is
what a sibling repo's lockstep test wants to import.

Every read distinguishes definitive absence (finding) from can't-read (skip),
so a permission-limited token never produces a false red — the same discipline
the sibling committed-file rows in `_rows_files.py` hold to. The obligation
itself, the five facts, and the severity split are documented at the predicate
module; this module is the row's plumbing.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet.worktree_pack_wiring import (
    GITIGNORE_PATH,
    JUSTFILE_PATH,
    LEFTHOOK_PATH,
    LIVESPEC_JSONC_PATH,
    WIRING_FILES,
    WiringGap,
    worktree_pack_wiring_gaps,
)

__all__: list[str] = [
    "assert_worktree_pack_wired",
]


def _wiring_file(*, ctx: FleetContext, member: FleetMember, path: str) -> str | RowOutcome:
    """The member's committed file text, or the outcome that ends the row.

    Can't-read is never absence: an unreadable tree, a truncated tree that
    cannot prove absence, and an unreadable file are all skips, so a
    permission-limited token produces no false red. Only a readable,
    non-truncated tree that does not list the file is a finding.
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if path not in tree.paths:
        if tree.truncated:
            return RowSkip(
                reason=f"{member.repo}: tree truncated; absence of {path} not definitive"
            )
        return RowFinding(
            message=f"{member.repo}: required file {path} missing from master — pack unwired"
        )
    text = ctx.file_text(repo=member.repo, path=path)
    if text is None:
        return RowSkip(reason=f"{member.repo}: {path} unreadable")
    return text


def _wiring_finding(*, member: FleetMember, gaps: tuple[WiringGap, ...]) -> RowFinding:
    """The finding for a member with gaps, naming every missing line.

    Severity is the MAXIMUM over the gaps: one error-severity gap makes the
    row an error even when warning-severity ignore gaps ride along, so a
    broken mechanism is never demoted by the company it keeps.
    """
    detail = "; ".join(f"{gap.path} is missing {gap.missing}" for gap in gaps)
    severity = "error" if any(gap.severity == "error" for gap in gaps) else "warning"
    return RowFinding(
        message=f"{member.repo}: worktree-pack wiring incomplete — {detail}",
        severity=severity,
    )


def assert_worktree_pack_wired(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member's committed master carries the whole worktree-pack wiring."""
    texts: dict[str, str] = {}
    for path in WIRING_FILES:
        found = _wiring_file(ctx=ctx, member=member, path=path)
        if not isinstance(found, str):
            return found
        texts[path] = found
    gaps = worktree_pack_wiring_gaps(
        justfile_text=texts[JUSTFILE_PATH],
        gitignore_text=texts[GITIGNORE_PATH],
        lefthook_text=texts[LEFTHOOK_PATH],
        livespec_jsonc_text=texts[LIVESPEC_JSONC_PATH],
    )
    if not gaps:
        return RowPass()
    return _wiring_finding(member=member, gaps=gaps)
