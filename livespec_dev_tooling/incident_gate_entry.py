"""Resolve incident mode at every direct gate entrance before any gate work.

The installed commit/push hooks reach incident mode through
`incident_hook_entry`. Every other independently invocable entrance (the
`check` aggregate recipes, `check-pre-push`, `check-pre-commit`,
`lint-autofix-staged`, `check-commit-pairs-source-and-test`, the direct coverage
recipes, the delegated gate clients, the detached runner's venue selection and
`check-red-green-replay`) calls this boundary first. It reuses the hook
boundary's shared flag parser and its registered-authority trust path, so there
is exactly one parser and one notion of a trusted incident context.

Three outcomes, mirroring the hook entrance:

- both flags unset (or explicitly false): `normal`, and the caller's complete
  normal body continues unchanged;
- a malformed flag value: a named `invalid-incident-flag` configuration refusal;
- a flag set without a trusted incident receipt from the registered canonical
  authority: a named `untrusted-incident-receipt` refusal.

A trusted incident context continues only at a LAUNCHER entrance (the detached
runner, whose child is itself a hook-mediated operation that re-resolves). Every
other direct entrance refuses with `no-direct-incident-mode`: incident gates are
selected only by the commit/push hook entrance, so a direct aggregate never runs
nested and never falls back to normal mode after an incident request.
"""

from __future__ import annotations

import functools
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    Invocation,
    parse_incident_truth_value,
    resolve_execution_context,
)
from livespec_dev_tooling.incident_hook_entry import LOCAL_OPERATION_ENV, QUERY_ENV
from livespec_dev_tooling.incident_hook_process import (
    HookRefusalError,
    invoke_authority,
    parse_query,
    resolve_current,
)

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import impure_safe  # noqa: E402 — vendor-path-aware import.
from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402 — vendor-path-aware import.

__all__: list[str] = [
    "ENTRANCES",
    "NORMAL",
    "REFUSED",
    "EntranceDecision",
    "IncidentEntrance",
    "entrance_refusal",
    "main",
    "resolve_entrance",
]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-6bmta2
NORMAL = 75
REFUSED = 78
ENTRANCES = frozenset(
    (
        "check",
        "check-changed",
        "check-commit-pairs-source-and-test",
        "check-coverage",
        "check-per-file-coverage",
        "check-pre-commit",
        "check-pre-push",
        "check-red-green-replay",
        "check-scoped",
        "gate-remote-delegate",
        "gate-runner",
        "lint-autofix-staged",
        "pre-commit-delegate",
    )
)


@dataclass(frozen=True, kw_only=True)
class EntranceDecision:
    """One entrance's resolved mode: `normal`, `incident` or `refused`."""

    mode: str
    status: int
    reason: str = ""


def _refused(*, surface: str, code: str, detail: str) -> EntranceDecision:
    reason = f"incident-gate-refused: {surface}: {code}: {detail}"
    _ = sys.stderr.write(reason + "\n")
    return EntranceDecision(mode="refused", status=REFUSED, reason=reason)


@impure_safe
def _trust_current() -> None:
    query = parse_query(text=os.environ.get(QUERY_ENV, "{}"))
    local_operation = os.environ.get(LOCAL_OPERATION_ENV, "")
    if query is None or not local_operation.strip() or local_operation != local_operation.strip():
        message = "exact canonical query and distinct local operation identity required"
        raise HookRefusalError(message)
    reading = invoke_authority(repo=Path.cwd(), query=query, action="read-current")
    _ = resolve_current(reading=reading, query=query)


def _trusted_normal_decision(*, surface: str, invocation: str) -> EntranceDecision | None:
    """Resolve an explicit trusted-normal caller before ambient flags are inspected."""
    if invocation == Invocation.ORDINARY:
        return None
    resolved = resolve_execution_context(environ=os.environ, invocation=invocation, identity=None)
    if not resolved.is_successful:
        refusal = resolved.failure()
        return _refused(surface=surface, code=refusal.code, detail=refusal.detail)
    return EntranceDecision(mode="normal", status=NORMAL)


def _ambient_decision(*, surface: str, launcher: bool) -> EntranceDecision:
    """Resolve ordinary ambient flags after the trusted-origin boundary has run."""
    flags = [
        parse_incident_truth_value(name=name, value=os.environ.get(name))
        for name in (EXPEDITED_INCIDENT_RESPONSE, EXPEDITED_INCIDENT_RESPONSE_REVERT)
    ]
    malformed = [flag.failure() for flag in flags if not is_successful(flag)]
    if malformed:
        return _refused(surface=surface, code=malformed[0].code, detail=malformed[0].detail)
    if not any(flag.unwrap() for flag in flags):
        return EntranceDecision(mode="normal", status=NORMAL)
    trusted = _trust_current()
    if not is_successful(trusted):
        detail = str(unsafe_perform_io(trusted.failure()))
        return _refused(surface=surface, code="untrusted-incident-receipt", detail=detail)
    if not launcher:
        return _refused(
            surface=surface,
            code="no-direct-incident-mode",
            detail="incident gates run only through the installed commit/push hook entrance",
        )
    return EntranceDecision(mode="incident", status=NORMAL)


def resolve_entrance(
    *, surface: str, launcher: bool = False, invocation: str = Invocation.ORDINARY
) -> EntranceDecision:
    """Decide one entrance's mode before its first selection, probe or submission."""
    if surface not in ENTRANCES:
        return _refused(surface=surface, code="unknown-entrance", detail="not a gate entrance")
    trusted_normal = _trusted_normal_decision(surface=surface, invocation=invocation)
    if trusted_normal is not None:
        return trusted_normal
    return _ambient_decision(surface=surface, launcher=launcher)


def entrance_refusal(*, surface: str) -> int | None:
    """Return None to continue the normal body, or the terminal refusal status."""
    decision = resolve_entrance(surface=surface)
    return None if decision.mode == "normal" else decision.status


@dataclass(frozen=True, kw_only=True)
class IncidentEntrance:
    """Decorate a zero-argument entrance `main` so this boundary runs before its body."""

    surface: str

    def __call__(self, entry: Callable[[], int]) -> Callable[[], int]:
        surface = self.surface

        @functools.wraps(entry)
        def guarded() -> int:
            refused = entrance_refusal(surface=surface)
            return entry() if refused is None else refused

        return guarded


def main(*, argv: list[str] | None = None) -> int:
    """Exit 75 only for the unchanged normal body; every other exit is terminal."""
    args = sys.argv[1:] if argv is None else argv
    surface = args[0] if len(args) == 1 else ""
    return resolve_entrance(surface=surface).status


if __name__ == "__main__":
    raise SystemExit(main())
