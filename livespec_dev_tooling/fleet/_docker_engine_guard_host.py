"""The Docker engine install guard's real host — CHILDREN 3a AND 4 REPLACE THIS FILE.

`docker_engine_guard.py`'s command line builds its `HostOps` from
`build_real_host` here, so the real host actions (the one timed command
runner, the unit reads, the firewall work, the preflight and the probes)
land in this module without reopening the guard module.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions" and "Preflight".
Child 1a ships NO real host action: every assertion it makes runs
against `FakeHost` instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_hostops import HostOps
    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths

__all__: list[str] = [
    "build_real_host",
]


def build_real_host(*, paths: GuardPaths) -> HostOps:
    """The `HostOps` that actually touches this host, rooted at `paths`."""
    raise NotImplementedError
