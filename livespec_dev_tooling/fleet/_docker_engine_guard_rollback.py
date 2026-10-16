"""The Docker engine install guard's rollback driver — CHILD 2 REPLACES THIS FILE.

`docker_engine_guard.py` reaches `run_rollback` here once its dispatch
table has decided that a rollback may proceed, so child 2 implements the
driver without reopening the guard module: the phase children under
`timeout -k 10`, the three-attempt skip, the final all-postconditions
check, and the `rolled-back` / `rollback-partial` outcome.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback". Child 1a ships the
decision that reaches this entry and nothing past it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import Decision, GuardOutcome
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "run_rollback",
]


def run_rollback(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Run every rollback phase for `run` and record its outcome.

    `decision` is the table's, already made under the lock: reaching here
    means the run is uncommitted and its phase admits a rollback.
    """
    raise NotImplementedError
