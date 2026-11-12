"""The retry rule for one forge call, on the released side of the incident trust boundary.

`SPECIFICATION/contracts.md`, in its expedited incident execution rules (proposal
one-unretried-github-api-answer, work item livespec-dev-tooling-levu6j), defines
one rule for every forge call the `incident-ci` job, the `ci-green` job and the
incident label workflow make. Workflow steps get it from the composite Action
`.github/actions/forge-read`; the released incident CI entrance, which runs only
released code, gets it here. `tests/livespec_dev_tooling/test_forge_policy.py`
drives both through the same scripted answers and holds them equal.

The rule, as this module applies it:

- An attempt is retried when it carries an HTTP 5xx status, when it carries no
  status at all (including one stopped at its time limit), when it is rate
  limited, or, for a read, when its body does not parse as JSON.
- A non-idempotent write is repeated only after a rate-limited answer; after any
  other retryable answer its outcome is unknown and the call ends
  `outcome-unknown`.
- At most six attempts. Waits double from 2 seconds; a rate-limited answer waits
  what its `Retry-After` names, else until its `X-RateLimit-Reset` when
  `X-RateLimit-Remaining` is `0`, else 60 seconds doubled per header-less
  rate-limited answer, never less than the doubling wait. The waits of one call
  total at most 300 seconds.
- Each failed attempt is one escaped line naming the call, the attempt, the
  status, the kind, the next wait and the first 256 bytes of the answer.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

__all__: list[str] = [
    "ATTEMPT_TIMEOUT_SECONDS",
    "Attempt",
    "Budget",
    "CallResult",
    "escape_answer",
    "parse_included",
    "run_call",
]

MAX_ATTEMPTS = 6
ATTEMPT_TIMEOUT_SECONDS = 30
WAIT_BUDGET_SECONDS = 300
_ANSWER_BYTES = 256
_FIRST_WAIT = 2
_HEADERLESS_RATE_WAIT = 60
# The fleet `gh` read-failure classification's secondary-limit bodies
# (`livespec_dev_tooling/fleet/_read_failure.py`): a 403 is a rate limit only
# when its body says so, or when the primary budget it reports is spent.
_RATE_LIMIT_BODY = re.compile(
    r"rate limit|abuse detection mechanism|secondary quota", re.IGNORECASE
)
# The classification's kinds for the statuses it names; any other status is
# `transport`. 403 and the 5xx range need more than the status and are decided
# in `_kind`.
_STATUS_KINDS: dict[int, str] = {429: "rate_limited", 401: "forbidden", 404: "not_found"}
_HTTP_STATUS_LINE = re.compile(r"HTTP/[0-9.]+ (?P<status>[0-9]{3})")
_PRINTABLE_LOW = 0x20
_PRINTABLE_HIGH = 0x7E
_BACKSLASH = 0x5C


@dataclass(frozen=True, kw_only=True)
class Attempt:
    """What one attempt got: an HTTP status (None when it got none), headers, body, stderr."""

    status: int | None
    headers: Mapping[str, str]
    body: str
    stderr: str


@dataclass(kw_only=True)
class Budget:
    """The one bound a call shares across its attempts, and across the pages of a paginated call."""

    attempts: int = 0
    waits: int = 0
    waited: int = 0
    rate_limited_answers: int = 0


@dataclass(frozen=True, kw_only=True)
class CallResult:
    """How a call ended: `answer`, `failed` or `outcome-unknown`, with the last attempt's status."""

    outcome: str
    body: str
    status: int | None
    kind: str
    lines: tuple[str, ...] = field(default=())


def escape_answer(*, text: str) -> str:
    """The first 256 bytes of `text`, every control, non-ASCII and backslash byte escaped."""
    escaped: list[str] = []
    for byte in text.encode("utf-8", "surrogatepass")[:_ANSWER_BYTES]:
        if byte == _BACKSLASH:
            escaped.append("\\\\")
        elif _PRINTABLE_LOW <= byte <= _PRINTABLE_HIGH:
            escaped.append(chr(byte))
        else:
            escaped.append(f"\\x{byte:02x}")
    return "".join(escaped)


def parse_included(*, stdout: str, stderr: str) -> Attempt:
    """Read `gh api --include` output: the HTTP status line, the headers, then the body."""
    head, separator, body = stdout.replace("\r\n", "\n").partition("\n\n")
    lines = head.split("\n")
    matched = _HTTP_STATUS_LINE.match(lines[0]) if separator else None
    if matched is None:
        return Attempt(status=None, headers={}, body="", stderr=stderr)
    headers = {
        name.strip().lower(): value.strip()
        for name, colon, value in (line.partition(":") for line in lines[1:])
        if colon
    }
    return Attempt(status=int(matched["status"]), headers=headers, body=body, stderr=stderr)


def _parses(*, text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def _kind(*, attempt: Attempt, read: bool) -> str:
    status = attempt.status
    if status is None:
        return "transport"
    if 200 <= status < 300:  # noqa: PLR2004  — the 2xx success range.
        return "answer" if not read or _parses(text=attempt.body) else "not_json"
    if status == 403:  # noqa: PLR2004  — HTTP 403 shared by permission and secondary limits.
        limited = _RATE_LIMIT_BODY.search(attempt.body) is not None
        spent = attempt.headers.get("x-ratelimit-remaining") == "0"
        return "rate_limited" if limited or spent else "forbidden"
    if 500 <= status < 600:  # noqa: PLR2004  — the 5xx range.
        return "server_error"
    return _STATUS_KINDS.get(status, "transport")


def _retryable(*, kind: str, attempt: Attempt, as_read: bool) -> bool:
    if kind in {"rate_limited", "server_error", "not_json"} or attempt.status is None:
        return True
    return as_read and not _parses(text=attempt.body)


def _asked_wait(*, kind: str, attempt: Attempt, budget: Budget, now: Callable[[], float]) -> int:
    doubling = _FIRST_WAIT * 2**budget.waits
    if kind != "rate_limited":
        return doubling
    retry_after = attempt.headers.get("retry-after", "").strip()
    reset = attempt.headers.get("x-ratelimit-reset", "").strip()
    if retry_after.isdigit():
        asked = int(retry_after)
    elif attempt.headers.get("x-ratelimit-remaining") == "0" and reset.isdigit():
        asked = max(0, int(reset) - int(now()))
    else:
        # Doubled once for every earlier rate-limited answer of the call,
        # whatever header that answer carried.
        asked = _HEADERLESS_RATE_WAIT * 2**budget.rate_limited_answers
    budget.rate_limited_answers += 1
    return max(asked, doubling)


def _line(*, name: str, number: int, attempt: Attempt, kind: str, wait: str) -> str:
    status = "none" if attempt.status is None else str(attempt.status)
    answer = escape_answer(text=attempt.body or attempt.stderr)
    return (
        f"forge-read: {name} attempt {number}/{MAX_ATTEMPTS} status={status} "
        f"kind={kind} wait={wait} answer={answer}"
    )


def _failed(*, name: str, attempt: Attempt, kind: str, lines: list[str], why: str) -> CallResult:
    status = "none" if attempt.status is None else str(attempt.status)
    lines.append(f"forge-read: {name} failed: {why}; last status {status}, kind {kind}")
    outcome = "outcome-unknown" if why.startswith("outcome-unknown") else "failed"
    return CallResult(
        outcome=outcome, body="", status=attempt.status, kind=kind, lines=tuple(lines)
    )


def run_call(  # noqa: PLR0913  — the call's identity plus its four injected effects.
    *,
    name: str,
    method: str,
    idempotent: bool,
    attempt: Callable[[], Attempt],
    sleep: Callable[[float], None],
    now: Callable[[], float],
    budget: Budget | None = None,
) -> CallResult:
    """Make one forge call under the rule, emitting a line for each failed attempt."""
    shared = Budget() if budget is None else budget
    read = method.upper() == "GET"
    as_read = read or idempotent
    lines: list[str] = []
    while True:
        got = attempt()
        shared.attempts += 1
        kind = _kind(attempt=got, read=read)
        if kind == "answer":
            return CallResult(
                outcome="answer", body=got.body, status=got.status, kind=kind, lines=tuple(lines)
            )
        retry = _retryable(kind=kind, attempt=got, as_read=as_read)
        if retry and not as_read and kind != "rate_limited":
            lines.append(
                _line(name=name, number=shared.attempts, attempt=got, kind=kind, wait="none")
            )
            return _failed(
                name=name, attempt=got, kind=kind, lines=lines, why="outcome-unknown write"
            )
        if not retry or shared.attempts >= MAX_ATTEMPTS:
            lines.append(
                _line(name=name, number=shared.attempts, attempt=got, kind=kind, wait="none")
            )
            why = "attempts exhausted" if retry else "answer not retryable"
            return _failed(name=name, attempt=got, kind=kind, lines=lines, why=why)
        asked = _asked_wait(kind=kind, attempt=got, budget=shared, now=now)
        if shared.waited + asked > WAIT_BUDGET_SECONDS:
            # The wait is refused, never taken, so the line names none.
            lines.append(
                _line(name=name, number=shared.attempts, attempt=got, kind=kind, wait="none")
            )
            why = f"wait of {asked}s asked would pass the {WAIT_BUDGET_SECONDS}s budget"
            return _failed(name=name, attempt=got, kind=kind, lines=lines, why=why)
        lines.append(
            _line(name=name, number=shared.attempts, attempt=got, kind=kind, wait=f"{asked}s")
        )
        sleep(asked)
        shared.waits += 1
        shared.waited += asked
