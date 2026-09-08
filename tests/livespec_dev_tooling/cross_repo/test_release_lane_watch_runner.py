"""Tests for `release_lane_watch_runner` — the three-valued caller of the detector.

The exit code IS the contract the calling workflow renders annotations from:
0 healthy, 1 the lane is FAILING, 2 CANNOT MEASURE. The case these tests exist
for is the third one: a forge that is unreachable, unauthorized, or unparsable
must never be read as a green lane, because a watcher that cannot measure and
reports healthy is the vacuous pass the whole watcher exists to remove.

No network is reached. `urllib.request.urlopen` is substituted per test, and the
run history replayed through it is the same RECORDED `thewoolleyman/livespec`
`release-tag.yml` window the sibling `test_release_lane_watch` module documents:
the `v0.37.0` failure of 2026-08-20 over the `v0.30.3` green of 2026-08-12, and
the `v0.37.1` green of 2026-08-21 that ended the block.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

import pytest

from livespec_dev_tooling.cross_repo.release_lane_watch_runner import fetch_runs, main

_SLUG = "thewoolleyman/livespec"
_WORKFLOW = "release-tag.yml"
_TOKEN = "forge-token-for-the-double"

_RECORDED_RED_TAIL = [
    {"conclusion": "failure", "created_at": "2026-08-20T11:29:03Z"},
    {"conclusion": "failure", "created_at": "2026-08-19T15:53:59Z"},
    {"conclusion": "success", "created_at": "2026-08-12T01:04:02Z"},
]
_RECORDED_GREEN_TAIL = [
    {"conclusion": "success", "created_at": "2026-08-21T22:57:27Z"},
    *_RECORDED_RED_TAIL,
]


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


class _RecordedForge:
    """A `urlopen` double serving recorded page bodies in order, recording each URL."""

    def __init__(self, *, bodies: list[bytes]) -> None:
        self.bodies = bodies
        self.requested: list[str] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> _FakeResponse:
        assert timeout > 0
        self.requested.append(request.full_url)
        return _FakeResponse(body=self.bodies[len(self.requested) - 1])


class _UnreachableForge:
    """A `urlopen` double for the CANNOT-MEASURE track: the call never completes."""

    def __call__(self, request: urllib.request.Request, timeout: float) -> _FakeResponse:
        assert request.full_url
        assert timeout > 0
        raise urllib.error.URLError("connection refused")


def _page(*, runs: list[dict[str, str]]) -> bytes:
    return json.dumps({"workflow_runs": runs}).encode("utf-8")


def _invoked_as(*, monkeypatch: pytest.MonkeyPatch, workflow: str = _WORKFLOW) -> None:
    """Put the runner in the shape the reusable workflow invokes it in."""
    monkeypatch.setattr(sys, "argv", ["release_lane_watch_runner", workflow])
    monkeypatch.setenv("GITHUB_REPOSITORY", _SLUG)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", _TOKEN)


def test_unreachable_forge_yields_cannot_measure_and_never_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead forge is exit 2. Collapsing it into 0 would paint an outage green."""
    monkeypatch.setattr("urllib.request.urlopen", _UnreachableForge())
    _invoked_as(monkeypatch=monkeypatch)

    assert main() == 2


def test_unparsable_forge_body_yields_cannot_measure(monkeypatch: pytest.MonkeyPatch) -> None:
    """An HTML error page where JSON was expected is a measurement failure, not a lane."""
    monkeypatch.setattr("urllib.request.urlopen", _RecordedForge(bodies=[b"<html>502</html>"]))
    _invoked_as(monkeypatch=monkeypatch)

    assert main() == 2


def test_payload_without_workflow_runs_yields_cannot_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `Not Found` body parses cleanly and carries no history — still exit 2."""
    body = json.dumps({"message": "Not Found"}).encode("utf-8")
    monkeypatch.setattr("urllib.request.urlopen", _RecordedForge(bodies=[body]))
    _invoked_as(monkeypatch=monkeypatch)

    assert main() == 2


def test_json_body_that_is_not_an_object_yields_cannot_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare JSON array parses and carries no `workflow_runs` — still exit 2, never 0."""
    monkeypatch.setattr("urllib.request.urlopen", _RecordedForge(bodies=[b"[]"]))
    _invoked_as(monkeypatch=monkeypatch)

    assert main() == 2


@pytest.mark.parametrize("missing", ["workflow", "slug", "token"])
def test_missing_invocation_input_yields_cannot_measure(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """The watcher asks nothing it cannot ask correctly, and says so as exit 2."""
    _invoked_as(monkeypatch=monkeypatch, workflow="" if missing == "workflow" else _WORKFLOW)
    if missing == "slug":
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    if missing == "token":
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert main() == 2


def test_failing_lane_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """The replayed 2026-08-19..2026-08-20 red tail is the finding: exit 1."""
    monkeypatch.setattr(
        "urllib.request.urlopen", _RecordedForge(bodies=[_page(runs=_RECORDED_RED_TAIL)])
    )
    _invoked_as(monkeypatch=monkeypatch)

    assert main() == 1


def test_healthy_lane_exits_0(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same lane with the 2026-08-21 `v0.37.1` green on top: exit 0."""
    monkeypatch.setattr(
        "urllib.request.urlopen", _RecordedForge(bodies=[_page(runs=_RECORDED_GREEN_TAIL)])
    )
    _invoked_as(monkeypatch=monkeypatch)

    assert main() == 0


def test_fetch_runs_queries_the_workflow_scoped_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unscoped `/actions/runs` form ignores the workflow and returns every lane's runs."""
    forge = _RecordedForge(bodies=[_page(runs=_RECORDED_RED_TAIL)])
    monkeypatch.setattr("urllib.request.urlopen", forge)

    runs = fetch_runs(slug=_SLUG, workflow=_WORKFLOW, token=_TOKEN)

    assert runs == _RECORDED_RED_TAIL
    assert forge.requested == [
        f"https://api.github.com/repos/{_SLUG}/actions/workflows/{_WORKFLOW}"
        "/runs?per_page=100&page=1"
    ]


def test_fetch_runs_pages_until_a_short_page_then_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """A short page means the history is exhausted — no further request is made."""
    full = [
        {"conclusion": "failure", "created_at": f"2026-08-20T11:{n:02d}:00Z"} for n in range(60)
    ]
    forge = _RecordedForge(bodies=[_page(runs=full + full[:40]), _page(runs=full[:3])])
    monkeypatch.setattr("urllib.request.urlopen", forge)

    runs = fetch_runs(slug=_SLUG, workflow=_WORKFLOW, token=_TOKEN)

    assert runs is not None
    assert len(runs) == 103
    assert len(forge.requested) == 2


def test_fetch_runs_stops_at_the_page_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """A limit is a measurement boundary: the detector reports truncation, not this."""
    full = [
        {"conclusion": "failure", "created_at": f"2026-08-20T11:{n:02d}:00Z"} for n in range(50)
    ]
    forge = _RecordedForge(bodies=[_page(runs=full + full)] * 4)
    monkeypatch.setattr("urllib.request.urlopen", forge)

    runs = fetch_runs(slug=_SLUG, workflow=_WORKFLOW, token=_TOKEN)

    assert runs is not None
    assert len(runs) == 400
    assert len(forge.requested) == 4
