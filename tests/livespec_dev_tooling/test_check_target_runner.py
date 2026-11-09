"""The one runner every check-target caller launches through.

Work-item livespec-dev-tooling-oqpw6t: the normal aggregate, the expedited
local hooks and the expedited CI entrance share these process semantics, so
each rule is pinned here once rather than per caller.
"""

from __future__ import annotations

import os
import select
import signal
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from livespec_dev_tooling import _check_target_runner as runner
from livespec_dev_tooling._check_target_runner import (
    BLOCKED,
    COMPLETED,
    LAUNCH_FAILED,
    NOT_ADMITTED,
    NOT_LAUNCHED,
    TIMED_OUT,
    TargetOutcome,
    TargetRun,
    run_targets,
)

__all__: list[str] = []


def _sh(*, name: str, script: str, after: str | None = None) -> TargetRun:
    return TargetRun(name=name, argv=("/bin/sh", "-c", script), after=after)


@contextmanager
def _lifetime(*, tmp_path: Path) -> Iterator[tuple[Path, int]]:
    """A FIFO whose reader sees EOF only once every holder of its writer is dead."""
    fifo = tmp_path / "lifetime.fifo"
    os.mkfifo(fifo)
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        yield fifo, reader
    finally:
        os.close(reader)


def _holders_dead(*, reader: int) -> bool:
    ready, _, _ = select.select([reader], [], [], 5)
    return ready == [reader] and os.read(reader, 1) == b""


# A target that holds the FIFO writer open in a TERM-ignoring background child,
# then marks itself ready; `_AFTER_READY` ends only once that mark exists, so an
# interruption on its completion always finds the holder running.
_HOLD = 'exec 3> "{fifo}"; trap "" TERM; sleep 30 & touch ready; wait'
_AFTER_READY = "while [ ! -e ready ]; do sleep 0.05; done"


def test_outcomes_keep_run_order_status_output_and_stdin_closed(tmp_path: Path) -> None:
    seen: list[str] = []
    outcomes = run_targets(
        runs=[
            _sh(name="slow", script="sleep 0.3; echo slow-out; exit 3"),
            _sh(name="fast", script="cat; echo fast-out >&2"),
        ],
        cwd=tmp_path,
        max_workers=2,
        on_complete=lambda outcome: seen.append(outcome.name),
    )
    assert [(o.name, o.status, o.returncode) for o in outcomes] == [
        ("slow", COMPLETED, 3),
        ("fast", COMPLETED, 0),
    ]
    assert outcomes[0].output == "slow-out\n"
    assert outcomes[1].output == "fast-out\n"
    assert seen == ["fast", "slow"]
    assert all(o.wall_time_s > 0 for o in outcomes)


def test_environment_replaces_or_inherits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNNER_TEST_INHERITED", "inherited")
    script = 'echo "${RUNNER_TEST_INHERITED:-absent} ${RUNNER_TEST_GIVEN:-absent}"'
    outcomes = run_targets(
        runs=[
            _sh(name="inherit", script=script),
            TargetRun(
                name="replace",
                argv=("/bin/sh", "-c", script),
                env={"PATH": os.environ["PATH"], "RUNNER_TEST_GIVEN": "given"},
            ),
        ],
        cwd=tmp_path,
        max_workers=2,
    )
    assert [o.output for o in outcomes] == ["inherited absent\n", "absent given\n"]


def test_missing_and_empty_commands_fail_with_127(tmp_path: Path) -> None:
    outcomes = run_targets(
        runs=[
            TargetRun(name="missing", argv=(str(tmp_path / "missing"),)),
            TargetRun(name="empty", argv=()),
        ],
        cwd=tmp_path,
        max_workers=2,
    )
    assert [(o.status, o.returncode) for o in outcomes] == [
        (LAUNCH_FAILED, 127),
        (LAUNCH_FAILED, 127),
    ]
    assert "missing" in outcomes[0].output
    assert outcomes[1].output == "empty target command"


def test_deadline_kills_the_whole_group_and_reports_no_return_code(tmp_path: Path) -> None:
    with _lifetime(tmp_path=tmp_path) as (fifo, reader):
        (outcome,) = run_targets(
            runs=[_sh(name="slow", script=_HOLD.format(fifo=fifo))],
            cwd=tmp_path,
            max_workers=1,
            deadline_seconds=2.0,
        )
        assert (outcome.status, outcome.returncode) == (TIMED_OUT, None)
        assert _holders_dead(reader=reader)


def test_a_finished_target_leaves_no_descendant_behind(tmp_path: Path) -> None:
    with _lifetime(tmp_path=tmp_path) as (fifo, reader):
        (outcome,) = run_targets(
            runs=[_sh(name="leaker", script=f'exec 3> "{fifo}"; sleep 30 & exit 0')],
            cwd=tmp_path,
            max_workers=1,
        )
        assert (outcome.status, outcome.returncode) == (COMPLETED, 0)
        assert _holders_dead(reader=reader)


def test_a_consumer_waits_for_its_producer_and_is_blocked_when_it_fails(tmp_path: Path) -> None:
    order = tmp_path / "order"
    outcomes = run_targets(
        runs=[
            _sh(name="producer", script=f"sleep 0.3; echo producer >> {order}"),
            _sh(name="consumer", script=f"echo consumer >> {order}", after="producer"),
            _sh(name="broken", script="exit 4"),
            _sh(name="blocked", script=f"echo blocked >> {order}", after="broken"),
            _sh(name="unknown-producer", script="true", after="later"),
            _sh(name="later", script="true"),
        ],
        cwd=tmp_path,
        max_workers=4,
    )
    assert order.read_text().splitlines() == ["producer", "consumer"]
    blocked = outcomes[3]
    assert (blocked.status, blocked.returncode) == (BLOCKED, None)
    assert blocked.output == "BLOCKED: prereq 'broken' failed (exit 4)"
    assert outcomes[4].status == COMPLETED


def test_a_refused_admission_stops_later_launches_but_not_running_targets(tmp_path: Path) -> None:
    answers = iter([True, False, True])
    asked: list[bool] = []

    def admit() -> bool:
        asked.append(next(answers))
        return asked[-1]

    outcomes = run_targets(
        runs=[
            _sh(name="admitted", script="echo ran"),
            _sh(name="refused", script="echo never"),
            _sh(name="after-refusal", script="echo never"),
        ],
        cwd=tmp_path,
        max_workers=1,
        admit=admit,
    )
    assert asked == [True, False, True]
    assert [(o.status, o.output) for o in outcomes] == [
        (COMPLETED, "ran\n"),
        (NOT_ADMITTED, ""),
        (NOT_LAUNCHED, ""),
    ]


def test_an_interrupted_caller_kills_every_live_group(tmp_path: Path) -> None:
    def interrupt(_outcome: TargetOutcome) -> None:
        raise KeyboardInterrupt

    with _lifetime(tmp_path=tmp_path) as (fifo, reader):
        with pytest.raises(KeyboardInterrupt):
            _ = run_targets(
                runs=[
                    _sh(name="held", script=_HOLD.format(fifo=fifo)),
                    _sh(name="quick", script=_AFTER_READY),
                ],
                cwd=tmp_path,
                max_workers=2,
                on_complete=interrupt,
            )
        assert _holders_dead(reader=reader)


def test_sigterm_while_waiting_raises_kills_groups_and_restores_handlers(tmp_path: Path) -> None:
    assert threading.current_thread() is threading.main_thread()
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}

    def terminate(_outcome: TargetOutcome) -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    with _lifetime(tmp_path=tmp_path) as (fifo, reader):
        with pytest.raises(SystemExit) as raised:
            _ = run_targets(
                runs=[
                    _sh(name="held", script=_HOLD.format(fifo=fifo)),
                    _sh(name="quick", script=_AFTER_READY),
                ],
                cwd=tmp_path,
                max_workers=2,
                on_complete=terminate,
            )
        assert raised.value.code == 128 + signal.SIGTERM
        assert _holders_dead(reader=reader)
    assert {sig: signal.getsignal(sig) for sig in before} == before


def test_off_the_main_thread_the_callers_signal_handling_stands(tmp_path: Path) -> None:
    seen: list[object] = []

    def run() -> None:
        with runner._termination_raises():  # noqa: SLF001
            seen.append(signal.getsignal(signal.SIGTERM))
        seen.extend(
            o.status
            for o in run_targets(runs=[_sh(name="t", script="true")], cwd=tmp_path, max_workers=1)
        )

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    assert seen == [signal.getsignal(signal.SIGTERM), COMPLETED]
