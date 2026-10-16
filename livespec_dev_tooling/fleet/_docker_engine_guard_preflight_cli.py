"""The command line the Docker engine install guard's ROLE runs the preflight through.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Preflight" and "Probes" --
"k3s witness" and "Interfaces". Governing design:
`docs/docker-engine-guard-design.md` F7 (the admission and collision
checks) and F8 (the witness the preflight records).

WHY THIS MODULE EXISTS, recorded because the gap it closes was found on
a real host rather than reasoned about. `RealHost.preflight_refusals`
and `RealHost.record_preflight` are deliberately NOT `HostOps` seams:
both run BEFORE `reserve`, so there is no run for the dispatch table to
admit an operation on, and they are the role's own reads of this
machine rather than steps of the lifecycle. But the role reaches the
guarded host only through the guard's own command line and through the
stdlib modules it runs as scripts, so until this module existed no
invocation reached either method -- which means no run on a real host
recorded the k3s witness, and every real `observe` died on a missing
`k3s-witness.json`.

WHY IT IS A SECOND COMMAND LINE RATHER THAN TWO MORE OPERATIONS. An
operation is admitted by the dispatch table, under the one lock, on a
run the host already reserved. These two reads have none of that: they
run before any run exists, which is exactly why child 4 kept them off
the protocol. Adding them to the table would have had to invent a
phase for them to be allowed from, so instead the role runs this
module the way it already runs the apt-lock helper --
`python3 -I -B <module> <subcommand>` from the installed guard tree.

Stdlib only, Python 3.10 syntax, for the reason the model module
records.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_host import build_real_host
from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_STATE_ROOT,
    GuardPaths,
)
from livespec_dev_tooling.fleet._docker_engine_guard_resync import K3S_CONFIG, K3S_CONFIG_DROPINS
from livespec_dev_tooling.fleet._docker_engine_guard_runner import run_command
from livespec_dev_tooling.fleet._docker_engine_guard_witness import PROC_ROOT

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from livespec_dev_tooling.fleet._docker_engine_guard_host import RealHost
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "LOGGER_NAME",
    "RECORD",
    "REFUSALS",
    "main",
    "read_declared_ranges",
]

LOGGER_NAME: Final[str] = "docker-engine-guard-preflight"

REFUSALS: Final[str] = "refusals"
RECORD: Final[str] = "record"

_PROG: Final[str] = "docker-engine-guard-preflight"
_DESCRIPTION: Final[str] = "Run the Docker engine install guard's preflight reads on this host."
_REFUSALS_HELP: Final[str] = "Report every reason this host may not reserve a run."
_RECORD_HELP: Final[str] = "Record the baselines every observation sample compares against."


def read_declared_ranges(*, path: Path) -> Mapping[str, str]:
    """The declared ranges the role uploaded: each range's name, mapped to its CIDR.

    DECLARED and never discovered, which is why they arrive as a file
    at all: the tailnet range and the cluster's pod and service CIDRs
    are facts about the tailnet and the cluster rather than about this
    machine, and a guard that read them off the host would be guessing
    on the one host that must not be guessed about.

    Both sides are coerced to `str` because the refusal an operator
    reads interpolates the label and the CIDR verbatim, and a JSON
    document is not obliged to carry strings in either position.
    """
    recorded = json.loads(path.read_text(encoding="utf-8"))
    return {str(label): str(cidr) for label, cidr in recorded.items()}


def _parser() -> argparse.ArgumentParser:
    """The whole command line: one subcommand per preflight read.

    Two subcommands rather than one invocation doing both, because the
    role runs them at different moments and for different reasons: the
    refusals decide whether the host may be reserved AT ALL, while the
    record is the baseline the window's samples compare against and so
    belongs after that decision and before the first package step.

    `--run` is REQUIRED and `--state-root` is not, which is the split
    the guard's own command line already makes: the run is decided by
    the role step and a default for it would be this module guessing
    which run it is recording, while the state root has a location the
    specification names and is overridden only for the disposable
    acceptance host.
    """
    parser = argparse.ArgumentParser(prog=_PROG, description=_DESCRIPTION)
    operations = parser.add_subparsers(dest="operation", required=True)
    refusals = operations.add_parser(REFUSALS, help=_REFUSALS_HELP)
    _ = refusals.add_argument("--declared", required=True)
    record = operations.add_parser(RECORD, help=_RECORD_HELP)
    _ = record.add_argument("--run", required=True)
    _ = record.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    return parser


def _host(
    *, state_root: Path = DEFAULT_STATE_ROOT, runner: GuardCommandRunner, proc_root: Path
) -> RealHost:
    """The real host both preflight reads run against.

    `build_real_host` and not the `HostOps` protocol, which is the
    whole point: a caller handed the protocol could not reach either of
    these two methods, because neither is a seam of it.

    The runtime root is the specification's own and is never overridden
    here: it holds the lock and the start permission, and the preflight
    takes neither -- it runs before there is a run to lock.
    """
    return build_real_host(
        paths=GuardPaths(state_root=state_root, runtime_root=DEFAULT_RUNTIME_ROOT),
        runner=runner,
        proc_root=proc_root,
    )


def _refusals(
    *, declared: Path, runner: GuardCommandRunner, proc_root: Path, config: Path, dropins: Path
) -> int:
    """Report every reason this host may not reserve a run; whether there was one.

    Every refusal is LOGGED one per line rather than returned, because
    the role's step reads exactly two things -- the exit code and the
    output -- and an operator on a machine reachable only over
    Tailscale has to be able to fix the host from the second.

    ALL of them, never the first: the preflight is one decision, so a
    command line that stopped at one reason would hand that operator a
    bridge to delete, then a group member to remove, then a drop-in to
    edit, one converge apart each.
    """
    refusals = _host(runner=runner, proc_root=proc_root).preflight_refusals(
        declared=read_declared_ranges(path=declared), config=config, dropins=dropins
    )
    logger = logging.getLogger(LOGGER_NAME)
    for refusal in refusals:
        logger.error(refusal)
    return 1 if refusals else 0


def _record(*, run: str, state_root: Path, runner: GuardCommandRunner, proc_root: Path) -> int:
    """Record the k3s witness and the interface snapshot in this run's `before/`.

    The destination is the run's OWN snapshot directory, derived from
    the state root rather than passed in, so a record cannot be written
    into another run's baseline -- a sample compared against a
    different run's snapshot is comparing this host with a different
    one.
    """
    host = _host(state_root=state_root, runner=runner, proc_root=proc_root)
    host.record_preflight(destination=host.paths.snapshot_dir(run=run))
    return 0


def main(
    *,
    argv: Sequence[str],
    runner: GuardCommandRunner = run_command,
    proc_root: Path = PROC_ROOT,
    config: Path = K3S_CONFIG,
    dropins: Path = K3S_CONFIG_DROPINS,
) -> int:
    """Run one preflight read and report what this host said.

    The four seams past `argv` carry the REAL defaults rather than
    being passed by the role, for the reason `RealHost` carries the
    same ones as fields: a read of the kernel's addresses and routes,
    of the NSS tables, of `/proc` and of k3s's own configuration cannot
    be proven at all against the machine a test is running on. The role
    passes none of them.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    args = _parser().parse_args(list(argv))
    if args.operation == RECORD:
        return _record(
            run=str(args.run),
            state_root=Path(args.state_root),
            runner=runner,
            proc_root=proc_root,
        )
    return _refusals(
        declared=Path(args.declared),
        runner=runner,
        proc_root=proc_root,
        config=config,
        dropins=dropins,
    )


if __name__ == "__main__":
    raise SystemExit(main(argv=sys.argv[1:]))
