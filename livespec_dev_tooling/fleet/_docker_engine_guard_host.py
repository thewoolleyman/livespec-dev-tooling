"""The Docker engine install guard's real host — CHILD 4 STILL OWNS THE REST.

`docker_engine_guard.py`'s command line builds its `HostOps` from
`build_real_host` here, so the real host actions land in this module
without reopening the guard module. Child 3a supplies the ones its
Definition of Done names: the snapshot, the firewall footprint, unit and
job control, the effective-condition check, the postcondition read and
the dead-man recipe. The remaining seams — the clock and boot identity,
the admission reads, the start permission, the observation `sample`, the
preflight's docker-group read, and child 3b's package step — still raise,
each saying so where it stands.

This module is deliberately THIN. Every action it exposes is one line of
delegation to a cohesive sibling — the firewall actions, the unit
actions, the condition reads, the kernel network state, the postcondition
record — because `HostOps` is a WIDE protocol and a host that also held
the work would be one file holding six unrelated concerns.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions" and "Preflight".
Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._docker_engine_guard_firewall_actions import (
    remove_footprint,
    restore_forward_policy,
    write_firewall_snapshot,
)
from livespec_dev_tooling.fleet._docker_engine_guard_netstate import (
    compare_sysctls,
    delete_bridge_interfaces,
    write_sysctl_snapshot,
)
from livespec_dev_tooling.fleet._docker_engine_guard_runner import run_command
from livespec_dev_tooling.fleet._docker_engine_guard_units import (
    cancel_jobs,
    disable_units,
    kill_cgroup,
    read_queued_jobs,
    stop_unit,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_hostops import HostOps, QueuedJob
    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "RealHost",
    "build_real_host",
]


@dataclass(frozen=True, kw_only=True)
class RealHost:
    """Every `HostOps` seam, against this machine, through one timed runner.

    The runner is a FIELD rather than a module-level call so the whole
    host layer is drivable from recorded command output: that is how an
    action which deletes firewall rules and SIGKILLs cgroups is asserted
    on at all.
    """

    paths: GuardPaths
    runner: GuardCommandRunner

    # --- clock, boot identity and the guard's own runtime directory ---

    def monotonic(self) -> float:
        """CHILD 4: CLOCK_MONOTONIC seconds, the clock a deadline is recorded against."""
        raise NotImplementedError

    def boot_id(self) -> str:
        """CHILD 4: this boot's id, carried with every recorded deadline."""
        raise NotImplementedError

    def sleep(self, *, seconds: float) -> None:
        """CHILD 4: the bounded wait the lock acquisition uses."""
        raise NotImplementedError

    def set_owner_root(self, *, path: Path) -> None:
        """CHILD 4: make the runtime directory root-owned."""
        raise NotImplementedError

    # --- admission reads (design I1) ---

    def guard_unit_states(self) -> Mapping[str, str]:
        """CHILD 4: every guard unit mapped to its `ActiveState`."""
        raise NotImplementedError

    def queued_jobs(self) -> tuple[QueuedJob, ...]:
        """The whole job queue, as both admission and cancellation read it."""
        return read_queued_jobs(runner=self.runner)

    def invoking_unit(self) -> str:
        """CHILD 4: this invocation's own transient unit."""
        raise NotImplementedError

    def docker_group_members(self) -> tuple[str, ...]:
        """CHILD 4: the preflight's docker-group read."""
        raise NotImplementedError

    # --- publish ---

    def take_snapshot(self, *, destination: Path) -> None:
        """Both families' tables, both FORWARD policies, the five watched sysctls."""
        write_firewall_snapshot(destination=destination, runner=self.runner)
        write_sysctl_snapshot(destination=destination, runner=self.runner)

    def install_packages(self, *, inputs: Path) -> None:
        """CHILD 3b: the fenced, audited package transaction."""
        raise NotImplementedError

    def condition_check_passed(self) -> bool:
        """Each guarded unit's EFFECTIVE conditions, read from the service manager."""
        raise NotImplementedError

    # --- arm ---

    def deadman_timer_exists(self, *, run: str) -> bool:
        """CHILD 4: whether this run's dead-man timer unit is already loaded."""
        raise NotImplementedError

    def deadman_timer_active(self, *, run: str) -> bool:
        """CHILD 4: whether it is active, which `start` refuses without."""
        raise NotImplementedError

    def systemd_run(self, *, argv: Sequence[str]) -> None:
        """Run a `systemd-run` argv the guard built, such as the dead-man recipe."""
        raise NotImplementedError

    # --- start ---

    def grant_start_permission(self) -> None:
        """CHILD 4: create the start permission the guarded units' condition reads."""
        raise NotImplementedError

    def start_unit(self, *, unit: str, timeout_seconds: int) -> None:
        """CHILD 4: start one guarded unit with a bounded wait."""
        raise NotImplementedError

    # --- observe (child 1b, probes from child 4) ---

    def sample(self) -> Mapping[str, object]:
        """CHILD 4: one observation sample, the probes and the k3s witness."""
        raise NotImplementedError

    # --- rollback phases ---

    def revoke_start_permission(self) -> None:
        """CHILD 4: remove the start permission. The first act of any rollback."""
        raise NotImplementedError

    def stop_unit(self, *, unit: str, timeout_seconds: int) -> None:
        """Stop one unit with a bounded wait."""
        stop_unit(runner=self.runner, unit=unit, timeout_seconds=timeout_seconds)

    def cancel_jobs(self, *, job_ids: Sequence[str]) -> None:
        """Cancel exactly the guarded units' queued jobs, by id."""
        cancel_jobs(runner=self.runner, job_ids=job_ids)

    def restore_forward_policy(self, *, snapshot: Path) -> None:
        """One `-P FORWARD` per family, with the policy the snapshot recorded."""
        restore_forward_policy(runner=self.runner, snapshot=snapshot)

    def kill_cgroup(self, *, units: Sequence[str]) -> None:
        """SIGKILL every process in the named cgroups, then stop them."""
        kill_cgroup(runner=self.runner, units=units)

    def disable_units(self, *, units: Sequence[str]) -> None:
        """Disable the three guarded units."""
        disable_units(runner=self.runner, units=units)

    def remove_firewall_footprint(self, *, snapshot: Path) -> tuple[str, ...]:
        """Remove Docker's rule footprint; report every residual Docker rule."""
        return remove_footprint(runner=self.runner, snapshot=snapshot)

    def delete_bridge_interfaces(self) -> tuple[str, ...]:
        """Delete `docker0` and every veth mastered by it; report what went."""
        return delete_bridge_interfaces(runner=self.runner)

    def compare_sysctls(self, *, snapshot: Path) -> tuple[str, ...]:
        """Compare the watched sysctls with the snapshot; report each difference."""
        return compare_sysctls(runner=self.runner, snapshot=snapshot)

    def read_postconditions(self, *, snapshot: Path) -> Mapping[str, bool]:
        """The whole postcondition set read as one record."""
        raise NotImplementedError


def build_real_host(*, paths: GuardPaths, runner: GuardCommandRunner = run_command) -> HostOps:
    """The `HostOps` that actually touches this host, rooted at `paths`."""
    return RealHost(paths=paths, runner=runner)
