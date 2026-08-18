"""Document-scoped charter defect detectors."""

from __future__ import annotations

import re

__all__: list[str] = [
    "adoptable_runtime_contract",
    "unattended_charter_missing_perform_the_unblock",
]

ADOPTABLE_RUNTIME_HEADING = "## Adoptable runtime launch and restart"
ADOPTABLE_RUNTIME_REQUIREMENTS = (
    "claude --dangerously-skip-permissions -n <topic>",
    "/rename <topic>",
    "signals.is_structured_gate",
    "numbered cursor",
    "permission question",
    'codex resume --dangerously-bypass-approvals-and-sandbox <session-id> "<kick>"',
    "session_index.jsonl",
    "thread_name",
    "tmux session name is not an adoption key",
    "daemon's own launch paths unchanged",
    "fuzzy matching",
    "tmux-name matching",
    "live killing",
    "blocking",
)
UNATTENDED_CHARTER_MARKERS = (
    "# Supervisor Protocol",
    "Shared role-level instructions for every generated supervisor handoff",
)
PICKER_PRESENTATION_MARKERS = (
    "AskUserQuestion",
    "picker",
)
PERFORM_UNBLOCK = re.compile(
    r"if\s+the\s+supervisor\s+can\s+perform\s+the\s+unblock,\s+perform\s+it",
    re.IGNORECASE,
)
UNCHANGED_LAUNCH_PATHS = re.compile(
    r"daemon's own launch paths(?: \w+){0,2} unchanged",
)


def unattended_charter_missing_perform_the_unblock(*, text: str) -> list[str]:
    """An unattended supervisor charter with picker rules must authorize unblocks."""
    if not any(marker in text for marker in UNATTENDED_CHARTER_MARKERS):
        return []
    if not all(marker.casefold() in text.casefold() for marker in PICKER_PRESENTATION_MARKERS):
        return []
    if PERFORM_UNBLOCK.search(text) is not None:
        return []
    return ["unattended charter presents a picker without perform-the-unblock authority"]


def requirement_is_present(*, requirement: str, normalized: str) -> bool:
    if requirement == "daemon's own launch paths unchanged":
        return UNCHANGED_LAUNCH_PATHS.search(normalized) is not None
    return requirement.casefold() in normalized


def adoptable_runtime_contract(*, text: str) -> list[str]:
    """Require the shared launch/restart contract when a charter declares it."""
    if ADOPTABLE_RUNTIME_HEADING not in text:
        return []
    normalized = " ".join(text.split()).casefold()
    missing = [
        requirement
        for requirement in ADOPTABLE_RUNTIME_REQUIREMENTS
        if not requirement_is_present(requirement=requirement, normalized=normalized)
    ]
    if not missing:
        return []
    return [f"missing required adoption rule(s): {', '.join(missing)}"]
