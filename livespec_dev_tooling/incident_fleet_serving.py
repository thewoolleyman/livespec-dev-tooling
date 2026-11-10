"""The fleet's serving readers, one per capability, composed for the audit.

Each capability is read from what actually serves it on this host: the installed
dev-tooling revision for gate readers, the consumer's default-branch workflow pins for
templates, the harness's installed plugin builds for driver hooks, the principal's
release with the forge bypass for recovery authorization, and the running observer
process for the independent controller. A capability this table does not name, and any
read that cannot be taken, is None: unverified.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Protocol

from livespec_dev_tooling._incident_fleet_driver_reader import read_driver_hooks
from livespec_dev_tooling._incident_fleet_gate_reader import read_gate_readers
from livespec_dev_tooling._incident_fleet_recovery_reader import read_recovery_authorization
from livespec_dev_tooling._incident_fleet_template_reader import read_templates
from livespec_dev_tooling.incident_fleet_controller_reader import read_controller_serving
from livespec_dev_tooling.incident_fleet_host import HostProbe

__all__: list[str] = ["PRODUCTION_READERS", "Reader", "ServingReader", "host_serving_reader"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
Reader = Callable[..., str | None]


class ServingReader(Protocol):
    """Reads one capability's serving version for one consumer; None when unverified."""

    def __call__(self, *, repository: str, capability: str) -> str | None: ...


def _recovery(*, probe: HostProbe, repository: str) -> str | None:
    return read_recovery_authorization(
        repository=repository,
        controller=read_controller_serving(probe=probe, repository=repository),
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

    def read(*, repository: str, capability: str) -> str | None:
        reader = readers.get(capability)
        return None if reader is None else reader(probe=probe, repository=repository)

    return read
