"""Where a manifest consumer's clone is on this host."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.incident_fleet_host import HostProbe

__all__: list[str] = ["consumer_clone"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx


def consumer_clone(*, probe: HostProbe, repository: str) -> Path | None:
    """The consumer's clone beside this code's primary checkout, or None when it is absent.

    A consumer with no clone on this host (an adopter the operator has not cloned) has
    nothing installed to read; every reader treats that as unverified, not as an error.
    """
    name = repository.rsplit("/", 1)[-1]
    if probe.clones_root is None or name in {"", ".", ".."}:
        return None
    clone = probe.clones_root / name
    return clone if clone.is_dir() else None
