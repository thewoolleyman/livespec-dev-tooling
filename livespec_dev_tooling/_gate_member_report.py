"""The one structured line naming every aggregate member a run executed, and its verdict.

Two prefixes, one shape. The check aggregate's dispatcher closes its summary
with a `LIVESPEC_CHECK_MEMBERS` line, and a delegated gate Job re-prints the
LAST such line of its recipes' output as its own `LIVESPEC_GATE_MEMBERS` line
once its recipes have finished. The gate client reads only the Job's line.

The payload is a JSON object mapping each member that RAN to `passed` or
`failed`, in the order the aggregate listed them. A member the run skipped is
absent, because the line answers which members a verdict covered and a skipped
member was covered by nothing (livespec-dev-tooling's
`SPECIFICATION/contracts.md`, the evidence rule of its delegated pre-commit
aggregate section).

LAST WINS on both sides. A member's captured output can carry an earlier line
verbatim, for example a test that drives a fixture aggregate, and the outer
run prints its own line after every member's output.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import cast

__all__: list[str] = [
    "CHECK_MEMBERS_PREFIX",
    "GATE_MEMBERS_PREFIX",
    "MEMBER_FAILED",
    "MEMBER_PASSED",
    "format_member_line",
    "parse_member_report",
    "passed_members",
]

CHECK_MEMBERS_PREFIX = "LIVESPEC_CHECK_MEMBERS "
GATE_MEMBERS_PREFIX = "LIVESPEC_GATE_MEMBERS "
MEMBER_PASSED = "passed"
MEMBER_FAILED = "failed"
_VERDICTS = frozenset({MEMBER_PASSED, MEMBER_FAILED})


def format_member_line(*, prefix: str, ran: Iterable[tuple[str, bool]]) -> str:
    """Render `(member, passed)` pairs as one prefixed line, without its newline."""
    payload = {name: MEMBER_PASSED if passed else MEMBER_FAILED for name, passed in ran}
    return f"{prefix}{json.dumps(payload)}"


def parse_member_report(*, output: str) -> tuple[tuple[str, str], ...] | None:
    """The last gate-Job member line in `output`, or None when there is no usable one.

    Anything malformed answers None rather than a partial list: a report that
    cannot be read whole names no member, so it must not let a later reader
    skip one.
    """
    payload: str | None = None
    for line in output.splitlines():
        stripped = line.rstrip("\r")
        if stripped.startswith(GATE_MEMBERS_PREFIX):
            payload = stripped[len(GATE_MEMBERS_PREFIX) :]
    if payload is None:
        return None
    try:
        decoded: object = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict) or not decoded:
        return None
    pairs = tuple(cast("dict[object, object]", decoded).items())
    if not all(isinstance(name, str) and name and verdict in _VERDICTS for name, verdict in pairs):
        return None
    return cast("tuple[tuple[str, str], ...]", pairs)


def passed_members(*, report: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    """The members `report` names as run and passed, in its order."""
    return tuple(name for name, verdict in report if verdict == MEMBER_PASSED)
