"""The Docker engine install guard's rollback driver.

`docker_engine_guard.py` reaches `run_rollback` here once its dispatch
table has decided that a rollback may proceed, so the driver lives beside
the guard rather than inside it.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback" (this repository).
Governing design: `docs/docker-engine-guard-design.md` — F1's rollback,
R4's ordering, G5, H2's stop-first rule and H6's bounds.

Stdlib only, for the reason the model module records: these files are
copied onto the guarded host and run against its bare interpreter, so an
expected refusal is RETURNED in a `GuardOutcome` rather than raised.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardOutcome
from livespec_dev_tooling.fleet._docker_engine_guard_state import read_phase, record_phase

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import Decision, Phase
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "run_rollback",
]

# The phases a run is already ON the rollback path in. A firing that
# arrives on one of them records nothing: the dead-man re-fires every 60
# seconds, so most firings land here, and re-recording `rolling-back`
# over a `rollback-partial` would erase the one record an operator reads
# while deciding whether the host needs a repair.
_ROLLBACK_PATH_PHASES: Final[tuple[Phase, ...]] = ("rolling-back", "rollback-partial")

# The two guard units that can still write to the Docker daemon when a
# rollback begins: the observer, which may hold an API request, and the
# starter, which may be mid-start. Both are fixed unit names (design I3),
# so the service manager refuses a second activation of either.
GUARD_OBSERVE_UNIT: Final[str] = "docker-engine-guard-observe.service"
GUARD_START_UNIT: Final[str] = "docker-engine-guard-start.service"

# How long each fenced unit gets between its SIGTERM and its SIGKILL.
FENCE_KILL_SECONDS: Final[int] = 10


def _fence_and_revoke(*, env: GuardEnv) -> None:
    """Stop both writers, then take the start permission back.

    The ORDER is the content of this step. Revoking first would leave a
    window in which an observer that has been told to stop, but is not
    yet inactive, submits one more Docker request against a daemon the
    revocation was meant to close; a `systemctl stop` returns only once
    the unit is inactive, so stopping first is what closes it. The
    revocation itself is what makes `Restart=always` unable to respawn
    the daemon, which is why nothing else may precede it either.
    """
    env.host.stop_unit(unit=GUARD_OBSERVE_UNIT, timeout_seconds=FENCE_KILL_SECONDS)
    env.host.stop_unit(unit=GUARD_START_UNIT, timeout_seconds=FENCE_KILL_SECONDS)
    env.host.revoke_start_permission()


def run_rollback(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Run every rollback phase for `run` and record its outcome.

    `decision` is the table's, already made under the lock: reaching here
    means the run is uncommitted and its phase admits a rollback.

    The phase record comes FIRST, before any other step. It is what
    closes the forward path — `start` and `confirm` are each allowed only
    from a phase this run no longer has — so recording it first is what
    makes a driver killed immediately afterwards leave a run nothing can
    carry forward, rather than one that was acted on and still looks
    startable. A run already on the rollback path keeps the phase it
    arrived with until this firing writes an outcome.
    """
    if read_phase(paths=env.paths, run=run) not in _ROLLBACK_PATH_PHASES:
        record_phase(paths=env.paths, run=run, phase="rolling-back")
    _fence_and_revoke(env=env)
    return GuardOutcome(
        operation="rollback",
        run=run,
        verdict=decision.verdict,
        reason="the run is on the rollback path",
    )
