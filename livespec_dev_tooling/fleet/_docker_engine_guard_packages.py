"""The Docker engine install guard's package step — CHILD 3b REPLACES THIS FILE.

The real host's `install_packages` seam calls `run_package_step` here, so
the fenced, audited transaction — the frontend lock, the simulated
transaction against the committed allowlist, the SHA256 and maintainer
script digests, `dpkg -i` under `DPKG_FRONTEND_LOCKED=1`, and the
interrupted-install recovery — lands in this module without reopening
the guard module or the host module.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence". The step is inert
by construction: the guard drop-ins are in place before it runs, so the
postinst's start finds its condition unmet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "run_package_step",
]


def run_package_step(*, inputs: Path) -> None:
    """Install exactly the audited package set named by this run's `inputs`."""
    raise NotImplementedError
