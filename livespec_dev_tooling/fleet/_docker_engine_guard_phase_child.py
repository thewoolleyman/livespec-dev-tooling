"""Running ONE rollback phase as its own child process.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback" (this repository).
Governing design: `docs/docker-engine-guard-design.md` — each phase of
a rollback runs in a child under `timeout -k 10 <phase budget>`, so a
phase that hangs or that crashes the guard's own parser costs its own
budget and nothing more.

WHY THE ANSWER IS ONE BOOLEAN. The driver treats a non-zero exit, the
`timeout` expiry and a kill by signal identically: record no success,
enter the next phase. Reporting WHICH of the three happened would
offer the driver a distinction it must not act on, and the dangerous
direction is the other one — a `True` on anything but a clean exit
writes a success record for a phase that never ran, and every later
firing of the dead-man then SKIPS the teardown step that did not
happen.

Stdlib only, Python 3.10 syntax, for the reason
`_docker_engine_guard_model.py` records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_rollback import (
    PHASE_BUDGET_SECONDS,
    PHASE_KILL_AFTER_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "PHASE_CHILD_MARGIN_SECONDS",
    "PHASE_CHILD_TIMEOUT_SECONDS",
    "run_phase_child",
]

# Slack between the fence the child carries and the bound this seam
# puts on the call that spawns it. Thirty seconds, which is a process
# spawn and a `timeout` delivering SIGTERM then SIGKILL, with room.
PHASE_CHILD_MARGIN_SECONDS: Final[int] = 30

# DERIVED from the phase budget table rather than written down beside
# it, so a budget that moves moves this with it. The ordering is the
# load-bearing part: the runner's bound must OUTLIVE the child's own
# `timeout -k 10 <budget>`, because a runner that expired first would
# kill a phase still inside its budget and the driver would read that
# kill as a phase that failed.
PHASE_CHILD_TIMEOUT_SECONDS: Final[int] = (
    max(PHASE_BUDGET_SECONDS.values()) + PHASE_KILL_AFTER_SECONDS + PHASE_CHILD_MARGIN_SECONDS
)


def run_phase_child(*, runner: GuardCommandRunner, argv: Sequence[str]) -> bool:
    """Run `argv` as its own child; answer whether that child COMPLETED.

    The argv is passed THROUGH unaltered, fence and all: the
    `timeout -k 10 <phase budget>` in front of it is the driver's, built
    beside the budget table it derives from, and this seam's only job
    is that it reaches the host bounded like every other command.
    """
    answer = runner(argv=tuple(argv), timeout_seconds=PHASE_CHILD_TIMEOUT_SECONDS)
    return answer.returncode == 0
