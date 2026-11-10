"""Refuse an expected graph that disagrees with the merge revision's workflow, by name.

The workflow source at the merge revision is the authority for which jobs an original
run should have created. A graph an operator supplies is only a claim about it: one
that drops a declared job would hide that job from the never-created disposition, and
one that invents a job would report it as never created.
"""

from __future__ import annotations

from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_run_types import EvidenceRefusal, ExpectedJob

__all__: list[str] = ["graph_refusal", "watched_refusal"]


def _invalid(*, detail: str) -> EvidenceRefusal:
    return EvidenceRefusal(code="incident-original-run-graph-invalid", detail=detail)


def watched_refusal(
    *, registration: ObserverRegistration, graph: tuple[ExpectedJob, ...]
) -> EvidenceRefusal | None:
    """The registration's watched jobs a graph leaves out, named."""
    missing = sorted(set(registration.required_jobs) - {job.name for job in graph})
    return _invalid(detail="expected graph omits " + ", ".join(missing)) if missing else None


def graph_refusal(
    *,
    registration: ObserverRegistration,
    declared: tuple[ExpectedJob, ...],
    supplied: tuple[ExpectedJob, ...] | None,
) -> EvidenceRefusal | None:
    """Why a supplied graph (or the workflow itself) cannot be collected against, if it cannot."""
    if supplied is None:
        absent = sorted(set(registration.required_jobs) - {job.name for job in declared})
        if absent:
            detail = "the merge revision's workflow does not declare watched job " + ", ".join(
                absent
            )
            return _invalid(detail=detail)
        return None
    wanted = {job.name: set(job.needs) for job in declared}
    given = {job.name: set(job.needs) for job in supplied}
    omitted, invented = sorted(wanted.keys() - given.keys()), sorted(given.keys() - wanted.keys())
    rewired = sorted(name for name in wanted.keys() & given.keys() if wanted[name] != given[name])
    if omitted:
        return _invalid(detail="expected graph omits " + ", ".join(omitted))
    if invented:
        detail = "expected graph names jobs the merge revision's workflow does not declare: "
        return _invalid(detail=detail + ", ".join(invented))
    if rewired:
        detail = "expected graph needs differ from the merge revision's workflow for: "
        return _invalid(detail=detail + ", ".join(rewired))
    return None
