"""The two checkout-side verdicts: the `associated_work_item_id` anchor pair.

`plan_anchor_present` grades the file's EXISTENCE and SHAPE — exactly one line
holding a same-tenant work-item id or the literal `unassigned` — and
`plan_anchor_consistent` grades what that line MEANS against the ledger, in both
directions. Both directions are graded because the identity is deliberately
carried on both sides of the seam: from the directory, the anchor's id must name
an epic whose `plan_slug` equals the directory name; from the epic, a directory
named by its slug must anchor back to it. A one-directional check passes a
tenant where every anchor is right and one epic points at a directory that
answers to somebody else.

Shape is graded before meaning, and a malformed anchor produces exactly ONE
finding: a file that is not one legible line has no meaning to disagree with,
and reporting both would tell an operator to fix a mismatch that does not exist
yet.
"""

from __future__ import annotations

from livespec_dev_tooling.checks._plan_record_dirs import PlanDirectory
from livespec_dev_tooling.checks._plan_record_model import (
    ERROR_VERDICT,
    PLAN_ANCHOR_FILENAME,
    UNASSIGNED_ANCHOR,
    Finding,
    plan_slug_of,
)

__all__: list[str] = [
    "anchor_findings",
]

_EPIC_TYPE = "epic"

_MISSING_REMEDIATION = (
    "write `plan/<slug>/associated_work_item_id` holding one line: the id of the "
    "epic whose `plan_slug` is this directory's name, or the literal "
    "`unassigned` while no epic carries it."
)
_SHAPE_REMEDIATION = (
    "hold exactly one line in the anchor: a same-tenant work-item id or the "
    "literal `unassigned`. The anchor is a re-derivable pointer, never a place "
    "to mirror children, statuses, handoffs, readiness or archive state."
)
_UNKNOWN_REMEDIATION = (
    "point the anchor at the same-tenant EPIC whose `plan_slug` equals this "
    "directory's name, or write `unassigned` while no epic carries that slug."
)
_UNASSIGNED_REMEDIATION = (
    "complete the anchor: `unassigned` is the research-before-work-items state, "
    "and once an epic carries this directory's slug the anchor names that epic."
)
_CONVERSE_REMEDIATION = (
    "make the directory anchor back to this epic, or give the epic the slug of "
    "the plan it actually anchors; the identity is carried on both sides so "
    "either side resolves the other."
)


def anchor_findings(
    *,
    directories: list[PlanDirectory],
    grouped: dict[str, list[dict[str, object]]],
    records: list[dict[str, object]],
) -> list[Finding]:
    """Return every anchor-family verdict for one repo's plan directories."""
    by_id = {
        item_id: record
        for record in records
        if isinstance(item_id := record.get("id"), str) and item_id != ""
    }
    findings: list[Finding] = []
    for directory in directories:
        if directory.anchor is None:
            findings.append(_present_finding(directory=directory))
            continue
        findings.extend(
            _consistent_findings(
                directory=directory, anchor=directory.anchor, grouped=grouped, by_id=by_id
            )
        )
    findings.extend(_converse_findings(directories=directories, grouped=grouped))
    return findings


def _present_finding(*, directory: PlanDirectory) -> Finding:
    absent = directory.raw is None
    message = (
        f"plan directory has no `{PLAN_ANCHOR_FILENAME}` file"
        if absent
        else (
            f"`{PLAN_ANCHOR_FILENAME}` does not hold exactly one same-tenant "
            f"work-item id or `{UNASSIGNED_ANCHOR}`"
        )
    )
    return Finding(
        check_id="plan_anchor_present",
        subject=directory.relative,
        verdict=ERROR_VERDICT,
        message=message,
        remediation=_MISSING_REMEDIATION if absent else _SHAPE_REMEDIATION,
    )


def _consistent_findings(
    *,
    directory: PlanDirectory,
    anchor: str,
    grouped: dict[str, list[dict[str, object]]],
    by_id: dict[str, dict[str, object]],
) -> list[Finding]:
    if anchor == UNASSIGNED_ANCHOR:
        return _unassigned_findings(directory=directory, grouped=grouped)
    record = by_id.get(anchor)
    if record is None:
        return [_inconsistent(directory=directory, message=f"anchor names no record {anchor}")]
    if record.get("type") != _EPIC_TYPE:
        return [
            _inconsistent(directory=directory, message=f"anchor names non-epic record {anchor}")
        ]
    slug = plan_slug_of(record=record)
    if slug == directory.slug:
        return []
    return [
        _inconsistent(
            directory=directory,
            message=(
                f"anchor names epic {anchor} whose plan_slug {slug!r} differs from the "
                "directory name"
            ),
        )
    ]


def _unassigned_findings(
    *, directory: PlanDirectory, grouped: dict[str, list[dict[str, object]]]
) -> list[Finding]:
    holders = grouped.get(directory.slug, [])
    if not holders:
        return []
    return [
        Finding(
            check_id="plan_anchor_consistent",
            subject=directory.relative,
            verdict=ERROR_VERDICT,
            message=(
                f"anchor is `{UNASSIGNED_ANCHOR}` while epic "
                f"{_joined_ids(records=holders)} carries this directory's slug"
            ),
            remediation=_UNASSIGNED_REMEDIATION,
        )
    ]


def _converse_findings(
    *, directories: list[PlanDirectory], grouped: dict[str, list[dict[str, object]]]
) -> list[Finding]:
    """Report an epic whose slug names a directory that anchors somebody else."""
    by_slug = {directory.slug: directory for directory in directories}
    findings: list[Finding] = []
    for slug, holders in sorted(grouped.items()):
        directory = by_slug.get(slug)
        if directory is None or directory.anchor is None or directory.anchor == UNASSIGNED_ANCHOR:
            continue
        findings.extend(
            Finding(
                check_id="plan_anchor_consistent",
                subject=holder_id,
                verdict=ERROR_VERDICT,
                message=(
                    f"epic's plan_slug names {directory.relative}, whose anchor holds "
                    f"{directory.anchor!r}"
                ),
                remediation=_CONVERSE_REMEDIATION,
            )
            for holder in holders
            if (holder_id := _joined_ids(records=[holder])) != directory.anchor
        )
    return findings


def _inconsistent(*, directory: PlanDirectory, message: str) -> Finding:
    return Finding(
        check_id="plan_anchor_consistent",
        subject=directory.relative,
        verdict=ERROR_VERDICT,
        message=message,
        remediation=_UNKNOWN_REMEDIATION,
    )


def _joined_ids(*, records: list[dict[str, object]]) -> str:
    """Return the comma-joined ids of ledger records, in ledger order."""
    return ", ".join(item_id for record in records if isinstance(item_id := record.get("id"), str))
