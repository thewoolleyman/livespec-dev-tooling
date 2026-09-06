"""Reading one plan epic's append-only comment timeline.

The parsing half of the timeline family, held apart from the verdicts that grade
it (`_plan_record_timeline`). Three different questions are asked of the same
comment stream — is there durable completeness-review evidence, what does the
newest handoff say happens next, and how fast was this plan written to — and
each is a shape question about a comment body rather than a judgement about a
plan, which is why they read as one concern here.

The evidence and handoff header shapes are the ones the orchestrator's plan
primitives WRITE (`record_completeness_review_evidence` and `append_handoff`):
a prefix line, then `key: value` header lines, then a blank line and the body. A
reader that guessed a different shape would grade evidence nobody wrote.

The archiving actor is deliberately NOT compared here. The plan operation's own
gate rejects a self-review by comparing the reviewer against the actor
performing the archive; a static check has no archive actor to compare against,
so it grades the three durable attestations the comment carries and leaves the
identity comparison to the gate that has the identity.
"""

from __future__ import annotations

__all__: list[str] = [
    "comment_day",
    "comment_text",
    "is_completeness_review_evidence",
    "newest_handoff_action",
]

_COMPLETENESS_REVIEW_PREFIX = "plan-completeness-review-evidence"
_HANDOFF_PREFIX = "plan-handoff-entry"
_NEXT_ACTION_MARKER = "next action"
_MARKER_ORNAMENTS = "-*# "
_TRUE = "true"
_DAY_LENGTH = len("YYYY-MM-DD")
_TEXT_FIELD = "text"
_CREATED_AT_FIELD = "created_at"
_EXACTLY_ONE_ACTION = 1


def comment_text(*, comment: dict[str, object]) -> str:
    """Return one comment's body, empty when the record carries none."""
    value = comment.get(_TEXT_FIELD)
    return value if isinstance(value, str) else ""


def comment_day(*, comment: dict[str, object]) -> str | None:
    """Return one comment's UTC day as `YYYY-MM-DD`, or None when unreadable."""
    value = comment.get(_CREATED_AT_FIELD)
    if not isinstance(value, str):
        return None
    head, _, _ = value.partition("T")
    return head if len(head) == _DAY_LENGTH else None


def is_completeness_review_evidence(*, text: str) -> bool:
    """Report whether one comment is durable independent completeness-review evidence.

    All three attestations are required, because each removes a different way a
    review can be worthless: an unnamed reviewer, a self-review, and a review
    that did not attest complete requirement-carrier coverage.
    """
    fields = _evidence_fields(text=text)
    return (
        fields.get("reviewer-identity", "") != ""
        and fields.get("separate-reviewer") == _TRUE
        and fields.get("attests-complete-requirement-coverage") == _TRUE
    )


def newest_handoff_action(*, comments: list[dict[str, object]]) -> str | None:
    """Return the ONE next action the newest handoff names in prose, if exactly one.

    Zero actions and several actions are the same answer — None — because both
    leave nothing to compare the typed pointer against, and `plan_next_action_drift`
    reports a DISAGREEMENT rather than the absence of a prose line the contract
    does not require.
    """
    bodies = [
        text
        for comment in comments
        if (text := comment_text(comment=comment)).startswith(_HANDOFF_PREFIX)
    ]
    if not bodies:
        return None
    actions = _recorded_next_actions(body=bodies[-1])
    return actions[0] if len(actions) == _EXACTLY_ONE_ACTION else None


def _recorded_next_actions(*, body: str) -> tuple[str, ...]:
    """Return every next action a handoff body names in prose, in written order."""
    actions: list[str] = []
    for line in body.splitlines():
        marker_line = line.strip().lstrip(_MARKER_ORNAMENTS).strip()
        if not marker_line.casefold().startswith(_NEXT_ACTION_MARKER):
            continue
        _, separator, action = marker_line.partition(":")
        if separator != "" and action.strip() != "":
            actions.append(action.strip())
    return tuple(actions)


def _evidence_fields(*, text: str) -> dict[str, str]:
    """Parse the evidence comment's header block, empty when it is not one."""
    header = text.split("\n\n", maxsplit=1)[0]
    lines = header.splitlines()
    if not lines or lines[0] != _COMPLETENESS_REVIEW_PREFIX:
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        key, separator, value = line.partition(": ")
        if separator == "":
            return {}
        fields[key] = value
    return fields
