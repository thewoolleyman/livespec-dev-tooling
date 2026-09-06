"""Green-leg edge for `red_green_replay` — an unreadable HEAD refuses the commit.

A `*_edges.py`-convention sibling of `test_red_green_replay.py`, per the
Green-leg rule: the Red-recorded test file of a Red→Green pair is
byte-identity-bound, so tests authored at the Green amend land beside it.

WHAT THIS PINS — livespec-dev-tooling-qndn, epic 8o8e, and it is the
sharpest instance in the whole conversion. `head_red_awaiting_green` chooses
WHICH LEG of the commit ritual runs. Before it went on the railway, a git
that failed produced empty stdout, empty stdout contains no `TDD-Red-*`
trailer, and "no Red trailer" routes to the SUITE-GREEN leg — which then
runs the full suite and stamps `TDD-Suite-Green-*` onto what may well be a
Green amend. Not a fail-closed: a fail-WRONG, writing the wrong evidence
shape into history because a read it never noticed had failed.

`_dispatch_impl_staged` now refuses instead, and this is the arm that proves
the refusal is reached rather than merely written.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
import structlog
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.checks._red_green_replay_trailers import GitCommandFailed

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__: list[str] = []


_SUPERVISOR_PATH = (
    Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "checks" / "red_green_replay.py"
)

# The refusal exit the ritual uses for every rejection.
_REFUSED = 1

_UNREADABLE_HEAD = GitCommandFailed(
    argv="git rev-parse --verify --quiet HEAD", detail="exit 128: fatal: not a git repository"
)

_UNREADABLE_HEAD_MESSAGE = GitCommandFailed(
    argv="git log -1 --format=%B", detail="exit 128: fatal: not a git repository"
)

# What `head_red_awaiting_green` answers at a genuine Green amend — the state
# that elects branch 4 and therefore the state the half-pair guard runs in.
_RED_AWAITING_GREEN = True


@pytest.fixture
def supervisor() -> Iterator[ModuleType]:
    """The supervisor module, loaded standalone the way the hook loads it."""
    spec = importlib.util.spec_from_file_location(
        "red_green_replay_git_failure_edges", _SUPERVISOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("test")


def test_unreadable_head_refuses_rather_than_taking_the_suite_green_leg(
    *, tmp_path: Path, supervisor: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """⛔ THE FAIL-WRONG THE CONVERSION REMOVES, asserted at the routing seam.

    Both legs are stubbed to record their invocation, so the test can assert
    the ONE thing that matters: with HEAD unreadable, NEITHER leg runs. An
    assertion on the exit code alone would pass even if the suite-green leg
    had run and happened to reject.
    """
    legs: list[str] = []
    supervisor.head_red_awaiting_green = lambda: IOFailure(_UNREADABLE_HEAD)
    supervisor._handle_green_mode = lambda **_kwargs: legs.append("green") or 0  # noqa: SLF001
    supervisor._handle_suite_green_mode = lambda **_kwargs: legs.append("suite") or 0  # noqa: SLF001

    rc = supervisor._dispatch_impl_staged(  # noqa: SLF001
        msg_path=tmp_path / "COMMIT_EDITMSG",
        log=_logger(),
        impl_paths=["livespec/x.py"],
        staged_paths=["livespec/x.py"],
    )

    assert rc == _REFUSED, f"an unreadable HEAD must REFUSE the commit; got {rc}"
    assert legs == [], f"no leg may run when HEAD was never read; ran {legs}"
    stderr = capsys.readouterr().err
    assert '"check_id": "red-green-replay-git-command-failed"' in stderr, stderr
    assert '"argv": "git rev-parse --verify --quiet HEAD"' in stderr, stderr


def test_unread_head_message_refuses_rather_than_admitting_the_green_amend(
    *, tmp_path: Path, supervisor: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """The half-pair guard's own read is on the railway for the same reason.

    `dropped_red_trailers` answers with an EMPTY tuple when the amend kept
    HEAD's Red block — and empty is the ADMITTING answer. Folding a git that
    did not run onto it would wave through exactly the message-replacing
    amend the guard exists to refuse (work-item livespec-dev-tooling-zv78),
    silently, on a read nobody noticed had failed.
    """
    legs: list[str] = []
    supervisor.head_red_awaiting_green = lambda: IOSuccess(_RED_AWAITING_GREEN)
    supervisor.dropped_red_trailers = lambda *, message: IOFailure(  # noqa: ARG005
        _UNREADABLE_HEAD_MESSAGE
    )
    supervisor._handle_green_mode = lambda **_kwargs: legs.append("green") or 0  # noqa: SLF001
    supervisor._handle_suite_green_mode = lambda **_kwargs: legs.append("suite") or 0  # noqa: SLF001
    msg_path = tmp_path / "COMMIT_EDITMSG"
    _ = msg_path.write_text("feat: green impl\n", encoding="utf-8")

    rc = supervisor._dispatch_impl_staged(  # noqa: SLF001
        msg_path=msg_path,
        log=_logger(),
        impl_paths=["livespec/x.py"],
        staged_paths=["livespec/x.py"],
    )

    assert rc == _REFUSED, f"an unread HEAD message must REFUSE the amend; got {rc}"
    assert legs == [], f"no leg may run when the Red block could not be compared; ran {legs}"
    stderr = capsys.readouterr().err
    assert '"check_id": "red-green-replay-git-command-failed"' in stderr, stderr
    assert '"argv": "git log -1 --format=%B"' in stderr, stderr
