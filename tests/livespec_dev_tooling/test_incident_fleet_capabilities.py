"""Every audited surface is served by one known capability, and the map cannot be edited."""

from __future__ import annotations

from types import MappingProxyType

from livespec_dev_tooling._incident_fleet_capabilities import CAPABILITIES, SURFACE_CAPABILITY
from livespec_dev_tooling.incident_fleet_audit import SURFACES


def test_every_audited_surface_is_served_by_exactly_one_known_capability() -> None:
    assert set(SURFACE_CAPABILITY) == set(SURFACES)
    assert set(SURFACE_CAPABILITY.values()) == set(CAPABILITIES)


def test_the_surface_capability_map_is_read_only() -> None:
    assert isinstance(SURFACE_CAPABILITY, MappingProxyType)
