"""The recovery principal reads every commit of the armed pull, not only the first page.

livespec-dev-tooling-gwzviw: `pulls/<n>/commits?per_page=100` answers one page of at
most one hundred commits. A pull with more landed more commits than the first page
named, so its messages could never equal the landed chain's and a revert the forge
had merged could not be recovered.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from livespec_dev_tooling._incident_recovery_effects import RecoveryEffects
from livespec_dev_tooling.incident_recovery_app import RecoveryForge

__all__: list[str] = []

_PAGE = 100
_FIRST = "pulls/7/commits?per_page=100"


def _rows(*, start: int, stop: int) -> list[dict[str, dict[str, str]]]:
    return [{"commit": {"message": f" message {index}\n"}} for index in range(start, stop)]


def _effects(*, answers: dict[str, tuple[int, object]], calls: list[str]) -> RecoveryEffects:
    def request(*, method: str, path: str) -> tuple[int, object]:
        assert method == "GET"
        calls.append(path)
        return answers.get(path, (404, {}))

    forge = SimpleNamespace(request=request)
    return RecoveryEffects(forge=cast("RecoveryForge", forge), root=Path("unused"), branch="master")


def _messages(*, count: int) -> tuple[str, ...]:
    return tuple(f"message {index}" for index in range(count))


def test_a_pull_of_more_than_one_page_is_read_in_full() -> None:
    calls: list[str] = []
    effects = _effects(
        answers={
            _FIRST: (200, _rows(start=0, stop=_PAGE)),
            f"{_FIRST}&page=2": (200, _rows(start=_PAGE, stop=150)),
        },
        calls=calls,
    )
    assert effects._pull_messages(number=7) == _messages(count=150)  # noqa: SLF001
    assert calls == [_FIRST, f"{_FIRST}&page=2"]


def test_a_pull_of_exactly_one_full_page_asks_for_the_next_and_stops_on_its_empty_answer() -> None:
    calls: list[str] = []
    effects = _effects(
        answers={_FIRST: (200, _rows(start=0, stop=_PAGE)), f"{_FIRST}&page=2": (200, [])},
        calls=calls,
    )
    assert effects._pull_messages(number=7) == _messages(count=_PAGE)  # noqa: SLF001
    assert calls == [_FIRST, f"{_FIRST}&page=2"]


def test_a_short_first_page_is_the_whole_pull() -> None:
    calls: list[str] = []
    effects = _effects(answers={_FIRST: (200, _rows(start=0, stop=3))}, calls=calls)
    assert effects._pull_messages(number=7) == _messages(count=3)  # noqa: SLF001
    assert calls == [_FIRST]


@pytest.mark.parametrize(
    "later",
    [(500, {"message": "server error"}), (200, {"message": "not a list"}), (200, [{"commit": 1}])],
)
def test_a_later_page_that_cannot_be_read_leaves_the_messages_unproven(
    later: tuple[int, object],
) -> None:
    effects = _effects(
        answers={_FIRST: (200, _rows(start=0, stop=_PAGE)), f"{_FIRST}&page=2": later}, calls=[]
    )
    assert effects._pull_messages(number=7) is None  # noqa: SLF001


def test_the_read_is_bounded_by_the_forges_own_commit_listing_ceiling() -> None:
    calls: list[str] = []
    full = (200, _rows(start=0, stop=_PAGE))
    effects = _effects(
        answers={_FIRST: full, f"{_FIRST}&page=2": full, f"{_FIRST}&page=3": full}, calls=calls
    )
    assert len(effects._pull_messages(number=7) or ()) == 3 * _PAGE  # noqa: SLF001
    assert calls == [_FIRST, f"{_FIRST}&page=2", f"{_FIRST}&page=3"]
