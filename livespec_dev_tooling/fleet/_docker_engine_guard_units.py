"""Unit and job control, scoped so it can never reach k3s.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions" -- job
cancellation, the cgroup kill, disable -- and "Rollback", whose ordering
these actions implement. Governing design:
`docs/docker-engine-guard-design.md` R4 and H2, and rider point 1.

EVERY ACTION HERE IS NARROWED TO A FIXED SET. The guarded units and the
sandbox slice are named as constants and each action intersects its
argument with them, so a caller that passed `k3s-agent.service` -- by
defect, by a mis-parsed read, or by a future refactor -- would still not
stop it. That narrowing is the single most load-bearing property of this
module: the lockout the whole guard exists to prevent is a stopped k3s
agent on a machine reachable only over Tailscale, and `systemctl` offers
no undo.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_hostops import QueuedJob
from livespec_dev_tooling.fleet._docker_engine_guard_model import GUARDED_UNITS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "LIST_JOBS_ARGV",
    "SYSTEMCTL",
    "UNIT_ACTION_TIMEOUT_SECONDS",
    "UNIT_READ_TIMEOUT_SECONDS",
    "cancel_jobs",
    "guarded_job_ids",
    "read_queued_jobs",
]

SYSTEMCTL: Final[str] = "systemctl"

# `--no-legend` drops the header and `--no-pager` keeps the answer on
# stdout; neither suppresses the trailing "N jobs listed." line, which is
# why the parse below requires a job's exact four columns.
LIST_JOBS_ARGV: Final[tuple[str, ...]] = (SYSTEMCTL, "list-jobs", "--no-legend", "--no-pager")

# A read asks the service manager a question it answers from memory, so
# the bound is short. An action waits on a job, so it gets the same
# minute the lifecycle gives a unit start.
UNIT_READ_TIMEOUT_SECONDS: Final[int] = 15
UNIT_ACTION_TIMEOUT_SECONDS: Final[int] = 60

# A `list-jobs` row's exact column count: JOB, UNIT, TYPE, STATE.
_JOB_COLUMNS: Final[int] = 4


def read_queued_jobs(*, runner: GuardCommandRunner) -> tuple[QueuedJob, ...]:
    """Every queued job, as `systemctl list-jobs` reports it.

    A job row is exactly four whitespace-separated columns (JOB, UNIT,
    TYPE, STATE) whose first is the numeric id. Requiring all four is
    what keeps the footer out: `4 jobs listed.` has three columns and a
    first one that is numeric, so a laxer parse would invent a queued job
    called `jobs`.
    """
    answer = runner(argv=LIST_JOBS_ARGV, timeout_seconds=UNIT_READ_TIMEOUT_SECONDS)
    jobs: list[QueuedJob] = []
    for raw in answer.stdout.splitlines():
        fields = raw.split()
        if len(fields) == _JOB_COLUMNS and fields[0].isdigit():
            jobs.append(QueuedJob(job_id=fields[0], unit=fields[1]))
    return tuple(jobs)


def guarded_job_ids(*, jobs: Sequence[QueuedJob], job_ids: Sequence[str]) -> tuple[str, ...]:
    """The ids among `job_ids` that the queue holds for a GUARDED unit.

    Both filters are deliberate. The caller's set says which jobs it
    means; the guarded-unit set says which ones may be touched at all,
    and it wins -- a cancellation is one of the two actions on this host
    that can stop the k3s agent, and the other is the kill below.
    """
    wanted = set(job_ids)
    return tuple(job.job_id for job in jobs if job.unit in GUARDED_UNITS and job.job_id in wanted)


def cancel_jobs(*, runner: GuardCommandRunner, job_ids: Sequence[str]) -> None:
    """`systemctl cancel` with those ids, or no command at all.

    A BARE `systemctl cancel` cancels the whole queue, which on this host
    includes `k3s-agent.service`. So an empty selection issues nothing:
    there is no such thing as a harmless default here.
    """
    selected = guarded_job_ids(jobs=read_queued_jobs(runner=runner), job_ids=job_ids)
    if selected:
        _ = runner(
            argv=(SYSTEMCTL, "cancel", *selected),
            timeout_seconds=UNIT_ACTION_TIMEOUT_SECONDS,
        )
