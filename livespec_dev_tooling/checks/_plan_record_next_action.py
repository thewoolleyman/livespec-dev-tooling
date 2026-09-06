"""The typed `next_action` pointer: how it is read, typed, and compared to prose.

The pointer concern, held apart from the verdicts that report it
(`_plan_record_timeline`). Per the ratified contract governing the typed
`next_action` and `last_session` metadata, an open plan epic's pointer is an
object carrying exactly `kind`, `ref` and `text`, beside a non-empty
`last_session` naming who wrote it and when. `kind` is one of `impl`,
`spec-op`, `human` or `none`; `impl` and `spec-op` MUST carry a ref (they are
dispatchable action ids), `none` MUST NOT.

An ABSENT pointer and an ILL-TYPED one are different answers here, unlike in the
resume path that reads the same metadata. A resume collapses them — both mean
there is nothing to act on — but naming the typing violation is exactly this
family's job, so `parse_next_action` returns the object it found and
`typing_violations` grades it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_dev_tooling.checks._plan_record_model import (
    LAST_SESSION_METADATA_KEY,
    NEXT_ACTION_METADATA_KEY,
    metadata_string,
    record_metadata,
)

__all__: list[str] = [
    "NEXT_ACTION_KINDS",
    "NextAction",
    "matches",
    "parse_next_action",
    "typing_violations",
]

NEXT_ACTION_KINDS: tuple[str, ...] = ("impl", "spec-op", "human", "none")

_REF_REQUIRED_KINDS = frozenset({"impl", "spec-op"})
_NONE_KIND = "none"


@dataclass(frozen=True, kw_only=True)
class NextAction:
    """One epic's typed pointer, as the metadata carries it."""

    kind: str
    ref: str
    text: str


def parse_next_action(*, record: dict[str, object]) -> NextAction | None:
    """Return the typed pointer, or None when the key is absent or not an object."""
    value = record_metadata(record=record).get(NEXT_ACTION_METADATA_KEY)
    if not isinstance(value, dict):
        return None
    fields = cast("dict[str, object]", value)
    return NextAction(
        kind=_field(fields=fields, key="kind"),
        ref=_field(fields=fields, key="ref"),
        text=_field(fields=fields, key="text"),
    )


def typing_violations(*, action: NextAction, epic: dict[str, object]) -> list[str]:
    """Return every typing rule this pointer breaks, in the contract's order."""
    violations: list[str] = []
    if action.kind not in NEXT_ACTION_KINDS:
        violations.append(f"next_action kind {action.kind!r} is not one of {NEXT_ACTION_KINDS}")
    if action.kind in _REF_REQUIRED_KINDS and action.ref == "":
        violations.append(f"next_action kind {action.kind!r} carries an empty ref")
    if action.kind == _NONE_KIND and action.ref != "":
        violations.append("next_action kind 'none' carries a ref")
    if action.text == "":
        violations.append("next_action carries no text")
    if metadata_string(record=epic, key=LAST_SESSION_METADATA_KEY) == "":
        violations.append("epic carries no `last_session`")
    return violations


def matches(*, recorded: str, action: NextAction) -> bool:
    """Report whether a prose marker line agrees with the typed pointer.

    Agreement is generous on purpose: the prose line is written for a person and
    the pointer for a machine, so naming the same `ref` counts as agreement even
    when the sentence around it differs. `plan_next_action_drift` reports a real
    disagreement, not a wording difference.
    """
    normalized = _normalized(text=recorded)
    if normalized == _normalized(text=action.text):
        return True
    return action.ref != "" and action.ref.casefold() in normalized


def _field(*, fields: dict[str, object], key: str) -> str:
    value = fields.get(key)
    return value.strip() if isinstance(value, str) else ""


def _normalized(*, text: str) -> str:
    return " ".join(text.split()).casefold()
