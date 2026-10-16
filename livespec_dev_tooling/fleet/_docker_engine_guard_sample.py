"""One observation sample of the Docker engine install guard: its probe results.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" (this repository).
Governing design: `docs/docker-engine-guard-design.md` Mechanism 3 as
corrected by R8.

`HostOps.sample` answers ONE record per sample and the observer treats a
record that does not say `passed` as the window's failure, so the probe
set, its retry rule and its failure record all live below that seam --
which is why they live here, beside each other, rather than inside the
observer that consumes them.

Stdlib only, Python 3.10 syntax, for the reason the model module records.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "ProbeResult",
]


@dataclass(frozen=True, kw_only=True)
class ProbeResult:
    """What one probe saw: which probe, whether it passed, and why not.

    The NAME is carried on the result rather than supplied by whoever
    records it, because the specification requires every probe failure
    to be recorded with the probe's name and its error — and a name the
    caller supplies is a name that can disagree with the probe that
    actually ran. An operator reading a rolled-back run has only this
    record to tell "Docker broke the pod network" from "CoreDNS
    restarted".
    """

    name: str
    passed: bool
    error: str = ""
