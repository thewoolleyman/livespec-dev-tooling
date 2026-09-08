"""The four verdicts that need an epic's TIMELINE, not just its metadata.

`plan_close_evidence`, `plan_next_action_typed`, `plan_next_action_drift` and
`plan_comment_rate` are grouped because they share one expensive input — the
epic's append-only comment timeline, one ledger read per epic — and because
three of them ask the same question from different angles: what does this plan
say happens next, and does the record agree with itself.

Two of the four never fail a run. `plan_next_action_drift` and
`plan_comment_rate` are WARN verdicts by ratification: a prose marker line that
disagrees with the typed pointer is a readability defect (the metadata wins by
contract, so nothing is broken), and a fast-writing day is a smell rather than a
rule — "a session writing records this fast is usually blocked rather than
productive" is a thing somebody should SEE, not a thing to refuse.

The two ERROR verdicts are SCOPED to plan records, per the ratified clauses: an
epic owes close evidence when its slug names a live or archived directory, and
owes a typed pointer when it is OPEN and its slug names a LIVE one. An epic with
no directory at all owes neither, and grading it would report a violation of a
rule the contract does not state.

Close evidence is owed from `CLOSE_EVIDENCE_CUTOFF_DAY` forward, for the same
reason: an epic closed before the writing primitive existed owes evidence to a
discipline that had no mechanism, and its only remaining route to green would be
to fabricate the comment. See that constant for the pinned commit.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from livespec_dev_tooling.checks._plan_ledger import CommentReader, record_id
from livespec_dev_tooling.checks._plan_record_comments import (
    comment_day,
    comment_text,
    is_completeness_review_evidence,
    newest_handoff_action,
)
from livespec_dev_tooling.checks._plan_record_model import (
    ERROR_VERDICT,
    WARN_VERDICT,
    Finding,
    closed_day,
    is_closed,
    plan_slug_of,
)
from livespec_dev_tooling.checks._plan_record_next_action import (
    NextAction,
    matches,
    parse_next_action,
    typing_violations,
)

__all__: list[str] = [
    "CLOSE_EVIDENCE_CUTOFF_DAY",
    "DEFAULT_DAILY_COMMENT_THRESHOLD",
    "timeline_findings",
]

DEFAULT_DAILY_COMMENT_THRESHOLD = 6

# The UTC day the archive gate's completeness-review-evidence discipline landed:
# `livespec-orchestrator-beads-fabro` commit 2a7e9107, "feat: orchestrate plan
# archive review evidence" (2026-08-16), which added `_plan_archive_review` and
# the `record_completeness_review_evidence` primitive that WRITES the comment
# this verdict reads. The check itself shipped 2026-09-06 and is the upper
# bound; the pinned commit is the earliest day an epic could have carried the
# evidence at all.
#
# This is a GRANDFATHER clause, not a severity knob. An epic closed before that
# day cannot satisfy the verdict by any honest route — the writing primitive did
# not exist, the stated remediation (re-run the archive gate) is unavailable on
# an already-archived plan, and appending the comment after the fact is the
# fabrication the verdict exists to prevent. Grading those closes reports a
# violation of a rule that had no mechanism. From the cutoff forward the
# evidence is required UNCONDITIONALLY, on every route into a closed status.
CLOSE_EVIDENCE_CUTOFF_DAY = "2026-08-16"

_EVIDENCE_REMEDIATION = (
    "record durable independent completeness-review evidence on the epic "
    "timeline through the plan operation's archive gate; a self-review, an "
    "unrecorded result, or a review that does not attest complete "
    "requirement-carrier coverage is not evidence."
)
_TYPED_REMEDIATION = (
    "write `next_action` as an object carrying `kind` (impl, spec-op, human or "
    "none), `ref` and `text`, beside a non-empty `last_session`, through the "
    "plan primitives — never by hand-editing epic metadata."
)
_DRIFT_REMEDIATION = (
    "update the typed `next_action` to match the prose, or reword the handoff's "
    "marker line; the metadata wins by contract, so a disagreeing prose line "
    "misleads the human reader it was written for."
)
_RATE_REMEDIATION = (
    "check whether the plan is blocked rather than productive; this warns and "
    "never refuses a write, and a genuinely busy day is allowed to exceed it."
)


def timeline_findings(
    *,
    epics: list[dict[str, object]],
    live_slugs: frozenset[str],
    record_slugs: frozenset[str],
    read_comments: CommentReader,
    repo: Path,
    threshold: int = DEFAULT_DAILY_COMMENT_THRESHOLD,
) -> list[Finding]:
    """Return every timeline-family verdict, reading each epic's comments once."""
    findings: list[Finding] = []
    for epic in epics:
        epic_id = record_id(record=epic)
        if epic_id is None:
            continue
        comments = read_comments(repo=repo, item_id=epic_id)
        slug = plan_slug_of(record=epic)
        findings.extend(
            _close_evidence_findings(
                epic=epic, epic_id=epic_id, comments=comments, graded=slug in record_slugs
            )
        )
        findings.extend(
            _next_action_findings(
                epic=epic, epic_id=epic_id, comments=comments, graded=slug in live_slugs
            )
        )
        findings.extend(
            _comment_rate_findings(epic_id=epic_id, comments=comments, threshold=threshold)
        )
    return findings


def _close_evidence_findings(
    *,
    epic: dict[str, object],
    epic_id: str,
    comments: list[dict[str, object]],
    graded: bool,
) -> list[Finding]:
    if not graded or not is_closed(record=epic) or _closed_before_cutoff(epic=epic):
        return []
    if any(
        is_completeness_review_evidence(text=comment_text(comment=comment)) for comment in comments
    ):
        return []
    return [
        Finding(
            check_id="plan_close_evidence",
            subject=epic_id,
            verdict=ERROR_VERDICT,
            message="closed plan epic carries no completeness-review evidence comment",
            remediation=_EVIDENCE_REMEDIATION,
        )
    ]


def _closed_before_cutoff(*, epic: dict[str, object]) -> bool:
    """Report whether an epic closed before the evidence discipline existed.

    ISO-8601 days sort lexicographically, so the comparison is the string one.
    An epic whose close day is UNKNOWN is graded rather than grandfathered: the
    cutoff excuses records the discipline could not reach, and a record carrying
    no readable stamp at all is not evidence of an early close.
    """
    day = closed_day(record=epic)
    return day is not None and day < CLOSE_EVIDENCE_CUTOFF_DAY


def _next_action_findings(
    *,
    epic: dict[str, object],
    epic_id: str,
    comments: list[dict[str, object]],
    graded: bool,
) -> list[Finding]:
    if not graded or is_closed(record=epic):
        return []
    action = parse_next_action(record=epic)
    if action is None:
        return [_typed(epic_id=epic_id, message="open plan epic carries no typed `next_action`")]
    findings = [
        _typed(epic_id=epic_id, message=message)
        for message in typing_violations(action=action, epic=epic)
    ]
    findings.extend(_drift_findings(epic_id=epic_id, action=action, comments=comments))
    return findings


def _drift_findings(
    *, epic_id: str, action: NextAction, comments: list[dict[str, object]]
) -> list[Finding]:
    recorded = newest_handoff_action(comments=comments)
    if recorded is None or matches(recorded=recorded, action=action):
        return []
    return [
        Finding(
            check_id="plan_next_action_drift",
            subject=epic_id,
            verdict=WARN_VERDICT,
            message=(
                f"newest handoff names next action {recorded!r}, which does not match the "
                f"typed pointer ({action.kind}, ref {action.ref!r})"
            ),
            remediation=_DRIFT_REMEDIATION,
        )
    ]


def _comment_rate_findings(
    *, epic_id: str, comments: list[dict[str, object]], threshold: int
) -> list[Finding]:
    days: Counter[str] = Counter()
    for comment in comments:
        day = comment_day(comment=comment)
        if day is not None:
            days[day] += 1
    return [
        Finding(
            check_id="plan_comment_rate",
            subject=epic_id,
            verdict=WARN_VERDICT,
            message=f"{count} comments on {day} exceeds the record-rate threshold of {threshold}",
            remediation=_RATE_REMEDIATION,
        )
        for day, count in sorted(days.items())
        if count > threshold
    ]


def _typed(*, epic_id: str, message: str) -> Finding:
    return Finding(
        check_id="plan_next_action_typed",
        subject=epic_id,
        verdict=ERROR_VERDICT,
        message=message,
        remediation=_TYPED_REMEDIATION,
    )
