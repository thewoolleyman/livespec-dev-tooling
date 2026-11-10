"""Record focused incident evidence and the manual reproduction on the incident item.

The operator runs this from the expedited incident worktree, on the committed
repair head, before the expedited PR merges::

    python -m livespec_dev_tooling.incident_focused_evidence_entry \\
        --procedure TEXT --expected TEXT --observed TEXT --verdict passed|failed \\
        [--related-test PATH ...] [--related-reason TEXT] [--defer-test PATH=REASON ...]

It resolves the trusted incident context exactly as the hook entrance does: the
flags select incident handling, and only the registered canonical authority's
`read-current` answer supplies the identity. It then runs the changed and
related tests and touched-file coverage through `collect_focused_evidence`,
keeps the manual reproduction verbatim beside that measurement, and publishes
the record to the incident item through the authority's `record-local-gates`
evidence channel, the only canonical evidence write the authority exposes. Its
receipt id is the first free slot derived from the exact identity, head and tree
(`incident_focused_admission`), so the observer's `/arm` reads every record of
the head tree without the operator naming one. The receipt is
`expedited-local-partial` evidence for the pushed tree, never a normal green
token, coverage reuse marker or factory proof.

Every refusal exits 78 with a named reason. A refusal raised before the
publish step publishes nothing.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, NoReturn, cast

from livespec_dev_tooling.config import derive_source_prefixes, load_config
from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    parse_incident_truth_value,
)
from livespec_dev_tooling.incident_focused_admission import EvidenceSubject, first_free_slot
from livespec_dev_tooling.incident_focused_evidence import (
    FocusedScope,
    ManualReproduction,
    collect_focused_evidence,
)
from livespec_dev_tooling.incident_hook_entry import QUERY_ENV
from livespec_dev_tooling.incident_hook_process import (
    HookRefusalError,
    canonical,
    exact_tree,
    invoke_authority,
    mapping,
    parse_query,
    resolve_current,
)

if TYPE_CHECKING:
    from livespec_dev_tooling._incident_focused_types import ResolvedContext
    from livespec_dev_tooling.incident_execution import OperationIdentity

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import impure_safe  # noqa: E402 — vendor-path-aware import.
from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402 — vendor-path-aware import.

__all__: list[str] = ["main"]

_REFUSED = 78
# The authority refuses a receipt larger than this; refuse first, unpublished.
_MAX_RECEIPT_BYTES = 1048576
# The authority admits a `passed` row only under the sixty-second gate budget.
_MAX_PASSED_SECONDS = 60
_ROW = "incident-focused-evidence"
_CHECKSUM = re.compile(r"sha256:[0-9a-f]{64}")


def _refuse(*, reason: str) -> int:
    _ = sys.stderr.write("incident-evidence-refused: " + reason + "\n")
    return _REFUSED


def _fail(*, reason: str) -> NoReturn:
    raise HookRefusalError(reason)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m livespec_dev_tooling.incident_focused_evidence_entry",
        description="Record focused incident evidence on the incident item before merge.",
    )
    for name, text in (
        ("--procedure", "the manual reproduction's procedure, kept verbatim"),
        ("--expected", "the outcome the procedure should show, kept verbatim"),
        ("--observed", "the outcome the operator observed, kept verbatim"),
    ):
        _ = parser.add_argument(name, required=True, help=text)
    _ = parser.add_argument("--verdict", required=True, choices=("passed", "failed"))
    _ = parser.add_argument("--related-test", action="append", default=[], dest="related")
    _ = parser.add_argument("--related-reason", default="")
    _ = parser.add_argument(
        "--defer-test", action="append", default=[], dest="deferred", metavar="PATH=REASON"
    )
    return parser


def _requested() -> bool:
    values = [
        parse_incident_truth_value(name=name, value=os.environ.get(name))
        for name in (EXPEDITED_INCIDENT_RESPONSE, EXPEDITED_INCIDENT_RESPONSE_REVERT)
    ]
    if any(not is_successful(value) for value in values):
        _fail(reason="malformed incident flag")
    return any(value.unwrap() for value in values)


def _deferred(*, values: list[str]) -> tuple[tuple[str, str], ...]:
    parts = [value.partition("=") for value in values]
    if any(not separator for _, separator, _ in parts):
        _fail(reason="--defer-test takes PATH=REASON")
    return tuple((name, reason) for name, _, reason in parts)


def _receipt(
    *, record: dict[str, Any], duration: float, tree: str, receipt_id: str
) -> dict[str, Any]:
    """Shape the record as one canonical expedited-local-partial evidence row."""
    outcome = record["outcome"]
    status = (
        ("passed" if duration < _MAX_PASSED_SECONDS else "deferred-timeout")
        if outcome == "passed"
        else "failed"
    )
    returncode = {"passed": 0, "failed": 1}.get(status)
    row = dict(
        name=_ROW,
        status=status,
        reason="focused evidence " + outcome + "".join("; " + risk for risk in record["risks"]),
        returncode=returncode,
        duration_seconds=duration,
        output=canonical(value=record),
    )
    return dict(
        receipt_id=receipt_id,
        hook="pre-push",
        tree=tree,
        mode=record["mode"],
        evidence_kind="expedited-local-partial",
        exit_status=returncode or 0,
        results=[row],
    )


def _recorded(*, repo: Path, query: dict[str, Any], receipt_id: str) -> bool:
    lookup = invoke_authority(
        repo=repo, query=query, action="read-local-gates", receipt_id=receipt_id
    )
    status = lookup.get("status")
    if lookup.get("receipt_id") != receipt_id or status not in {"recorded", "absent"}:
        _fail(reason="focused-evidence slot lookup does not bind this tree")
    return status == "recorded"


def _slot(*, repo: Path, query: dict[str, Any], subject: EvidenceSubject) -> str:
    """The first free evidence slot for this exact identity, head and tree.

    The observer's `/arm` reads every slot of the head tree, so a record is only
    ever appended, never chosen by the operator at arm time.
    """
    receipt_id = first_free_slot(
        subject=subject,
        recorded=lambda slot_id: _recorded(repo=repo, query=query, receipt_id=slot_id),
    )
    if receipt_id is None:
        _fail(reason="every focused-evidence slot of this head tree is recorded; commit a new head")
    return receipt_id


def _publish(
    *,
    repo: Path,
    query: dict[str, Any],
    reading: dict[str, Any],
    identity: OperationIdentity,
    receipt: dict[str, Any],
) -> dict[str, str]:
    """Append, read back and bind the record to the attempt and head it measured."""
    saved = invoke_authority(
        repo=repo, query=query, action="record-local-gates", receipt=canonical(value=receipt)
    )
    checksum = saved.get("checksum")
    expected = dict(
        receipt_id=receipt["receipt_id"],
        committed_token_id=reading["committed_token_id"],
        current_token_id=reading["current_token_id"],
    )
    if (
        any(saved.get(key) != value for key, value in expected.items())
        or not isinstance(checksum, str)
        or _CHECKSUM.fullmatch(checksum) is None
    ):
        _fail(reason="published receipt does not bind this record")
    lookup = invoke_authority(
        repo=repo, query=query, action="read-local-gates", receipt_id=receipt["receipt_id"]
    )
    if (lookup.get("status"), lookup.get("checksum"), lookup.get("receipt")) != (
        "recorded",
        checksum,
        receipt,
    ):
        _fail(reason="recorded focused evidence does not read back exactly")
    history = mapping(
        value=invoke_authority(repo=repo, query=query, action="read-history").get("attempt")
    )
    if (history.get("attempt_id"), history.get("head")) != (identity.attempt_id, identity.head_sha):
        _fail(reason="incident history does not show the attempt and head this record measured")
    return dict(
        receipt_id=receipt["receipt_id"],
        checksum=checksum,
        item=identity.incident_item_id,
        attempt=identity.attempt_id,
        head=identity.head_sha,
        tree=receipt["tree"],
    )


@impure_safe
def _run(*, args: argparse.Namespace) -> int:
    if not _requested():
        _fail(reason="resolved expedited incident context required: no incident flag is set")
    query = parse_query(text=os.environ.get(QUERY_ENV, "{}"))
    if query is None:
        _fail(reason="exact canonical incident authority query required in " + QUERY_ENV)
    deferred = _deferred(values=args.deferred)
    repo = Path.cwd()
    reading = invoke_authority(repo=repo, query=query, action="read-current")
    context = resolve_current(reading=reading, query=query)
    tree = exact_tree(repo=repo, context=context, hook="pre-push")
    config = load_config(repo_root=repo)
    started = monotonic()
    record = collect_focused_evidence(
        repo_root=repo,
        # The frozen resolver context satisfies the collector's read-only use.
        context=cast("ResolvedContext", context),
        scope=FocusedScope(
            tree_hash=tree,
            source_prefixes=derive_source_prefixes(config=config),
            test_prefixes=(config.tests_tree_prefix,),
            related_tests=tuple(args.related),
            prior_paths=tuple(mapping(value=reading["attempt"]).get("original_paths", ())),
            related_test_reason=args.related_reason,
            deferred_tests=deferred,
        ),
        manual=ManualReproduction(
            procedure=args.procedure,
            expected=args.expected,
            observed=args.observed,
            outcome=args.verdict,
        ),
    )
    duration = monotonic() - started
    if record["outcome"] == "refused":
        _fail(reason="focused evidence refused: " + str(record["reason"]))
    identity = cast("OperationIdentity", context.identity)
    subject = EvidenceSubject(
        repository=identity.repository,
        item=identity.incident_item_id,
        attempt=identity.attempt_id,
        operation=identity.operation_id,
        generation=query["generation"],
        head=identity.head_sha,
        tree=tree,
    )
    # Every slot id is 64 hex characters, so the bound holds for whichever slot is free.
    receipt = _receipt(record=record, duration=duration, tree=tree, receipt_id="0" * 64)
    if len(canonical(value=receipt).encode()) > _MAX_RECEIPT_BYTES:
        _fail(reason="focused record exceeds the authority's receipt size bound")
    receipt["receipt_id"] = _slot(repo=repo, query=query, subject=subject)
    publication = _publish(
        repo=repo,
        query=query,
        reading=reading,
        identity=identity,
        receipt=receipt,
    )
    _ = sys.stdout.write(
        canonical(
            value=dict(schema=1, record=record, publication=publication, normal_factory_proof=False)
        )
        + "\n"
    )
    return 0 if record["outcome"] == "passed" else 1


def main(*, argv: list[str] | None = None) -> int:
    """Exit 0 for passed evidence, 1 for recorded failed or incomplete evidence, 78 refused."""
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
