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
from typing import Protocol

__all__: list[str] = [
    "Probe",
    "ProbeResult",
    "run_probe",
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

    # Whether this result is EVIDENCE, as distinct from whether it
    # passed. The two come apart in exactly one place (design F7): a
    # DNS probe answered by a CoreDNS replica that has been rescheduled
    # onto this node did not fail -- the reschedule is ordinary cluster
    # behaviour and says nothing about Docker -- but it stopped proving
    # that the pod network reaches ANOTHER node, which is the property
    # the probe exists to establish. Reporting that as a failure would
    # roll back a healthy install; reporting it as a pass would confirm
    # one on evidence that was not gathered.
    counts_toward_confirmation: bool = True


class Probe(Protocol):
    """One bounded probe of the guarded host, re-runnable with no arguments.

    No arguments at all, so the retry below can run the SAME probe
    again without knowing what it probes: whatever a probe needs -- a
    runner, a pod's namespace PID, a snapshot directory -- is bound
    when the probe is assembled, and the retry rule stays one rule
    rather than one per probe.
    """

    def __call__(self) -> ProbeResult: ...


def run_probe(*, probe: Probe) -> ProbeResult:
    """Run `probe`, and on a failure run it once more IMMEDIATELY.

    A single failed request is not evidence that Docker broke anything.
    This host runs a CI pool whose pods are created and deleted
    continuously, CoreDNS restarts, and a window sampling every fifteen
    seconds will land on one of those moments sooner or later -- so a
    window that rolled back on the first failure would never confirm an
    install on a perfectly healthy machine.

    The retry is immediate rather than delayed on purpose: the point is
    to distinguish a transient from a change, and waiting would give a
    real breakage time to look like one more transient.

    BOTH attempts' errors are recorded when the retry fails too,
    because "it failed twice the same way" and "it failed twice
    differently" point an operator at different causes -- and the
    second result's own `counts_toward_confirmation` is carried
    forward, since that is a fact about the evidence rather than about
    the attempt.
    """
    first = probe()
    if first.passed:
        return first
    second = probe()
    if second.passed:
        return second
    return ProbeResult(
        name=second.name,
        passed=False,
        error=f"{first.error}; then {second.error}",
        counts_toward_confirmation=second.counts_toward_confirmation,
    )
