"""The incident forge-call retry rule, and its two definitions held equal (livespec-dev-tooling-levu6j).

`livespec_dev_tooling._forge_policy` is the released entrance's definition; the
composite Action `.github/actions/forge-read` carries the workflow-side one as a
stdlib command. `SPECIFICATION/contracts.md`, in its expedited incident execution rules,
requires a test that drives both through the same scripted answers and fails when
they differ in kinds, retries, waits, stopping point or printed lines.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

from livespec_dev_tooling import _forge_policy as policy

__all__: list[str] = []

_ACTION_COMMAND = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "actions"
    / "forge-read"
    / "livespec-forge-read"
)
_NOW = 1_800_000_000.0


def _action():
    loader = importlib.machinery.SourceFileLoader("livespec_forge_read", str(_ACTION_COMMAND))
    spec = importlib.util.spec_from_loader("livespec_forge_read", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _answer(*, status, body="", headers=None, stderr=""):
    return {"status": status, "body": body, "headers": headers or {}, "stderr": stderr}


_OK = _answer(status=200, body='{"ok": true}')

# The nine scripted sequences the contract names, plus the success path.
_SEQUENCES: dict[str, tuple[str, list[dict[str, object]]]] = {
    "2xx-not-json": ("GET", [_answer(status=200, body="Server busy"), _OK]),
    "502": ("GET", [_answer(status=502, body='{"message":"Bad Gateway"}'), _OK]),
    "no-status": ("GET", [_answer(status=None, stderr="connection reset"), _OK]),
    "time-limit": ("GET", [_answer(status=None, stderr="timed out after 30s"), _OK]),
    "429-retry-after": (
        "GET",
        [_answer(status=429, body="{}", headers={"retry-after": "20"}), _OK],
    ),
    "secondary-403-reset": (
        "GET",
        [
            _answer(
                status=403,
                body='{"message":"You have exceeded a secondary rate limit"}',
                headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(_NOW) + 45)},
            ),
            _OK,
        ],
    ),
    "rate-limited-no-header": (
        "GET",
        [
            _answer(status=429, body="{}"),
            _answer(status=429, body="{}"),
            _OK,
        ],
    ),
    "rate-limited-past-budget": (
        "GET",
        [_answer(status=429, body="{}", headers={"retry-after": "400"})],
    ),
    "404-json": ("GET", [_answer(status=404, body='{"message":"Not Found"}')]),
    "all-5xx": ("GET", [_answer(status=503, body="{}")] * 6),
    "write-5xx-outcome-unknown": ("POST", [_answer(status=502, body="{}")]),
    "write-429-repeats": (
        "POST",
        [
            _answer(status=429, body="{}", headers={"retry-after": "10"}),
            _answer(status=201, body=""),
        ],
    ),
    "success": ("GET", [_OK]),
}


def _drive_package(*, method, answers):
    queue = list(answers)
    waits: list[float] = []

    def attempt():
        nxt = queue.pop(0)
        return policy.Attempt(
            status=nxt["status"], headers=nxt["headers"], body=nxt["body"], stderr=nxt["stderr"]
        )

    result = policy.run_call(
        name="pr-body",
        method=method,
        idempotent=False,
        attempt=attempt,
        sleep=waits.append,
        now=lambda: _NOW,
    )
    return result.outcome, result.status, result.kind, waits, list(result.lines)


def _drive_action(*, method, answers):
    action = _action()
    queue = list(answers)
    waits: list[float] = []
    lines: list[str] = []

    def attempt():
        nxt = queue.pop(0)
        return action.Attempt(
            status=nxt["status"], headers=nxt["headers"], body=nxt["body"], stderr=nxt["stderr"]
        )

    outcome, got, kind = action.run_call(
        name="pr-body",
        method=method,
        idempotent=False,
        attempt=attempt,
        sleep=waits.append,
        now=lambda: _NOW,
        emit=lines.append,
    )
    return outcome, got.status, kind, waits, lines


@pytest.mark.parametrize("case", sorted(_SEQUENCES))
def test_the_action_and_the_entrance_apply_the_same_rule(case: str) -> None:
    method, answers = _SEQUENCES[case]
    assert _drive_action(method=method, answers=answers) == _drive_package(
        method=method, answers=answers
    )


def test_the_contract_scenario_waits_two_four_then_twenty_and_reads_the_fourth_answer() -> None:
    answers = [
        _answer(status=200, body="not json"),
        _answer(status=502, body="{}"),
        _answer(status=429, body="{}", headers={"retry-after": "20"}),
        _OK,
    ]
    outcome, status, kind, waits, lines = _drive_package(method="GET", answers=answers)
    assert (outcome, status, kind, waits) == ("answer", 200, "answer", [2, 4, 20])
    assert [line.split(" kind=")[1].split(" ")[0] for line in lines] == [
        "not_json",
        "server_error",
        "rate_limited",
    ]


def test_every_5xx_stops_after_six_attempts_naming_the_call() -> None:
    outcome, status, kind, waits, lines = _drive_package(
        method="GET", answers=[_answer(status=503, body="{}")] * 6
    )
    assert (outcome, status, kind) == ("failed", 503, "server_error")
    assert waits == [2, 4, 8, 16, 32]
    assert (
        lines[-1]
        == "forge-read: pr-body failed: attempts exhausted; last status 503, kind server_error"
    )


def test_a_wait_past_the_budget_fails_at_once_without_waiting() -> None:
    outcome, _, kind, waits, lines = _drive_package(
        method="GET", answers=[_answer(status=429, body="{}", headers={"retry-after": "400"})]
    )
    assert (outcome, kind, waits) == ("failed", "rate_limited", [])
    assert "wait of 400s asked would pass the 300s budget" in lines[-1]


def test_header_less_rate_limits_double_from_sixty() -> None:
    _, _, _, waits, _ = _drive_package(
        method="GET", answers=[_answer(status=429, body="{}"), _answer(status=429, body="{}"), _OK]
    )
    assert waits == [60, 120]


def test_a_secondary_limit_waits_until_its_reset() -> None:
    reset = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(_NOW) + 45)}
    _, _, _, waits, _ = _drive_package(
        method="GET", answers=[_answer(status=403, body="{}", headers=reset), _OK]
    )
    assert waits == [45]


def test_a_short_named_wait_is_raised_to_the_doubling_wait() -> None:
    answers = [
        _answer(status=502, body="{}"),
        _answer(status=502, body="{}"),
        _answer(status=429, body="{}", headers={"retry-after": "1"}),
        _OK,
    ]
    _, _, _, waits, _ = _drive_package(method="GET", answers=answers)
    assert waits == [2, 4, 8]


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (401, "{}", "forbidden"),
        (403, '{"message":"Resource not accessible by integration"}', "forbidden"),
        (404, "{}", "not_found"),
        (409, "{}", "transport"),
        (422, "{}", "transport"),
    ],
)
def test_a_json_error_answer_fails_at_once(status: int, body: str, kind: str) -> None:
    outcome, _, got, waits, lines = _drive_package(
        method="GET", answers=[_answer(status=status, body=body)]
    )
    assert (outcome, got, waits) == ("failed", kind, [])
    assert lines[-1].endswith(f"answer not retryable; last status {status}, kind {kind}")


def test_a_non_json_error_answer_to_a_read_is_retried() -> None:
    outcome, _, _, waits, _ = _drive_package(
        method="GET", answers=[_answer(status=404, body="<html>"), _OK]
    )
    assert (outcome, waits) == ("answer", [2])


def test_a_non_idempotent_write_ends_outcome_unknown_on_a_5xx() -> None:
    outcome, status, kind, waits, lines = _drive_package(
        method="POST", answers=[_answer(status=502, body="{}")]
    )
    assert (outcome, status, kind, waits) == ("outcome-unknown", 502, "server_error", [])
    assert "outcome-unknown write" in lines[-1]


def test_a_write_answer_is_any_2xx_whatever_its_body() -> None:
    outcome, status, _, _, _ = _drive_package(method="POST", answers=[_answer(status=204, body="")])
    assert (outcome, status) == ("answer", 204)


def test_an_idempotent_write_is_retried_like_a_read() -> None:
    queue = [
        policy.Attempt(status=503, headers={}, body="{}", stderr=""),
        policy.Attempt(status=200, headers={}, body="", stderr=""),
    ]
    waits: list[float] = []
    result = policy.run_call(
        name="hold-release",
        method="PATCH",
        idempotent=True,
        attempt=lambda: queue.pop(0),
        sleep=waits.append,
        now=lambda: _NOW,
    )
    assert (result.outcome, waits) == ("answer", [2])


def test_each_failed_line_is_escaped_and_bounded() -> None:
    body = "line one\nline two\\" + "é" + "x" * 400
    _, _, _, _, lines = _drive_package(method="GET", answers=[_answer(status=502, body=body), _OK])
    printed = lines[0].split(" answer=")[1]
    assert "\n" not in printed
    assert printed.startswith("line one\\x0aline two\\\\\\xc3\\xa9x")
    assert len(printed.encode()) < 300


def test_an_attempt_with_no_body_prints_its_stderr() -> None:
    _, _, _, _, lines = _drive_package(
        method="GET", answers=[_answer(status=None, stderr="dial tcp: refused"), _OK]
    )
    assert lines[0] == (
        "forge-read: pr-body attempt 1/6 status=none kind=transport wait=2s answer=dial tcp: refused"
    )


def test_parse_included_reads_status_headers_and_body() -> None:
    got = policy.parse_included(
        stdout="HTTP/2.0 429 Too Many Requests\r\nRetry-After: 7\r\nNo-Colon-Line\r\n\r\n{}",
        stderr="",
    )
    assert (got.status, got.headers, got.body) == (429, {"retry-after": "7"}, "{}")


@pytest.mark.parametrize("stdout", ["", "garbage without a status line", "HTTP/2.0 200 OK"])
def test_parse_included_without_a_status_block_is_an_attempt_with_no_status(stdout: str) -> None:
    got = policy.parse_included(stdout=stdout, stderr="boom")
    assert (got.status, got.headers, got.body, got.stderr) == (None, {}, "", "boom")


def test_the_action_parses_included_output_like_the_entrance() -> None:
    action = _action()
    text = "HTTP/1.1 502 Bad Gateway\nX-A: b\n\nbody"
    mine = policy.parse_included(stdout=text, stderr="")
    theirs = action.parse_included(stdout=text, stderr="")
    assert (theirs.status, theirs.headers, theirs.body) == (
        mine.status,
        dict(mine.headers),
        mine.body,
    )
    assert action.parse_included(stdout="x", stderr="e").status is None


class _Done:
    def __init__(self, *, stdout: str) -> None:
        self.stdout = stdout
        self.stderr = ""


def _replay(*, monkeypatch, action, replies: list[object]) -> list[list[str]]:
    """Replace the command's `subprocess.run` with replies played in order, logging each argv."""
    calls: list[list[str]] = []
    queue = list(replies)

    def run(argv, **_kwargs):
        calls.append(list(argv))
        reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return _Done(stdout=str(reply))

    monkeypatch.setattr(action.subprocess, "run", run)
    monkeypatch.setattr(action.time, "sleep", lambda _seconds: None)
    return calls


def test_the_command_writes_the_answer_body(monkeypatch, capsys) -> None:
    action = _action()
    calls = _replay(
        monkeypatch=monkeypatch, action=action, replies=['HTTP/2.0 200 OK\nX: y\n\n{"body": "hi"}']
    )
    assert action.main(["pr-body", "repos/o/r/pulls/7"]) == 0
    assert capsys.readouterr().out == '{"body": "hi"}'
    assert calls == [["gh", "api", "--include", "--method", "GET", "repos/o/r/pulls/7"]]


def test_the_command_exits_75_on_an_outcome_unknown_write(monkeypatch, capsys) -> None:
    action = _action()
    calls = _replay(
        monkeypatch=monkeypatch, action=action, replies=["HTTP/2.0 502 Bad Gateway\n\n{}"]
    )
    argv = ["hold-create", "--method", "POST", "--field", "name=ci-green", "repos/o/r/check-runs"]
    assert action.main(argv) == 75
    assert "outcome-unknown write" in capsys.readouterr().err
    assert calls[0][-3:] == ["--raw-field", "name=ci-green", "repos/o/r/check-runs"]


def test_the_command_exits_1_on_a_json_404(monkeypatch, capsys) -> None:
    action = _action()
    _replay(
        monkeypatch=monkeypatch,
        action=action,
        replies=['HTTP/2.0 404 Not Found\n\n{"message":"Not Found"}'],
    )
    assert action.main(["pr-body", "repos/o/r/pulls/7"]) == 1
    captured = capsys.readouterr()
    assert (captured.out, "kind not_found" in captured.err) == ("", True)


def test_the_command_paginates_into_one_array(monkeypatch, capsys) -> None:
    action = _action()
    _replay(
        monkeypatch=monkeypatch,
        action=action,
        replies=[
            'HTTP/2.0 200 OK\nLink: <https://api.github.com/x?page=2>; rel="next"\n\n{"p": 1}',
            'HTTP/2.0 200 OK\n\n{"p": 2}',
        ],
    )
    assert action.main(["jobs", "--paginate", "repos/o/r/actions/runs/1/jobs"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"p": 1}, {"p": 2}]


def test_the_command_reads_a_timed_out_or_unrunnable_gh_as_no_status(monkeypatch, capsys) -> None:
    action = _action()
    _replay(
        monkeypatch=monkeypatch,
        action=action,
        replies=[
            action.subprocess.TimeoutExpired(cmd="gh", timeout=30),
            OSError("gh: not found"),
            'HTTP/2.0 200 OK\n\n{"ok": true}',
        ],
    )
    assert action.main(["pr-body", "repos/o/r/pulls/7"]) == 0
    err = capsys.readouterr().err
    assert "status=none kind=transport wait=2s answer=timed out after 30s" in err
    assert "status=none kind=transport wait=4s answer=gh: not found" in err


def test_the_action_escapes_and_classifies_like_the_entrance() -> None:
    action = _action()
    text = "a\\b\nc\x07é"
    assert (
        action.escape_answer(text=text)
        == policy.escape_answer(text=text)
        == "a\\\\b\\x0ac\\x07\\xc3\\xa9"
    )
    included = "HTTP/2.0 401 Unauthorized\nNo-Colon-Line\nX-A: b\n\n{}"
    theirs = action.parse_included(stdout=included, stderr="")
    mine = policy.parse_included(stdout=included, stderr="")
    assert theirs.headers == dict(mine.headers) == {"x-a": "b"}
    assert action.kind_of(attempt=theirs, read=True) == "forbidden"
