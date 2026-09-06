"""The vocabulary the eleven plan-record conformance verdicts are stated in.

One `Finding` shape, one verdict pair, one canonicalization, and one set of
record projections, shared by the slug, anchor and timeline families so a
verdict reads identically whichever family produced it. The check ids and the
`error`/`warn` split are the ratified ones (`livespec-orchestrator-beads-fabro`
`SPECIFICATION/contracts.md` §"Plan-record conformance checks", v095) and are
NORMATIVE — an id spelled differently here is a verdict no operator can look up.

The canonicalization is stated ONCE here for the same reason it is stated once
in the orchestrator's `_plan_identity`: a second copy is how a writer and a
reader come to disagree about what "the same slug" means, and this reader grades
exactly what that writer wrote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

__all__: list[str] = [
    "CHECK_IDS",
    "CLOSED_STATUSES",
    "ERROR_VERDICT",
    "LAST_SESSION_METADATA_KEY",
    "NEXT_ACTION_METADATA_KEY",
    "PLAN_ANCHOR_FILENAME",
    "PLAN_REF_METADATA_KEY",
    "PLAN_SLUG_METADATA_KEY",
    "UNASSIGNED_ANCHOR",
    "WARN_VERDICT",
    "Finding",
    "canonical_plan_slug",
    "is_closed",
    "is_same_tenant_epic",
    "metadata_string",
    "plan_slug_of",
    "record_metadata",
]

ERROR_VERDICT = "error"
WARN_VERDICT = "warn"

# The ratified check ids, in the order the contract states them. Every armed run
# reports each of these ids — a hit as its verdict, a clean family as the
# delegation/summary line — because an id that only appears when it fires cannot
# be told apart from an id that never ran.
CHECK_IDS: tuple[str, ...] = (
    "plan_slug_present",
    "plan_slug_unique",
    "plan_slug_canonical",
    "plan_slug_on_non_epic",
    "plan_anchor_present",
    "plan_anchor_consistent",
    "plan_lifecycle_parity",
    "plan_close_evidence",
    "plan_next_action_typed",
    "plan_next_action_drift",
    "plan_comment_rate",
)

PLAN_SLUG_METADATA_KEY = "plan_slug"
PLAN_REF_METADATA_KEY = "plan_ref"
NEXT_ACTION_METADATA_KEY = "next_action"
LAST_SESSION_METADATA_KEY = "last_session"
PLAN_ANCHOR_FILENAME = "associated_work_item_id"
UNASSIGNED_ANCHOR = "unassigned"
CLOSED_STATUSES = frozenset({"closed", "done"})

_EPIC_TYPE = "epic"
_METADATA_FIELD = "metadata"
_SLUG_SEPARATOR_RUN = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LENGTH = 64


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One conformance verdict: which check, which offender, and what to do.

    `subject` is the offending epic id or the repo-relative directory path —
    the contract requires a finding to name one or the other, because a verdict
    an operator cannot locate is a verdict nobody acts on.
    """

    check_id: str
    subject: str
    verdict: str
    message: str
    remediation: str


def canonical_plan_slug(*, text: str) -> str:
    """Canonicalize a title or raw slug hint into the tenant's plan-slug form.

    Lowercase; each run of non-`[a-z0-9]` characters becomes one hyphen; leading
    and trailing hyphens are stripped; truncated to 64 characters. The trailing
    strip runs AGAIN after the truncation because the cut can land on a
    separator, and a value ending in a hyphen would not equal its own
    canonicalization — the property `plan_slug_canonical` grades.
    """
    hyphenated = _SLUG_SEPARATOR_RUN.sub("-", text.lower()).strip("-")
    return hyphenated[:_MAX_SLUG_LENGTH].strip("-")


def record_metadata(*, record: dict[str, object]) -> dict[str, object]:
    """Return a record's metadata block, tolerating the key's absence.

    Beads records are `omitempty`-sparse: a record holding no metadata omits the
    key ENTIRELY rather than carrying an empty object, so a subscript would
    raise on exactly the untagged epics `plan_slug_present` exists to report.
    """
    metadata = record.get(_METADATA_FIELD)
    if not isinstance(metadata, dict):
        return {}
    return dict(cast("dict[str, object]", metadata))


def metadata_string(*, record: dict[str, object], key: str) -> str:
    """Return one string-valued metadata key, empty when absent or ill-typed."""
    value = record_metadata(record=record).get(key)
    return value.strip() if isinstance(value, str) else ""


def plan_slug_of(*, record: dict[str, object]) -> str:
    """Return a record's `plan_slug`, empty when it carries none."""
    return metadata_string(record=record, key=PLAN_SLUG_METADATA_KEY)


def is_same_tenant_epic(*, record: dict[str, object], tenant_re: re.Pattern[str]) -> bool:
    """Return True for records that are epics of this tenant.

    An epic IS a plan under the ratified identity contract, so this predicate is
    the whole population of the slug, close-evidence and next-action verdicts.
    """
    item_id = record.get("id")
    return (
        record.get("type") == _EPIC_TYPE
        and isinstance(item_id, str)
        and tenant_re.match(item_id) is not None
    )


def is_closed(*, record: dict[str, object]) -> bool:
    """Return True when a record's ledger status is done or closed."""
    return record.get("status") in CLOSED_STATUSES
