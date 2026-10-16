"""Running one rollback phase as its own child process.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback" — every step is
attempted whatever the previous one returned. Governing design:
`docs/docker-engine-guard-design.md` F1, whose rollback wraps each step
in its own `timeout`.

WHY A CHILD AT ALL. A phase that hangs, or that crashes the guard's own
parser, costs its own budget and nothing more: the driver stays alive to
run the remaining phases and to write an outcome, which is the one thing
a rollback must always do. A phase run in the driver would take the
driver with it.

THE BOUND THAT MATTERS RIDES IN THE ARGV. The driver builds
`timeout -k 10 <phase budget> …` beside the budget table those numbers
come from, so a budget that moves moves the command with it. The bound
passed to the runner here is the whole ROLLBACK budget — the outermost
one there is — because the guard's one command seam requires an explicit
timeout and a child that outlived the entire rollback is already past
anything the driver could use. The inner `timeout` fires long first on
every phase there is.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import operation_budget_seconds

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "PHASE_CHILD_TIMEOUT_SECONDS",
    "run_phase_child",
]

# Derived from the budget table rather than written down beside it, so a
# rollback budget that moves moves this bound with it. `window_seconds`
# is irrelevant here: only `observe` reads it.
PHASE_CHILD_TIMEOUT_SECONDS: Final[int] = operation_budget_seconds(
    operation="rollback", window_seconds=0
)


def run_phase_child(*, runner: GuardCommandRunner, argv: Sequence[str]) -> bool:
    """Run `argv` as its own child, and answer whether that child COMPLETED.

    True only on an exit of zero. A non-zero exit, an expiry — the
    phase's own `timeout`, or this bound — and a signal all answer
    False, because the driver treats all three identically: record no
    success for the phase and enter the next one. Distinguishing them
    here would offer the driver a choice it does not have.
    """
    answer = runner(argv=tuple(argv), timeout_seconds=PHASE_CHILD_TIMEOUT_SECONDS)
    return answer.returncode == 0
