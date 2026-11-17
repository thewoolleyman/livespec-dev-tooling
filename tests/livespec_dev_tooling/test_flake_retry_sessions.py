"""The session bookkeeping that keeps a nested pytest session from owning plugin state."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from livespec_dev_tooling.flake_retry_sessions import enter_session, is_nested, leave_session


def _config() -> SimpleNamespace:
    return SimpleNamespace(stash=pytest.Stash())


def test_the_first_session_to_start_is_not_nested() -> None:
    live: list[object] = []
    outer = _config()

    enter_session(config=outer, live=live)

    assert (is_nested(config=outer), live) == (False, [outer])


def test_a_session_that_starts_while_another_is_live_is_nested() -> None:
    live: list[object] = []
    outer = _config()
    inner = _config()

    enter_session(config=outer, live=live)
    enter_session(config=inner, live=live)

    assert (is_nested(config=outer), is_nested(config=inner)) == (False, True)


def test_a_finished_session_leaves_the_live_list_and_a_stranger_is_ignored() -> None:
    live: list[object] = []
    outer = _config()
    enter_session(config=outer, live=live)

    leave_session(config=_config(), live=live)
    leave_session(config=outer, live=live)

    assert live == []


def test_an_object_without_a_real_stash_is_never_nested_and_is_still_tracked() -> None:
    live: list[object] = [object()]
    stashless = SimpleNamespace(stash=object())

    enter_session(config=stashless, live=live)

    assert (is_nested(config=stashless), len(live)) == (False, 2)
