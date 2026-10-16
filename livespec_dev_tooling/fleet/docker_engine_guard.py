"""The Docker engine install guard: one dispatch table over one lock.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" (this repository). Governing
design: `docs/docker-engine-guard-design.md`, revisions 5 to 8.

Run on the guarded host as `python3 docker_engine_guard.py <op> <run>`,
which is why every module in this set is STDLIB ONLY: the host has no
virtual environment and no third-party package, so the railway this
repository otherwise rides is not importable where this code executes.
Run that way there is also no PACKAGE, so the preamble below puts the
package root on `sys.path` and `sibling_module_name` falls back to the
guard's own package name — both halves are needed, because the sibling
modules import each other package-qualified.

WHAT THIS MODULE IS FOR. The guard installs the Docker engine on a host
that is already running k3s and is reachable only over Tailscale, so the
cost of a wrong move is an unreachable machine the maintainer cannot
power-cycle. Every operation therefore decides the same way: ensure the
runtime directory, take the one lock within a bounded wait, confirm the
run is the current reservation, read the commit MARKER (never the phase)
to learn whether the run is committed, and then consult exactly one
table. Nothing acts before that table says so.

Child 1a owns the lifecycle: the lock, the records, the deadline, the
table, and `reserve`, `publish`, `arm`, `start` and `recover`. Child 1b
owns `observe`, `confirm`, `verify` and `reconfigure`, each in its own
module beside this one; the rows that are still `_pending` reach their
table decision here and raise `NotImplementedError` past it. `rollback`'s
entry calls `run_rollback` in `_docker_engine_guard_rollback.py`, the
real host lives in `_docker_engine_guard_host.py`, and the package step
lives in `_docker_engine_guard_packages.py` — three stubs each sibling
replaces, so that no sibling ever has to edit this module.
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

# The guard also runs as a plain script on the guarded host, where there
# is no package and the sibling modules' package-qualified imports would
# not resolve. Putting the package ROOT on `sys.path` makes them resolve
# from either side — the same preamble every shipped module in this
# repository already carries for its vendored tree.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

# Child 1b's operation bodies are reached through their MODULES rather
# than name by name. Each is a table HANDLER and nothing else in this
# file calls it, so a module alias keeps the table reading as the
# registry it is instead of growing an import line per operation.
from livespec_dev_tooling.fleet import _docker_engine_guard_commit as commit  # noqa: E402
from livespec_dev_tooling.fleet import _docker_engine_guard_observer as observer  # noqa: E402
from livespec_dev_tooling.fleet._docker_engine_guard_cli import (  # noqa: E402
    CliRequest,
    emit,
    parse_request,
)
from livespec_dev_tooling.fleet._docker_engine_guard_dispatch import (  # noqa: E402
    DispatchRow,
    decide,
)
from livespec_dev_tooling.fleet._docker_engine_guard_hostops import HostOps  # noqa: E402
from livespec_dev_tooling.fleet._docker_engine_guard_model import (  # noqa: E402
    INSTALL_PHASES,
    PHASES,
    Decision,
    GuardOutcome,
    Holder,
    Operation,
)
from livespec_dev_tooling.fleet._docker_engine_guard_ops import (  # noqa: E402
    arm,
    publish,
    recover,
    reserve,
    start,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import (  # noqa: E402
    GuardEnv,
    acquire_lock,
    deadline_passed,
    ensure_runtime_dir,
    holder_of,
    read_marker,
    read_reservation,
    release_lock,
)

__all__: list[str] = [
    "DISPATCH_TABLE",
    "GUARD_PACKAGE",
    "main",
    "row_for",
    "run_operation",
    "run_request",
    "sibling_module_name",
]


def _pending(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """A row whose work a later child owns.

    The table decision above it is real and is reached on every
    invocation; only the work past it is missing, which is why this
    raises rather than returning a refusal — an unimplemented operation
    is a defect in the guard, not a state of the host.
    """
    raise NotImplementedError


GUARD_PACKAGE: Final[str] = "livespec_dev_tooling.fleet"


def sibling_module_name(*, package: str, name: str) -> str:
    """The import name of a module beside this one, from either side of the split.

    Imported as part of this package, `package` names it and the sibling
    is `<package>.<name>`. Run as `python3 docker_engine_guard.py` on the
    guarded host there is no package at all and `package` is empty — but
    the preamble above has put the package ROOT on `sys.path`, so the
    guard's own package name is the one that resolves.
    """
    return f"{package or GUARD_PACKAGE}.{name}"


def _sibling_module(*, name: str) -> ModuleType:
    """Import a sibling guard module, whichever way this module was loaded."""
    return importlib.import_module(sibling_module_name(package=__package__ or "", name=name))


def _rollback_entry(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Hand a decided rollback to child 2's driver.

    The decision above this call is 1a's and is made under the lock; the
    driver is reached by name so that child 2 implements it in its own
    module rather than in this one.
    """
    rollback = _sibling_module(name="_docker_engine_guard_rollback")
    return rollback.run_rollback(run=run, env=env, decision=decision)


DISPATCH_TABLE: Final[tuple[DispatchRow, ...]] = (
    DispatchRow(
        operation="reserve",
        handler=reserve,
        marker_self="refuse",
        allowed_from=("rolled-back",),
        allowed_without_reservation=True,
        transition="reserved",
    ),
    DispatchRow(
        operation="publish",
        handler=publish,
        marker_self="refuse",
        allowed_from=("reserved", "publishing"),
        transition="published",
    ),
    DispatchRow(
        operation="arm",
        handler=arm,
        marker_self="refuse",
        allowed_from=("published",),
        transition="armed",
    ),
    DispatchRow(
        operation="start",
        handler=start,
        marker_self="refuse",
        allowed_from=("armed",),
        needs_deadline=True,
        transition="started",
    ),
    DispatchRow(
        operation="observe",
        handler=observer.observe,
        marker_self="refuse",
        allowed_from=("started",),
        needs_deadline=True,
        transition="observing",
    ),
    DispatchRow(
        operation="confirm",
        handler=commit.confirm,
        marker_self="finish",
        allowed_from=("observed",),
        needs_deadline=True,
        transition="confirmed",
    ),
    DispatchRow(
        operation="rollback",
        handler=_rollback_entry,
        marker_self="noop",
        allowed_from=(*INSTALL_PHASES, "rolling-back", "rollback-partial"),
        noop_from=("rolled-back",),
        transition="rolling-back",
    ),
    DispatchRow(
        operation="recover",
        handler=recover,
        marker_self="finish",
        allowed_from=PHASES,
    ),
    DispatchRow(
        operation="verify",
        handler=_pending,
        marker_self="refuse",
        allowed_from=("rollback-partial", "rolled-back"),
    ),
    DispatchRow(
        operation="reconfigure",
        handler=_pending,
        marker_self="proceed",
        marker_self_from=("confirmed",),
    ),
)

_ROW_BY_OPERATION: Final[dict[Operation, DispatchRow]] = {
    row.operation: row for row in DISPATCH_TABLE
}


def row_for(*, operation: Operation) -> DispatchRow:
    """The one table row registering `operation`."""
    return _ROW_BY_OPERATION[operation]


def _decided(
    *, operation: Operation, run: str, decision: Decision, holder: Holder | None
) -> GuardOutcome:
    """Carry a refusal or a no-op out, with everything an operator must see."""
    return GuardOutcome(
        operation=operation,
        run=run,
        verdict=decision.verdict,
        reason=decision.reason,
        holder=holder,
    )


def _locked_operation(*, operation: Operation, run: str, env: GuardEnv) -> GuardOutcome:
    """Decide and run one operation, with the lock already held.

    The order is the specification's and is not interchangeable: the
    reservation first (an operation on a run this host does not hold
    changes nothing), then the MARKER, then the phase. Reading the phase
    before the marker would let a run whose phase record says `committed`
    after a failed directory fsync be treated as committed when it is not.
    """
    row = row_for(operation=operation)
    reservation = read_reservation(paths=env.paths)
    holder = holder_of(env=env, run=reservation)
    if not row.allowed_without_reservation and reservation != run:
        return GuardOutcome(
            operation=operation,
            run=run,
            verdict="refuse",
            reason=f"{run} is not this host's current reservation",
            holder=holder,
        )
    decision = decide(
        row=row,
        marker=read_marker(paths=env.paths, run=run),
        phase=None if holder is None else holder.phase,
        deadline_passed=deadline_passed(
            deadline=None if holder is None else holder.deadline, host=env.host
        ),
    )
    if decision.verdict in {"refuse", "noop"}:
        return _decided(operation=operation, run=run, decision=decision, holder=holder)
    return row.handler(run=run, env=env, decision=decision)


def run_operation(*, operation: Operation, run: str, env: GuardEnv) -> GuardOutcome:
    """Run one guard operation end to end: directory, lock, decision, work.

    Every operation takes this path, which is what makes the lock, the
    bounded wait and the reservation check properties of the GUARD rather
    than habits of each operation. A lock wait that expires refuses
    without acting: it has read nothing and written nothing.
    """
    ensure_runtime_dir(paths=env.paths, host=env.host)
    fd = acquire_lock(paths=env.paths, host=env.host)
    if fd is None:
        return GuardOutcome(
            operation=operation,
            run=run,
            verdict="refuse",
            reason="another guard operation holds the lock; waited the full bound and stopped",
        )
    try:
        return _locked_operation(operation=operation, run=run, env=env)
    finally:
        release_lock(fd=fd)


def run_request(*, request: CliRequest, host: HostOps) -> int:
    """Run one parsed request against `host` and report what it decided.

    Separated from `main` so the whole command line is exercised
    against `FakeHost`: `main`'s remaining job is to build the REAL
    host, which child 3a supplies and child 1a therefore cannot run.
    """
    env = GuardEnv(paths=request.paths, host=host, window_seconds=request.window_seconds)
    return emit(outcome=run_operation(operation=request.operation, run=request.run, env=env))


def main() -> int:
    """The guard's entry point, as the role's transient unit invokes it."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    request = parse_request(argv=sys.argv[1:])
    host_module = _sibling_module(name="_docker_engine_guard_host")
    return run_request(request=request, host=host_module.build_real_host(paths=request.paths))


if __name__ == "__main__":
    raise SystemExit(main())
