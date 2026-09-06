"""The four ledger-side plan-identity verdicts, graded off epic metadata alone.

`plan_slug_present`, `plan_slug_unique`, `plan_slug_canonical` and
`plan_slug_on_non_epic` all read the same population — this tenant's records —
and none of them touches the checkout, which is what separates this family from
the anchor family next door.

The `plan_ref` half of `plan_slug_on_non_epic` is here rather than with the
anchors because it grades the SAME rule from the other side: a non-epic's plan
is its parent chain, so the only sanctioned reference it may carry is a
tenant-qualified pointer at a plan it is NOT already a child of. A pointer at
its own parent restates the edge the ledger already holds, which is the shadow
this verdict exists to catch.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.checks._plan_ledger import depends_on, record_id
from livespec_dev_tooling.checks._plan_record_model import (
    ERROR_VERDICT,
    PLAN_REF_METADATA_KEY,
    Finding,
    canonical_plan_slug,
    is_same_tenant_epic,
    metadata_string,
    plan_slug_of,
)

__all__: list[str] = [
    "plan_epics_by_slug",
    "same_tenant_epics",
    "slug_findings",
]

_PRESENT_REMEDIATION = (
    "write the epic's canonical `plan_slug` metadata through the plan primitive "
    "that anchors it; every epic IS a plan and carries the handle its listings "
    "and its `plan/<slug>/` directory are keyed on."
)
_UNIQUE_REMEDIATION = (
    "give one of the colliding epics a different canonical slug; `plan_slug` is "
    "unique across a tenant's epics, closed ones included, so a retired slug is "
    "not reused while its epic remains."
)
_CANONICAL_REMEDIATION = (
    "rewrite the value as its own canonicalization (lowercase, one hyphen per "
    "run of non-[a-z0-9], stripped, truncated to 64); a slug that does not equal "
    "its canonicalization resolves differently for a writer and a reader."
)
_NON_EPIC_SLUG_REMEDIATION = (
    "remove `plan_slug` from the non-epic item; its plan is its parent chain, "
    "and the one sanctioned reference is a tenant-qualified `plan_ref`."
)
_PLAN_REF_SHAPE_REMEDIATION = (
    "spell the reference `<tenant>/<slug>`; an unqualified `plan_ref` names a "
    "slug the reader cannot resolve to a tenant."
)
_PLAN_REF_PARENT_REMEDIATION = (
    "drop the `plan_ref`; the item is already a child of that plan's epic, so "
    "the reference shadows an edge the ledger holds."
)


def same_tenant_epics(
    *, records: list[dict[str, object]], tenant_re: re.Pattern[str]
) -> list[dict[str, object]]:
    """Return this tenant's epic records — the population every slug verdict grades."""
    return [record for record in records if is_same_tenant_epic(record=record, tenant_re=tenant_re)]


def plan_epics_by_slug(*, epics: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Group epics carrying a slug by that slug, collisions included.

    Collisions are KEPT rather than resolved: `plan_slug_unique` reports them,
    and a mapping that silently picked a winner would hide the very state the
    anchor family then grades against.
    """
    grouped: dict[str, list[dict[str, object]]] = {}
    for epic in epics:
        slug = plan_slug_of(record=epic)
        if slug != "":
            grouped.setdefault(slug, []).append(epic)
    return grouped


def slug_findings(*, records: list[dict[str, object]], tenant_re: re.Pattern[str]) -> list[Finding]:
    """Return every slug-family verdict for one tenant's records."""
    epics = same_tenant_epics(records=records, tenant_re=tenant_re)
    findings = [
        *_present_findings(epics=epics),
        *_unique_findings(epics=epics),
        *_canonical_findings(epics=epics),
        *_non_epic_findings(records=records, epics=epics, tenant_re=tenant_re),
    ]
    return findings


def _present_findings(*, epics: list[dict[str, object]]) -> list[Finding]:
    return [
        Finding(
            check_id="plan_slug_present",
            subject=_id_of(record=epic),
            verdict=ERROR_VERDICT,
            message="epic carries no `plan_slug` metadata",
            remediation=_PRESENT_REMEDIATION,
        )
        for epic in epics
        if plan_slug_of(record=epic) == ""
    ]


def _unique_findings(*, epics: list[dict[str, object]]) -> list[Finding]:
    findings: list[Finding] = []
    for slug, holders in sorted(plan_epics_by_slug(epics=epics).items()):
        if len(holders) < 2:  # noqa: PLR2004  — two holders is what a collision IS
            continue
        holder_ids = sorted(_id_of(record=holder) for holder in holders)
        findings.extend(
            Finding(
                check_id="plan_slug_unique",
                subject=holder_id,
                verdict=ERROR_VERDICT,
                message=f"plan_slug {slug!r} is carried by epics {', '.join(holder_ids)}",
                remediation=_UNIQUE_REMEDIATION,
            )
            for holder_id in holder_ids
        )
    return findings


def _canonical_findings(*, epics: list[dict[str, object]]) -> list[Finding]:
    findings: list[Finding] = []
    for epic in epics:
        slug = plan_slug_of(record=epic)
        canonical = canonical_plan_slug(text=slug)
        if slug not in ("", canonical):
            findings.append(
                Finding(
                    check_id="plan_slug_canonical",
                    subject=_id_of(record=epic),
                    verdict=ERROR_VERDICT,
                    message=f"plan_slug {slug!r} is not its own canonicalization {canonical!r}",
                    remediation=_CANONICAL_REMEDIATION,
                )
            )
    return findings


def _non_epic_findings(
    *,
    records: list[dict[str, object]],
    epics: list[dict[str, object]],
    tenant_re: re.Pattern[str],
) -> list[Finding]:
    findings: list[Finding] = []
    grouped = plan_epics_by_slug(epics=epics)
    for record in records:
        item_id = record_id(record=record)
        if item_id is None or tenant_re.match(item_id) is None:
            continue
        if is_same_tenant_epic(record=record, tenant_re=tenant_re):
            continue
        findings.extend(_non_epic_slug_finding(record=record, item_id=item_id))
        findings.extend(_plan_ref_findings(record=record, item_id=item_id, grouped=grouped))
    return findings


def _non_epic_slug_finding(*, record: dict[str, object], item_id: str) -> list[Finding]:
    if plan_slug_of(record=record) == "":
        return []
    return [
        Finding(
            check_id="plan_slug_on_non_epic",
            subject=item_id,
            verdict=ERROR_VERDICT,
            message="work item that is not an epic carries `plan_slug`",
            remediation=_NON_EPIC_SLUG_REMEDIATION,
        )
    ]


def _plan_ref_findings(
    *,
    record: dict[str, object],
    item_id: str,
    grouped: dict[str, list[dict[str, object]]],
) -> list[Finding]:
    plan_ref = metadata_string(record=record, key=PLAN_REF_METADATA_KEY)
    if plan_ref == "":
        return []
    tenant, separator, slug = plan_ref.partition("/")
    if separator == "" or tenant == "" or slug == "" or "/" in slug:
        return [
            Finding(
                check_id="plan_slug_on_non_epic",
                subject=item_id,
                verdict=ERROR_VERDICT,
                message=f"plan_ref {plan_ref!r} is not tenant-qualified as `<tenant>/<slug>`",
                remediation=_PLAN_REF_SHAPE_REMEDIATION,
            )
        ]
    return [
        Finding(
            check_id="plan_slug_on_non_epic",
            subject=item_id,
            verdict=ERROR_VERDICT,
            message=f"plan_ref {plan_ref!r} names the epic this item is already a child of",
            remediation=_PLAN_REF_PARENT_REMEDIATION,
        )
        for epic in grouped.get(slug, [])
        if depends_on(record=record, epic_id=_id_of(record=epic))
    ]


def _id_of(*, record: dict[str, object]) -> str:
    """Return a record's id, empty when it carries none.

    Every caller here has already established the id through the tenant matcher
    or through `is_same_tenant_epic`, so the empty string is unreachable rather
    than a sentinel a reader has to handle.
    """
    item_id = record_id(record=record)
    return "" if item_id is None else item_id
