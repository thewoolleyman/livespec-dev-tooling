"""Fleet membership contract — central conformance check + reconcile mode.

Per `livespec/SPECIFICATION/non-functional-requirements.md` §"Fleet
membership contract": a committed manifest in livespec core
(`.livespec-fleet-manifest.jsonc` at that repo's root) enumerates every fleet
repo and its repo class; this package carries the SHARED contract
definition (the per-class obligation table in `contract`), the
central assert mode (`fleet_conformance`, wired into `just
check-fleet-conformance`, the scheduled fleet workflow, and the
release fan-out preflight), and the idempotent reconcile mode
(`wire_fleet_member`, operator-invoked under the 1Password
environment wrapper).
"""

from __future__ import annotations

__all__: list[str] = []
