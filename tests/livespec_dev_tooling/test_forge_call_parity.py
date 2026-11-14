"""The entrance's forge call and the forge-read Action agree on real `gh --include` answers (livespec-dev-tooling-levu6j).

`test_forge_policy.py` holds the two rule definitions equal when each is handed
parsed attempts. This module drives the entrance through its real attempt path,
`budgeted_gh.forge_call(execute=...)`, with the bytes `gh api --include` prints,
including the `x-ratelimit-*` headers every real GitHub answer carries, and the
Action through the same bytes. The two MUST reach the same outcome, status, kind,
waits and printed lines. The rule is in `SPECIFICATION/contracts.md`, under its
expedited incident execution rules (proposal one-unretried-github-api-answer).
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest
from livespec_runtime_budget.github_budget import GhInvocation

from livespec_dev_tooling.budgeted_gh import forge_call

__all__: list[str] = []

_ACTION_COMMAND = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "actions"
    / "forge-read"
    / "livespec-forge-read"
)
_NOW = 1_800_000_000


def _action():
    loader = importlib.machinery.SourceFileLoader(
        "livespec_forge_read_parity", str(_ACTION_COMMAND)
    )
    spec = importlib.util.spec_from_loader("livespec_forge_read_parity", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _reply(*, status: int, body: str, remaining: str = "4000", extra: str = "") -> GhInvocation:
    head = (
        f"HTTP/2.0 {status} X\nx-ratelimit-limit: 5000\nx-ratelimit-remaining: {remaining}\n"
        f"x-ratelimit-reset: {_NOW + 45}\nx-ratelimit-used: 1\nx-ratelimit-resource: core\n{extra}"
    )
    return GhInvocation(
        argv="gh", stdout=f"{head}\n{body}", stderr=f"gh: X (HTTP {status})\n", returncode=1
    )


_OK = GhInvocation(
    argv="gh",
    stdout='HTTP/2.0 200 OK\nx-ratelimit-remaining: 4000\n\n{"ok":true}',
    stderr="",
    returncode=0,
)

_CASES: dict[str, tuple[str, bool, list[GhInvocation]]] = {
    "secondary-limit-403": (
        "GET",
        False,
        [
            _reply(
                status=403,
                body='{"message":"You have exceeded a secondary rate limit"}',
                remaining="0",
            ),
            _OK,
        ],
    ),
    "permission-403": (
        "GET",
        False,
        [_reply(status=403, body='{"message":"Resource not accessible by integration"}'), _OK],
    ),
    "502": ("GET", False, [_reply(status=502, body='{"message":"Bad Gateway"}'), _OK]),
    "idempotent-write-503": (
        "PATCH",
        True,
        [
            _reply(status=503, body="{}"),
            GhInvocation(argv="gh", stdout="HTTP/2.0 200 OK\n\n", stderr="", returncode=0),
        ],
    ),
    "rate-limits-double-from-every-earlier-one": (
        "GET",
        False,
        [
            _reply(status=429, body="{}", extra="retry-after: 10\n"),
            _reply(status=429, body="{}", extra="x-ratelimit-reset-unused: 1\n"),
            _OK,
        ],
    ),
    "budget-refusal-takes-no-wait": (
        "GET",
        False,
        [_reply(status=429, body="{}", extra="retry-after: 400\n")],
    ),
}


def _entrance(*, method: str, idempotent: bool, replies: list[GhInvocation]):
    queue = list(replies)
    waits: list[float] = []
    result = forge_call(
        name="pr-body",
        endpoint="repos/o/r/pulls/7",
        method=method,
        idempotent=idempotent,
        execute=lambda **_kwargs: queue.pop(0),
        sleep=waits.append,
        now=lambda: float(_NOW),
    )
    return result.outcome, result.status, result.kind, waits, list(result.lines)


def _workflow(*, method: str, idempotent: bool, replies: list[GhInvocation]):
    action = _action()
    queue = list(replies)
    waits: list[float] = []
    lines: list[str] = []

    def attempt():
        reply = queue.pop(0)
        return action.parse_included(stdout=reply.stdout, stderr=reply.stderr)

    outcome, got, kind = action.run_call(
        name="pr-body",
        method=method,
        idempotent=idempotent,
        attempt=attempt,
        sleep=waits.append,
        now=lambda: float(_NOW),
        emit=lines.append,
    )
    return outcome, got.status, kind, waits, lines


_EXPECTED: dict[str, tuple[str, int, str, list[float]]] = {
    "secondary-limit-403": ("answer", 200, "answer", [45]),
    "permission-403": ("failed", 403, "forbidden", []),
    "502": ("answer", 200, "answer", [2]),
    "idempotent-write-503": ("answer", 200, "answer", [2]),
    "rate-limits-double-from-every-earlier-one": ("answer", 200, "answer", [10, 120]),
    "budget-refusal-takes-no-wait": ("failed", 429, "rate_limited", []),
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_the_entrance_and_the_action_answer_real_gh_output_alike(case: str) -> None:
    method, idempotent, replies = _CASES[case]
    entrance = _entrance(method=method, idempotent=idempotent, replies=replies)
    workflow = _workflow(method=method, idempotent=idempotent, replies=replies)
    facts = (entrance == workflow, entrance[:4] == _EXPECTED[case])
    assert facts == (True, True)


def test_a_budget_refusal_prints_no_wait_it_never_takes() -> None:
    method, idempotent, replies = _CASES["budget-refusal-takes-no-wait"]
    lines = _entrance(method=method, idempotent=idempotent, replies=replies)[4]
    facts = (
        lines[0].split(" kind=")[1].split(" answer=")[0] == "rate_limited wait=none",
        "wait of 400s asked would pass the 300s budget" in lines[-1],
    )
    assert facts == (True, True)
