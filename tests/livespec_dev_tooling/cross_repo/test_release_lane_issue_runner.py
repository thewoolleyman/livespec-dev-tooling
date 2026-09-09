"""Tests for `release_lane_issue_runner` — the forge-facing half of the producer.

Two contracts are under test and they are separable, which is why the double
below records every call rather than just the last one:

- THE WRITE. Exactly one `release-lane-red` issue per repo is opened, patched or
  closed, and the CANNOT-MEASURE row is the one that matters: an unmeasurable
  lane must patch the issue, never close it, because a closed issue reads as
  RECOVERED on the needs-attention screen and a lane that stopped being observed
  has not recovered.
- THE EXIT CODE. Unchanged from `release_lane_watch_runner`'s three-valued
  contract, taken worst-across-the-watched-set, so the job status still reports
  lane health even though the durable signal now lives in the issue.

No network is reached. `urllib.request.urlopen` is substituted per test, and the
run history replayed through it is the same RECORDED `thewoolleyman/livespec`
`release-tag.yml` window the sibling `test_release_lane_watch` modules document:
the `v0.37.0` failure of 2026-08-20 over the `v0.30.3` green of 2026-08-12, and
the `v0.37.1` green of 2026-08-21 that ended the block.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import cast

import pytest

from livespec_dev_tooling.cross_repo.release_lane_issue import (
    ACTION_NOOP,
    IssueAction,
)
from livespec_dev_tooling.cross_repo.release_lane_issue_runner import (
    apply_action,
    find_open_issue,
    main,
)

_SLUG = "thewoolleyman/livespec"
_LANE = "release-tag.yml"
_OTHER_LANE = "release-please.yml"
_TOKEN = "forge-token-for-the-double"
_ISSUE = 4127

_RECORDED_RED_TAIL = [
    {"conclusion": "failure", "created_at": "2026-08-20T11:29:03Z"},
    {"conclusion": "failure", "created_at": "2026-08-19T15:53:59Z"},
    {"conclusion": "success", "created_at": "2026-08-12T01:04:02Z"},
]
_RECORDED_GREEN_TAIL = [
    {"conclusion": "success", "created_at": "2026-08-21T22:57:27Z"},
    *_RECORDED_RED_TAIL,
]

_UNPARSABLE = b"<html>502 Bad Gateway</html>"
_WROTE = b'{"number": 4127}'


class _FakeResponse:
    """Stands in for the `http.client.HTTPResponse` context manager `urlopen` yields."""

    def __init__(self, *, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self.body


class _Forge:
    """A `urlopen` double routing by URL and method, recording every call it serves.

    `runs` maps a watched workflow file to the body its runs query answers with;
    `issues` is the body the labelled-issue query answers with, or None to make
    that query fail; `write` is the body a POST/PATCH answers with, or None to
    make the write fail.
    """

    def __init__(
        self,
        *,
        runs: dict[str, bytes],
        issues: bytes | None = b"[]",
        write: bytes | None = _WROTE,
    ) -> None:
        self.runs = runs
        self.issues = issues
        self.write = write
        self.calls: list[tuple[str, str]] = []
        self.writes: list[dict[str, object]] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> _FakeResponse:
        assert timeout > 0
        url = request.full_url
        self.calls.append((request.get_method(), url))
        data = request.data
        if isinstance(data, bytes):
            self.writes.append(cast("dict[str, object]", json.loads(data)))
        for workflow, body in self.runs.items():
            if f"/actions/workflows/{workflow}/" in url:
                return _FakeResponse(body=body)
        if request.get_method() == "GET":
            if self.issues is None:
                raise urllib.error.URLError("issue query refused")
            return _FakeResponse(body=self.issues)
        if self.write is None:
            raise urllib.error.URLError("issue write refused")
        return _FakeResponse(body=self.write)


def _runs(*, runs: list[dict[str, str]]) -> bytes:
    return json.dumps({"workflow_runs": runs}).encode("utf-8")


def _issue_rows(*, numbers: list[int]) -> bytes:
    return json.dumps([{"number": n} for n in numbers]).encode("utf-8")


def _invoked_as(*, monkeypatch: pytest.MonkeyPatch, workflows: list[str]) -> None:
    """Put the runner in the shape the reusable workflow invokes it in."""
    monkeypatch.setattr(sys, "argv", ["release_lane_issue_runner", *workflows])
    monkeypatch.setenv("GITHUB_REPOSITORY", _SLUG)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", _TOKEN)


def _calls_of(*, forge: _Forge, method: str) -> list[tuple[str, str]]:
    return [call for call in forge.calls if call[0] == method]


def test_red_lane_with_no_open_issue_opens_exactly_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first red run writes the issue the needs-attention screen reads."""
    forge = _Forge(runs={_LANE: _runs(runs=_RECORDED_RED_TAIL)})
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE])

    assert main() == 1
    assert _calls_of(forge=forge, method="POST") == [
        ("POST", f"https://api.github.com/repos/{_SLUG}/issues")
    ]
    assert forge.writes[0]["labels"] == ["release-lane-red"]
    assert _LANE in str(forge.writes[0]["body"])


def test_red_lane_with_an_open_issue_patches_it_instead_of_opening_a_second(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One issue per repo, reused — 123 cuts must not become 123 issues."""
    forge = _Forge(
        runs={_LANE: _runs(runs=_RECORDED_RED_TAIL)},
        issues=_issue_rows(numbers=[_ISSUE]),
    )
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE])

    assert main() == 1
    assert _calls_of(forge=forge, method="POST") == []
    assert _calls_of(forge=forge, method="PATCH") == [
        ("PATCH", f"https://api.github.com/repos/{_SLUG}/issues/{_ISSUE}")
    ]
    assert "state" not in forge.writes[0]


def test_recovered_lane_closes_the_open_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 2026-08-21 green ended the block, so the durable signal is retired."""
    forge = _Forge(
        runs={_LANE: _runs(runs=_RECORDED_GREEN_TAIL)},
        issues=_issue_rows(numbers=[_ISSUE]),
    )
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE])

    assert main() == 0
    assert forge.writes == [{"state": "closed"}]


def test_healthy_lane_with_no_open_issue_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The steady state is SILENT: a healthy fleet writes no issue at all."""
    forge = _Forge(runs={_LANE: _runs(runs=_RECORDED_GREEN_TAIL)})
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE])

    assert main() == 0
    assert forge.writes == []


def test_cannot_measure_patches_the_issue_and_never_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load-bearing row: an unobserved lane must not read as recovered."""
    forge = _Forge(runs={_LANE: _UNPARSABLE}, issues=_issue_rows(numbers=[_ISSUE]))
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE])

    assert main() == 2
    assert _calls_of(forge=forge, method="PATCH") == [
        ("PATCH", f"https://api.github.com/repos/{_SLUG}/issues/{_ISSUE}")
    ]
    assert forge.writes[0] != {"state": "closed"}
    assert "CANNOT MEASURE" in str(forge.writes[0]["body"])


def test_cannot_measure_with_no_open_issue_opens_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unmeasurable lane is a finding in its own right, not a quiet zero."""
    forge = _Forge(runs={_LANE: _UNPARSABLE})
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE])

    assert main() == 2
    assert _calls_of(forge=forge, method="POST") == [
        ("POST", f"https://api.github.com/repos/{_SLUG}/issues")
    ]


def test_worst_exit_across_the_watched_set_reports_cannot_measure_over_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A measured red lane beside an unmeasurable one is still exit 2, and BOTH list."""
    forge = _Forge(
        runs={_LANE: _runs(runs=_RECORDED_RED_TAIL), _OTHER_LANE: _UNPARSABLE},
        issues=_issue_rows(numbers=[_ISSUE]),
    )
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE, _OTHER_LANE])

    assert main() == 2
    body = str(forge.writes[0]["body"])
    assert f"{_LANE}: FAILING" in body
    assert f"{_OTHER_LANE}: CANNOT MEASURE" in body


@pytest.mark.parametrize("missing", ["workflows", "slug", "token"])
def test_missing_invocation_input_yields_cannot_measure_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """The watcher asks nothing it cannot ask correctly, and writes nothing either."""
    forge = _Forge(runs={_LANE: _runs(runs=_RECORDED_RED_TAIL)})
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[""] if missing == "workflows" else [_LANE])
    if missing == "slug":
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    if missing == "token":
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert main() == 2
    assert forge.calls == []


def test_an_unreadable_issue_query_writes_nothing_and_cannot_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`could not read` is not `there is none`: guessing here duplicates the issue."""
    forge = _Forge(runs={_LANE: _runs(runs=_RECORDED_GREEN_TAIL)}, issues=None)
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE])

    assert main() == 2
    assert forge.writes == []


def test_a_write_that_did_not_land_escalates_to_cannot_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The screen reads the ISSUE, so a lost write must not pass as a clean run."""
    forge = _Forge(runs={_LANE: _runs(runs=_RECORDED_RED_TAIL)}, write=None)
    monkeypatch.setattr("urllib.request.urlopen", forge)
    _invoked_as(monkeypatch=monkeypatch, workflows=[_LANE])

    assert main() == 2


def test_find_open_issue_queries_the_label_and_ignores_pull_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `/issues` collection returns PRs too; patching one would be a wrong write."""
    rows = json.dumps(
        [
            "not-an-object",
            {"number": 11, "pull_request": {"url": "…"}},
            {"title": "row with no number"},
            {"number": 88},
            {"number": _ISSUE},
        ]
    ).encode("utf-8")
    forge = _Forge(runs={}, issues=rows)
    monkeypatch.setattr("urllib.request.urlopen", forge)

    measured, number = find_open_issue(slug=_SLUG, token=_TOKEN)

    assert (measured, number) == (True, 88)
    assert forge.calls == [
        (
            "GET",
            f"https://api.github.com/repos/{_SLUG}/issues"
            "?labels=release-lane-red&state=open&per_page=100",
        )
    ]


def test_find_open_issue_reports_unmeasured_when_the_body_is_not_a_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `Not Found` object parses cleanly and is still not an answer."""
    forge = _Forge(runs={}, issues=b'{"message": "Not Found"}')
    monkeypatch.setattr("urllib.request.urlopen", forge)

    assert find_open_issue(slug=_SLUG, token=_TOKEN) == (False, None)


def test_apply_action_reaches_the_forge_not_at_all_for_a_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NOOP is the whole point of the silent steady state — it must cost no call."""
    forge = _Forge(runs={})
    monkeypatch.setattr("urllib.request.urlopen", forge)

    landed = apply_action(
        slug=_SLUG,
        token=_TOKEN,
        action=IssueAction(kind=ACTION_NOOP, issue_number=None, body=None),
    )

    assert landed is True
    assert forge.calls == []
