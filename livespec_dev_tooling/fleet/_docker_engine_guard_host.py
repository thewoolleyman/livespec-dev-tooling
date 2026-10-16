"""The Docker engine install guard's real host — SOME SEAMS STILL RAISE.

`docker_engine_guard.py`'s command line builds its `HostOps` from
`build_real_host` here, so the real host actions land in this module
without reopening the guard module. Child 3a supplied the snapshot, the
firewall footprint, unit and job control, the effective-condition check,
the postcondition read and the dead-man recipe; child 4 adds the
PREFLIGHT (the subnet-overlap refusals, the docker-group read and the
resync refusal) and the observation `sample`; child 5 adds the clock
and boot identity, the runtime directory's ownership and the start
permission, the admission reads, the unit start, the post-commit
enable and the reconfigure seams. The seams that still raise, each
saying so where it stands, are the rollback phase child child 2
added, and child 3b's package step.

TWO METHODS HERE ARE NOT `HostOps` SEAMS, and that is deliberate.
`preflight_refusals` and `record_preflight` run BEFORE `reserve`, which
is before any run exists for the dispatch table to admit an operation
on — so they are the role's own reads of this machine rather than steps
of the lifecycle. They live on the real host anyway, because they are
host state and nothing else, and the role has one place to ask this
machine anything.

This module is deliberately THIN. Every action it exposes is one line of
delegation to a cohesive sibling — the firewall actions, the unit
actions, the condition reads, the kernel network state, the postcondition
record, the preflight and the probe set — because `HostOps` is a WIDE
protocol and a host that also held the work would be one file holding
eight unrelated concerns.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions", "Preflight" and
"Probes". Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._docker_engine_guard_clock import (
    monotonic_seconds,
    read_boot_id,
    wait_seconds,
)
from livespec_dev_tooling.fleet._docker_engine_guard_conditions import condition_check_passed
from livespec_dev_tooling.fleet._docker_engine_guard_daemon import (
    DAEMON_CONFIG,
    PENDING_RESTART_MARKER,
    record_pending_drained_restart,
    write_daemon_keys,
)
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
from livespec_dev_tooling.fleet._docker_engine_guard_permission import (
    grant_start_permission,
    revoke_start_permission,
    set_owner_root,
)
from livespec_dev_tooling.fleet._docker_engine_guard_postconditions import read_postconditions
from livespec_dev_tooling.fleet._docker_engine_guard_preflight import (
    docker_group_accounts,
    preflight_refusals,
)
from livespec_dev_tooling.fleet._docker_engine_guard_probe_set import record_preflight, take_sample
from livespec_dev_tooling.fleet._docker_engine_guard_resync import K3S_CONFIG, K3S_CONFIG_DROPINS
from livespec_dev_tooling.fleet._docker_engine_guard_runner import run_command
from livespec_dev_tooling.fleet._docker_engine_guard_unit_state import (
    deadman_timer_active,
    deadman_timer_exists,
    guard_unit_states,
    invoking_unit,
    unit_enabled_states,
)
from livespec_dev_tooling.fleet._docker_engine_guard_units import (
    cancel_jobs,
    disable_units,
    enable_units,
    kill_cgroup,
    read_queued_jobs,
    start_unit,
    stop_unit,
    systemd_run,
)
from livespec_dev_tooling.fleet._docker_engine_guard_witness import CONTAINERD_PATHS, PROC_ROOT

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_hostops import QueuedJob
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

    # The two locations this host reads from the filesystem rather than
    # through the runner: `/proc`, where the k3s witness and the
    # canary's cgroup are read, and the paths k3s's containerd shims
    # keep their state in. Fields with the REAL defaults, so the whole
    # sample -- not a stand-in for it -- is drivable against a recorded
    # tree, exactly as the runner makes every command drivable.
    proc_root: Path = PROC_ROOT
    containerd_paths: Sequence[Path] = CONTAINERD_PATHS

    # The two locations the RECONFIGURE seams write, both shared with
    # the `docker_sandbox_slice` Ansible role. Fields with the real
    # defaults for the same reason the two above are: a write that
    # cannot be redirected is a write no test can assert without
    # reconfiguring the machine it runs on.
    daemon_config: Path = DAEMON_CONFIG
    restart_marker: Path = PENDING_RESTART_MARKER

    # --- clock, boot identity and the guard's own runtime directory ---

    def monotonic(self) -> float:
        """CLOCK_MONOTONIC seconds, the clock a deadline is recorded against."""
        return monotonic_seconds()

    def boot_id(self) -> str:
        """This boot's id, carried with every recorded deadline."""
        return read_boot_id(proc_root=self.proc_root)

    def sleep(self, *, seconds: float) -> None:
        """The bounded wait the lock acquisition uses."""
        wait_seconds(seconds=seconds)

    def set_owner_root(self, *, path: Path) -> None:
        """Make the runtime directory root-owned."""
        set_owner_root(runner=self.runner, path=path)

    # --- admission reads (design I1) ---

    def guard_unit_states(self) -> Mapping[str, str]:
        """Every guard unit mapped to its `ActiveState`."""
        return guard_unit_states(runner=self.runner)

    def queued_jobs(self) -> tuple[QueuedJob, ...]:
        """The whole job queue, as both admission and cancellation read it."""
        return read_queued_jobs(runner=self.runner)

    def invoking_unit(self) -> str:
        """This invocation's own transient unit."""
        return invoking_unit(proc_root=self.proc_root)

    def docker_group_members(self) -> tuple[str, ...]:
        """Every account the `docker` group admits, by either kind of membership."""
        return docker_group_accounts(runner=self.runner)

    # --- preflight (design F7) ---

    def preflight_refusals(
        self,
        *,
        declared: Mapping[str, str],
        config: Path = K3S_CONFIG,
        dropins: Path = K3S_CONFIG_DROPINS,
    ) -> tuple[str, ...]:
        """Every reason this host may not reserve a run, read before `reserve`.

        Not a `HostOps` seam: the specification puts the preflight
        BEFORE `reserve`, so it is the role's own read rather than a
        step of an operation the dispatch table admits. It lives on the
        real host all the same, because it is host state and nothing
        else, and the role has one place to ask this machine anything.
        """
        return preflight_refusals(
            runner=self.runner, declared=declared, config=config, dropins=dropins
        )

    # --- publish ---

    def take_snapshot(self, *, destination: Path) -> None:
        """Both families' tables, both FORWARD policies, the five watched sysctls."""
        write_firewall_snapshot(destination=destination, runner=self.runner)
        write_sysctl_snapshot(destination=destination, runner=self.runner)

    def record_preflight(self, *, destination: Path) -> None:
        """Record k3s's containerd and this host's interfaces beside the snapshot.

        Not a `HostOps` seam for the same reason the preflight reads
        are not: the specification takes these records at the
        preflight, before any guarded operation, so the role takes
        them rather than an operation the dispatch table admits.
        """
        record_preflight(destination=destination, runner=self.runner, proc_root=self.proc_root)

    def install_packages(self, *, inputs: Path) -> None:
        """CHILD 3b: the fenced, audited package transaction."""
        raise NotImplementedError

    def condition_check_passed(self) -> bool:
        """Each guarded unit's EFFECTIVE conditions, read from the service manager."""
        return condition_check_passed(runner=self.runner, paths=self.paths)

    # --- arm ---

    def deadman_timer_exists(self, *, run: str) -> bool:
        """Whether this run's dead-man timer unit is already loaded."""
        return deadman_timer_exists(runner=self.runner, run=run)

    def deadman_timer_active(self, *, run: str) -> bool:
        """Whether it is active, which `start` refuses without."""
        return deadman_timer_active(runner=self.runner, run=run)

    def systemd_run(self, *, argv: Sequence[str]) -> None:
        """Run a `systemd-run` argv the guard built, such as the dead-man recipe."""
        systemd_run(runner=self.runner, argv=argv)

    # --- start ---

    def grant_start_permission(self) -> None:
        """Create the start permission the guarded units' condition reads."""
        grant_start_permission(paths=self.paths)

    def start_unit(self, *, unit: str, timeout_seconds: int) -> None:
        """Start one guarded unit with a bounded wait."""
        start_unit(runner=self.runner, unit=unit, timeout_seconds=timeout_seconds)

    # --- observe (child 1b, probes from child 4) ---

    def sample(self) -> Mapping[str, object]:
        """One observation sample: every probe and the k3s witness, as one record."""
        return take_sample(
            runner=self.runner,
            paths=self.paths,
            proc_root=self.proc_root,
            containerd_paths=self.containerd_paths,
        )

    # --- confirm's post-commit steps (child 1b) ---

    def enable_units(self, *, units: Sequence[str]) -> None:
        """Enable the guarded units, carrying Docker across the next boot."""
        enable_units(runner=self.runner, units=units)

    def unit_enabled_states(self) -> Mapping[str, str]:
        """Every guard-relevant unit mapped to its `UnitFileState`."""
        return unit_enabled_states(runner=self.runner)

    # --- reconfigure (child 1b) ---

    def write_daemon_keys(self, *, keys: Mapping[str, object]) -> None:
        """Write the role-owned daemon keys, leaving every other key alone."""
        write_daemon_keys(keys=keys, config=self.daemon_config)

    def record_pending_drained_restart(self, *, unit: str) -> None:
        """Record that `unit` needs a drained restart, restarting nothing."""
        record_pending_drained_restart(unit=unit, marker=self.restart_marker)

    # --- rollback phases ---

    def revoke_start_permission(self) -> None:
        """Remove the start permission. The first act of any rollback."""
        revoke_start_permission(paths=self.paths)

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
        return read_postconditions(runner=self.runner, paths=self.paths, snapshot=snapshot)

    def run_phase_child(self, *, argv: Sequence[str]) -> bool:
        """CHILD 4: run one rollback phase as its own child; whether it completed."""
        raise NotImplementedError


def build_real_host(
    *,
    paths: GuardPaths,
    runner: GuardCommandRunner = run_command,
    proc_root: Path = PROC_ROOT,
    containerd_paths: Sequence[Path] = CONTAINERD_PATHS,
    daemon_config: Path = DAEMON_CONFIG,
    restart_marker: Path = PENDING_RESTART_MARKER,
) -> RealHost:
    """The `HostOps` that actually touches this host, rooted at `paths`.

    Answers `RealHost` rather than `HostOps`: the preflight reads and
    the preflight record are host state the ROLE asks for before any
    operation exists, so they are not seams of the protocol the
    lifecycle runs against — and a caller handed the protocol could not
    reach them.
    """
    return RealHost(
        paths=paths,
        runner=runner,
        proc_root=proc_root,
        containerd_paths=containerd_paths,
        daemon_config=daemon_config,
        restart_marker=restart_marker,
    )
