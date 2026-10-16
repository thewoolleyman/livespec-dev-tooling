"""`FakeHost` — the injectable host the whole Docker engine install guard is tested against.

It implements every seam `HostOps` declares, including 1b's `sample` and
child 2's rollback-phase methods, so each sibling tests against the same
harness and none has to reshape it.

Two properties make it worth more than a bag of stubs. Its clock, boot id
and state roots are INJECTED, so a deadline, a boot change and a lock wait
are all decided without a real clock. And every call is stamped with the
PHASE in force when it arrived — read from the run records on disk, the
same bytes the guard writes — which is how an ordering between a durable
record and a host action ("`start` reaches `started` BEFORE it grants the
start permission") is asserted at all.

It lives in the product tree rather than beside the tests because four
sibling children consume it, and a shared harness that moves with the
protocol it implements cannot drift from it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from livespec_dev_tooling.fleet._docker_engine_guard_hostops import QueuedJob

__all__: list[str] = [
    "FakeCall",
    "FakeHost",
]


@dataclass(frozen=True, kw_only=True)
class FakeCall:
    """One recorded seam call: its name, the phase then in force, its arguments."""

    name: str
    phase: str | None
    detail: tuple[str, ...] = ()


@dataclass(kw_only=True)
class FakeHost:
    """Every `HostOps` seam, answering injected values and recording each call."""

    state_root: Path
    runtime_root: Path
    clock: float = 0.0
    boot: str = "boot-a"
    unit_states: dict[str, str] = field(default_factory=dict)
    unit_file_states: dict[str, str] = field(default_factory=dict)
    jobs: tuple[QueuedJob, ...] = ()
    unit_of_invocation: str = "docker-engine-guard-reserve-run-a-1.service"
    docker_group: tuple[str, ...] = ()
    deadman_units: set[str] = field(default_factory=set)
    active_deadman_units: set[str] = field(default_factory=set)
    condition_check: bool = True
    sample_result: dict[str, object] = field(default_factory=dict)
    firewall_residue: tuple[str, ...] = ()
    deleted_interfaces: tuple[str, ...] = ()
    sysctl_differences: tuple[str, ...] = ()
    postconditions: dict[str, bool] = field(default_factory=dict)
    calls: list[FakeCall] = field(default_factory=list)

    # --- recording ---

    def _phase_now(self) -> str | None:
        """The current reservation's recorded phase, read the way the guard writes it."""
        reservation = self.state_root / "run"
        if not reservation.is_file():
            return None
        run = reservation.read_text(encoding="utf-8").strip()
        phase = self.state_root / "runs" / run / "phase"
        return phase.read_text(encoding="utf-8").strip() if phase.is_file() else None

    def _record(self, *, name: str, detail: tuple[str, ...] = ()) -> None:
        self.calls.append(FakeCall(name=name, phase=self._phase_now(), detail=detail))

    def calls_named(self, *, name: str) -> tuple[FakeCall, ...]:
        """Every recorded call of seam `name`, in order."""
        return tuple(call for call in self.calls if call.name == name)

    # --- clock, boot identity and the runtime directory ---

    def monotonic(self) -> float:
        return self.clock

    def boot_id(self) -> str:
        self._record(name="boot_id")
        return self.boot

    def sleep(self, *, seconds: float) -> None:
        self.clock += seconds

    def set_owner_root(self, *, path: Path) -> None:
        self._record(name="set_owner_root", detail=(str(path),))

    # --- admission reads ---

    def guard_unit_states(self) -> Mapping[str, str]:
        return self.unit_states

    def queued_jobs(self) -> tuple[QueuedJob, ...]:
        self._record(name="queued_jobs")
        return self.jobs

    def invoking_unit(self) -> str:
        return self.unit_of_invocation

    def docker_group_members(self) -> tuple[str, ...]:
        return self.docker_group

    # --- publish ---

    def take_snapshot(self, *, destination: Path) -> None:
        self._record(name="take_snapshot", detail=(str(destination),))
        destination.mkdir(parents=True, exist_ok=True)
        _ = (destination / "iptables-save").write_text("# snapshot\n", encoding="utf-8")

    def install_packages(self, *, inputs: Path) -> None:
        self._record(name="install_packages", detail=(str(inputs),))

    def condition_check_passed(self) -> bool:
        self._record(name="condition_check_passed")
        return self.condition_check

    # --- arm ---

    def deadman_timer_exists(self, *, run: str) -> bool:
        return f"docker-engine-deadman-{run}" in self.deadman_units

    def deadman_timer_active(self, *, run: str) -> bool:
        return f"docker-engine-deadman-{run}" in self.active_deadman_units

    def systemd_run(self, *, argv: Sequence[str]) -> None:
        self._record(name="systemd_run", detail=tuple(argv))

    # --- start ---

    def grant_start_permission(self) -> None:
        self._record(name="grant_start_permission")

    def start_unit(self, *, unit: str, timeout_seconds: int) -> None:
        self._record(name="start_unit", detail=(unit, str(timeout_seconds)))

    # --- observe (child 1b) ---

    def sample(self) -> Mapping[str, object]:
        self._record(name="sample")
        return self.sample_result

    # --- confirm's post-commit steps (child 1b) ---

    def enable_units(self, *, units: Sequence[str]) -> None:
        self._record(name="enable_units", detail=tuple(units))

    def unit_enabled_states(self) -> Mapping[str, str]:
        return self.unit_file_states

    # --- rollback phases (child 2) ---

    def revoke_start_permission(self) -> None:
        self._record(name="revoke_start_permission")

    def stop_unit(self, *, unit: str, timeout_seconds: int) -> None:
        self._record(name="stop_unit", detail=(unit, str(timeout_seconds)))

    def cancel_jobs(self, *, job_ids: Sequence[str]) -> None:
        self._record(name="cancel_jobs", detail=tuple(job_ids))

    def restore_forward_policy(self, *, snapshot: Path) -> None:
        self._record(name="restore_forward_policy", detail=(str(snapshot),))

    def kill_cgroup(self, *, units: Sequence[str]) -> None:
        self._record(name="kill_cgroup", detail=tuple(units))

    def disable_units(self, *, units: Sequence[str]) -> None:
        self._record(name="disable_units", detail=tuple(units))

    def remove_firewall_footprint(self, *, snapshot: Path) -> tuple[str, ...]:
        self._record(name="remove_firewall_footprint", detail=(str(snapshot),))
        return self.firewall_residue

    def delete_bridge_interfaces(self) -> tuple[str, ...]:
        self._record(name="delete_bridge_interfaces")
        return self.deleted_interfaces

    def compare_sysctls(self, *, snapshot: Path) -> tuple[str, ...]:
        self._record(name="compare_sysctls", detail=(str(snapshot),))
        return self.sysctl_differences

    def read_postconditions(self, *, snapshot: Path) -> Mapping[str, bool]:
        self._record(name="read_postconditions", detail=(str(snapshot),))
        return self.postconditions
