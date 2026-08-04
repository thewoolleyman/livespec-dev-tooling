"""Tests for `livespec_dev_tooling/fleet/_local_vantage.py`.

`local_vantage` answers ONE question — which member is this run executing
inside, and where is its checkout — and its value is mostly in the two
ways it declines to answer. Both are exercised here directly rather than
through `main()`, which is why the function was lifted out of
`fleet_conformance.py` in the first place.

⛔ THE FAIL-CLOSED DIRECTION IS THE POINT. When the self member cannot be
resolved, the correct answer is `(None, None)` — the FORGE vantage every
member had before the local read existed — never a guess derived from a
directory name or a configured value. A wrong self member would hand one
repo's tree to another repo's verdict, which is strictly worse than
reading a stale one. The two declining branches are therefore asserted
on their RETURN VALUE, not merely on "it didn't crash".
"""

from __future__ import annotations

from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.config import GitToplevelError
from livespec_dev_tooling.fleet._context import OriginRemoteUnresolved
from livespec_dev_tooling.fleet._local_vantage import local_vantage

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.fleet._local_vantage"


class _RecordingLog:
    """Minimal structlog stand-in that captures `info` calls."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append((event, kwargs))


def test_local_vantage_resolves_the_self_member_and_its_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(f"{_MODULE}.resolve_repo_root", lambda: Path("/checkout/here"))
    log = _RecordingLog()

    repo, root = local_vantage(running_as=IOSuccess("livespec-dev-tooling"), log=log)

    assert repo == "livespec-dev-tooling"
    assert root == Path("/checkout/here")
    # The resolving path is the quiet one: nothing to explain.
    assert log.events == []


def test_local_vantage_declines_when_the_origin_remote_is_unresolved() -> None:
    """An unresolvable origin remote leaves the WHOLE roster on its forge refs."""
    log = _RecordingLog()
    unresolved = OriginRemoteUnresolved(reason="no-origin", detail="no remote named origin")

    assert local_vantage(running_as=IOFailure(unresolved), log=log) == (None, None)

    # Reported, not swallowed: an unexplained vantage is unauditable from a run log.
    assert len(log.events) == 1
    event, fields = log.events[0]
    assert "canonical ref" in event
    assert fields["reason"] == "no-origin"


def test_local_vantage_declines_when_not_inside_a_git_working_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lane also runs off a checkout entirely; that is a decline, not a defect."""

    def _outside_worktree() -> Path:
        raise GitToplevelError("not a git working tree")

    monkeypatch.setattr(f"{_MODULE}.resolve_repo_root", _outside_worktree)
    log = _RecordingLog()

    assert local_vantage(running_as=IOSuccess("livespec-dev-tooling"), log=log) == (None, None)

    assert len(log.events) == 1
    event, fields = log.events[0]
    assert "git working tree" in event
    assert fields["member"] == "livespec-dev-tooling"
