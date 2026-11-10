"""Record an operator risk disposition for an incomplete member of focused incident evidence.

The operator runs this after `incident_focused_evidence_entry` published a
record that reads `incomplete`, and before arming the expedited merge::

    python -m livespec_dev_tooling.incident_focused_disposition_entry \\
        --evidence-receipt RECEIPT_ID --member MEMBER [--member MEMBER ...] \\
        --disposition TEXT

`RECEIPT_ID` is the `publication.receipt_id` the evidence entrance printed, and
each `MEMBER` is one deferred or incomplete member of that record exactly as
the observer's `/arm` refusal (`incident-focused-evidence-undisposed`) names
it. The disposition is published through the canonical authority's
`record-local-gates` channel under an id derived from the record and the
member, bound to the record's exact checksum, and read back before success.

A failed member is never disposable: a failing focused test or manual
reproduction requires repair (SPECIFICATION `contracts.md`, the expedited
incident execution contract). Every refusal exits 78 with a named reason; a refusal raised before
publication publishes nothing.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, cast

from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    parse_incident_truth_value,
)
from livespec_dev_tooling.incident_focused_admission import (
    MAX_EVIDENCE_SLOTS,
    EvidenceSubject,
    disposition_matches,
    disposition_receipt,
    evidence_receipt_id,
    review_record,
)
from livespec_dev_tooling.incident_hook_entry import QUERY_ENV
from livespec_dev_tooling.incident_hook_process import (
    HookRefusalError,
    canonical,
    invoke_authority,
    mapping,
    parse_query,
    resolve_current,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.incident_execution import OperationIdentity

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import impure_safe  # noqa: E402 — vendor-path-aware import.
from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402 — vendor-path-aware import.

__all__: list[str] = ["main"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
_REFUSED = 78


def _refuse(*, reason: str) -> int:
    _ = sys.stderr.write("incident-disposition-refused: " + reason + "\n")
    return _REFUSED


def _fail(*, reason: str) -> NoReturn:
    raise HookRefusalError(reason)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m livespec_dev_tooling.incident_focused_disposition_entry",
        description="Record an operator risk disposition for incomplete focused evidence.",
    )
    _ = parser.add_argument("--evidence-receipt", required=True, dest="evidence")
    _ = parser.add_argument("--member", action="append", required=True, dest="members")
    _ = parser.add_argument("--disposition", required=True)
    return parser


def _requested() -> bool:
    values = [
        parse_incident_truth_value(name=name, value=os.environ.get(name))
        for name in (EXPEDITED_INCIDENT_RESPONSE, EXPEDITED_INCIDENT_RESPONSE_REVERT)
    ]
    if any(not is_successful(value) for value in values):
        _fail(reason="malformed incident flag")
    return any(value.unwrap() for value in values)


def _lookup(*, repo: Path, query: dict[str, Any], receipt_id: str) -> tuple[dict[str, Any], str]:
    found = invoke_authority(
        repo=repo, query=query, action="read-local-gates", receipt_id=receipt_id
    )
    receipt, checksum = mapping(value=found.get("receipt")), found.get("checksum")
    if (found.get("status"), found.get("receipt_id"), receipt.get("receipt_id")) != (
        "recorded",
        receipt_id,
        receipt_id,
    ) or not isinstance(checksum, str):
        _fail(reason="no recorded receipt " + receipt_id + " reads back for this incident")
    return receipt, checksum


def _subject(
    *, query: dict[str, Any], identity: OperationIdentity, evidence: str, tree: str
) -> EvidenceSubject:
    subject = EvidenceSubject(
        repository=identity.repository,
        item=identity.incident_item_id,
        attempt=identity.attempt_id,
        operation=identity.operation_id,
        generation=query["generation"],
        head=identity.head_sha,
        tree=tree,
    )
    if evidence not in {
        evidence_receipt_id(subject=subject, slot=slot) for slot in range(MAX_EVIDENCE_SLOTS)
    }:
        _fail(reason="receipt " + evidence + " is not focused evidence of the current head")
    return subject


@impure_safe
def _run(*, args: argparse.Namespace) -> int:
    if not _requested():
        _fail(reason="resolved expedited incident context required: no incident flag is set")
    query = parse_query(text=os.environ.get(QUERY_ENV, "{}"))
    if query is None:
        _fail(reason="exact canonical incident authority query required in " + QUERY_ENV)
    if not args.disposition.strip():
        _fail(reason="the disposition text is empty")
    repo = Path.cwd()
    context = resolve_current(
        reading=invoke_authority(repo=repo, query=query, action="read-current"), query=query
    )
    evidence, checksum = _lookup(repo=repo, query=query, receipt_id=args.evidence)
    tree = str(evidence.get("tree"))
    subject = _subject(
        query=query,
        identity=cast("OperationIdentity", context.identity),
        evidence=args.evidence,
        tree=tree,
    )
    review = review_record(receipt=evidence, subject=subject)
    if review is None:
        _fail(reason="receipt " + args.evidence + " is not a focused-evidence record")
    for member in args.members:
        if member in review.failed:
            _fail(reason=member + " failed; a failing assertion requires repair, not disposition")
        if member not in review.members:
            _fail(
                reason=member
                + " is not a deferred or incomplete member of this record; its members are: "
                + "; ".join(review.members)
            )
    published: list[dict[str, str]] = []
    for member in dict.fromkeys(args.members):
        receipt = disposition_receipt(
            evidence_receipt_id=args.evidence,
            evidence_checksum=checksum,
            member=member,
            disposition=args.disposition,
            tree=tree,
        )
        _ = invoke_authority(
            repo=repo, query=query, action="record-local-gates", receipt=canonical(value=receipt)
        )
        saved, saved_checksum = _lookup(repo=repo, query=query, receipt_id=receipt["receipt_id"])
        if saved != receipt or not disposition_matches(
            receipt=saved,
            evidence_receipt_id=args.evidence,
            evidence_checksum=checksum,
            member=member,
            tree=tree,
        ):
            _fail(reason="the recorded disposition of " + member + " does not read back exactly")
        published.append(
            dict(member=member, receipt_id=receipt["receipt_id"], checksum=saved_checksum)
        )
    _ = sys.stdout.write(
        canonical(
            value=dict(
                schema=1,
                evidence_receipt_id=args.evidence,
                tree=tree,
                dispositions=published,
                normal_factory_proof=False,
            )
        )
        + "\n"
    )
    return 0


def main(*, argv: list[str] | None = None) -> int:
    """Exit 0 once every disposition reads back, 78 on any refusal."""
    try:
        args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as stop:
        return 0 if stop.code == 0 else _refuse(reason="invalid invocation (see usage above)")
    result = _run(args=args)
    if not is_successful(result):
        return _refuse(reason=str(unsafe_perform_io(result.failure())))
    return unsafe_perform_io(result.unwrap())


if __name__ == "__main__":
    raise SystemExit(main())
