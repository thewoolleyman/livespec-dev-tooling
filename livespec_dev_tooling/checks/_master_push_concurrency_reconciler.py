"""Pure workflow scan for the temporary master-push/reconciler incompatibility."""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = ["ConcurrencyFinding", "reconciler_concurrency_findings"]


_RECONCILER_CALL = re.compile(
    r"^[ \t]*uses:[ \t]*\S*reusable-master-health-reconcile\.yml(?:@|[ \t]|$)",
    re.MULTILINE,
)
_TOP_LEVEL_CONCURRENCY = re.compile(r"^concurrency:\s*\S", re.MULTILINE)
_PUSH_TRIGGER = re.compile(
    r"^on:[ \t]*(?:push|\[[^\]]*\bpush\b[^\]]*\]|\n[ \t]+push[ \t]*:)",
    re.MULTILINE,
)


@dataclass(frozen=True, kw_only=True)
class ConcurrencyFinding:
    """A workflow whose top-level concurrency conflicts with reconciliation."""

    workflow: str
    reconciler_caller: str


def reconciler_concurrency_findings(*, workflows: dict[str, str]) -> list[ConcurrencyFinding]:
    """Return master-push concurrency groups that conflict with reconciler callers."""
    callers = tuple(path for path, source in workflows.items() if _RECONCILER_CALL.search(source))
    if not callers:
        return []
    return [
        ConcurrencyFinding(workflow=path, reconciler_caller=caller)
        for path, source in workflows.items()
        if _TOP_LEVEL_CONCURRENCY.search(source) and _PUSH_TRIGGER.search(source)
        for caller in callers
    ]
