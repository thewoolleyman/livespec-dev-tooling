"""The fleet's serving readers, one per capability, composed for the audit.

Each capability is read from what actually serves it on this host: the installed
dev-tooling revision for gate readers, the consumer's default-branch workflow pins for
templates, the harness's installed plugin builds for driver hooks, the principal's
release with the forge bypass for recovery authorization, and the running observer
process for the independent controller. A capability this table does not name, and any
read that cannot be taken, is None: unverified.
"""

from __future__ import annotations

import shlex
import sys
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_runtime_budget.github_budget import GhInvocation  # noqa: E402

from livespec_dev_tooling._incident_fleet_driver_reader import read_driver_hooks  # noqa: E402
from livespec_dev_tooling._incident_fleet_gate_reader import read_gate_readers  # noqa: E402
from livespec_dev_tooling._incident_fleet_recovery_reader import (  # noqa: E402
    ForgeReader,
    read_recovery_authorization,
)
from livespec_dev_tooling._incident_fleet_release_keyed import ServingReading  # noqa: E402
from livespec_dev_tooling._incident_fleet_template_reader import read_templates  # noqa: E402
from livespec_dev_tooling.budgeted_gh import gh_read  # noqa: E402
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed  # noqa: E402
from livespec_dev_tooling.fleet._local_context import CommandRunner, command_answer  # noqa: E402
from livespec_dev_tooling.incident_fleet_controller_reader import (  # noqa: E402
    read_controller_serving,
)
from livespec_dev_tooling.incident_fleet_host import HostProbe  # noqa: E402

__all__: list[str] = [
    "PRODUCTION_READERS",
    "Reader",
    "ServingReader",
    "forge_reader",
    "host_serving_reader",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
Reader = Callable[..., str | ServingReading | None]


class ServingReader(Protocol):
    """Reads one capability's serving version for one consumer; None when unverified.

    A release-keyed read answers a `ServingReading`, which also names what it rests on.
    """

    def __call__(self, *, repository: str, capability: str) -> str | ServingReading | None: ...


def forge_reader(*, run: CommandRunner) -> ForgeReader:
    """The budgeted `gh` read, started through the audit's own runner.

    The budgeted client still builds the argv, spends the budget and reads the
    answer; only the process start is the audit's, so `gh` runs as a fixed binary
    with a scrubbed environment exactly as git and systemctl do.
    """

    def execute(*, argv: list[str]) -> GhInvocation:
        answer = command_answer(outcome=run(args=argv))
        if isinstance(answer, InvocationNotPerformed):
            return GhInvocation(argv=shlex.join(argv), unspawnable=answer.reason)
        return GhInvocation(
            argv=shlex.join(argv),
            stdout=answer.stdout,
            stderr=answer.stderr,
            returncode=answer.returncode,
        )

    return partial(gh_read, execute=execute)


def _recovery(*, probe: HostProbe, repository: str) -> str | None:
    return read_recovery_authorization(
        repository=repository,
        controller=read_controller_serving(probe=probe, repository=repository),
        read_forge=forge_reader(run=probe.run),
    )


PRODUCTION_READERS: Mapping[str, Reader] = MappingProxyType(
    {
        "gate-readers": read_gate_readers,
        "templates": read_templates,
        "driver-hooks": read_driver_hooks,
        "recovery-authorization": _recovery,
        "independent-controller": read_controller_serving,
    }
)


def host_serving_reader(
    *, probe: HostProbe, readers: Mapping[str, Reader] = PRODUCTION_READERS
) -> ServingReader:
    """A `(repository, capability)` reader; an unnamed capability reads as unverified."""

    def read(*, repository: str, capability: str) -> str | ServingReading | None:
        reader = readers.get(capability)
        return None if reader is None else reader(probe=probe, repository=repository)

    return read
