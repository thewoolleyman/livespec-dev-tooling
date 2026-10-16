"""The one seam between the Docker engine install guard and its host.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" (this repository), which requires
every external command the guard runs to go through one runner with an
explicit timeout. This protocol IS that boundary: nothing above it calls
`subprocess`, reads `/proc`, or touches a unit, so the whole lifecycle is
decided in-process against `FakeHost` and no test can reach a real host.

The protocol declares EVERY seam the six guard children need, not only
1a's. `sample` belongs to 1b's observer and the rollback-phase methods
belong to child 2's driver; they are declared here, now, so that no
sibling has to reopen this module or `docker_engine_guard.py` to add one.
Child 3a supplies the real implementation in
`_docker_engine_guard_host.py`; 1a ships no real host action at all.

Documentation rides in comments rather than per-method docstrings on
purpose: a protocol method needs an `...` body for its declared return
type to typecheck, and an `...` on its own line below a docstring is a
statement no caller ever executes — an unreachable line in a tree held to
100% per-file coverage. A comment costs neither.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "HostOps",
    "QueuedJob",
]


@dataclass(frozen=True, kw_only=True)
class QueuedJob:
    """One row of `systemctl list-jobs`: the job id and the unit it is for.

    The id is carried because job cancellation must issue `systemctl cancel`
    with the job ids of the guarded units' queued jobs, and never a bare
    `systemctl cancel`, which would cancel the whole queue.
    """

    job_id: str
    unit: str


class HostOps(Protocol):
    """Every host fact the guard reads and every host action it takes."""

    # --- clock, boot identity and the guard's own runtime directory ---

    # CLOCK_MONOTONIC seconds. The deadline is recorded against this clock
    # and a boot id, never against the wall clock.
    def monotonic(self) -> float: ...

    # The current boot id. A deadline recorded under a different one has
    # passed, whatever the monotonic instant says.
    def boot_id(self) -> str: ...

    # Bounded wait, used only while waiting for the lock.
    def sleep(self, *, seconds: float) -> None: ...

    # Make `path` root-owned. The runtime directory must be mode 0700 and
    # owned by root; the mode is set in-process, the ownership here.
    def set_owner_root(self, *, path: Path) -> None: ...

    # --- admission reads (design I1) ---

    # Every guard unit mapped to its `ActiveState`. A unit in `failed` is
    # not `inactive`, and admission must name it.
    def guard_unit_states(self) -> Mapping[str, str]: ...

    # Every queued job, so admission can require none for a guard unit and
    # child 2's driver can cancel exactly the guarded units' jobs.
    def queued_jobs(self) -> tuple[QueuedJob, ...]: ...

    # This invocation's own transient unit, excluded from every admission
    # check because it is necessarily active while it runs.
    def invoking_unit(self) -> str: ...

    # Accounts with `docker` as primary or supplementary group. Read before
    # `reserve`, and again by `arm` once the install has created the group.
    def docker_group_members(self) -> tuple[str, ...]: ...

    # --- publish ---

    # Write the host snapshot (both families' rules without counters, each
    # FORWARD policy, the five watched sysctls) into `destination`.
    def take_snapshot(self, *, destination: Path) -> None: ...

    # The fenced, audited package transaction, inert by the start condition.
    # Child 3b supplies the step behind it.
    def install_packages(self, *, inputs: Path) -> None: ...

    # The post-install condition check: each guarded unit's effective
    # conditions read from the service manager through `busctl`.
    def condition_check_passed(self) -> bool: ...

    # --- arm ---

    # Whether this run's dead-man timer unit exists, so a retried `arm` does
    # not create a second one.
    def deadman_timer_exists(self, *, run: str) -> bool: ...

    # Whether it is active, which `start` refuses without.
    def deadman_timer_active(self, *, run: str) -> bool: ...

    # Run a `systemd-run` argv the guard built. Used to arm the dead-man and
    # to start a `rollback` as its own transient unit.
    def systemd_run(self, *, argv: Sequence[str]) -> None: ...

    # --- start ---

    # Create the start permission. After this, and only after this, the
    # guarded units' start condition can be met.
    def grant_start_permission(self) -> None: ...

    # Start one guarded unit with a bounded wait.
    def start_unit(self, *, unit: str, timeout_seconds: int) -> None: ...

    # --- observe (child 1b) ---

    # One observation sample: the probes and the k3s witness, as a record.
    def sample(self) -> Mapping[str, object]: ...

    # --- confirm's post-commit steps (child 1b) ---

    # Enable the guarded units. After the commit point Docker is an
    # ordinary enabled service, and enabling is what carries it across the
    # next boot; `start_unit` above is what carries it across THIS one, so
    # the post-commit steps issue both (rider point 9).
    def enable_units(self, *, units: Sequence[str]) -> None: ...

    # Every guard-relevant unit mapped to its `UnitFileState`. Read beside
    # `guard_unit_states` above by the post-commit validation, which needs
    # BOTH: enablement carries the engine across the next boot, the active
    # state says it is running now, and neither implies the other.
    def unit_enabled_states(self) -> Mapping[str, str]: ...

    # --- reconfigure (child 1b) ---

    # Write the role-OWNED daemon keys into the daemon configuration,
    # leaving every other key in it alone: a key this role does not own
    # belongs to whoever wrote it.
    def write_daemon_keys(self, *, keys: Mapping[str, object]) -> None: ...

    # Record that `unit` needs a DRAINED restart, rather than restarting it.
    # After the commit point the host is running sandbox containers under
    # Docker, so an immediate restart would kill the work the host exists
    # to do; the drain is the fleet's own deferred-restart mechanism.
    def record_pending_drained_restart(self, *, unit: str) -> None: ...

    # --- rollback phases (child 2) ---

    # Remove the start permission. The first act of any rollback.
    def revoke_start_permission(self) -> None: ...

    def stop_unit(self, *, unit: str, timeout_seconds: int) -> None: ...

    def cancel_jobs(self, *, job_ids: Sequence[str]) -> None: ...

    def restore_forward_policy(self, *, snapshot: Path) -> None: ...

    def kill_cgroup(self, *, units: Sequence[str]) -> None: ...

    def disable_units(self, *, units: Sequence[str]) -> None: ...

    # Remove Docker's rule footprint; returns every residual rule.
    def remove_firewall_footprint(self, *, snapshot: Path) -> tuple[str, ...]: ...

    # Delete `docker0` and every veth mastered by it; returns what went.
    def delete_bridge_interfaces(self) -> tuple[str, ...]: ...

    # Compare the watched sysctls with the snapshot; returns each difference.
    def compare_sysctls(self, *, snapshot: Path) -> tuple[str, ...]: ...

    # The whole postcondition set read as one record, after every stop phase.
    def read_postconditions(self, *, snapshot: Path) -> Mapping[str, bool]: ...

    # Run one rollback phase as its own child process, under the command
    # line the driver built (`timeout -k 10 <phase budget> …`), and answer
    # whether that child COMPLETED. `False` covers every way it did not —
    # a non-zero exit, the timeout, a signal — because the driver treats
    # all three identically: record no success and enter the next phase.
    # The phase runs in a child rather than in the driver so that a phase
    # which hangs or crashes the guard's own parser costs its own budget
    # and nothing more.
    def run_phase_child(self, *, argv: Sequence[str]) -> bool: ...
