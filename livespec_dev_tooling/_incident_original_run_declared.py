"""The workflow a collection is graded against: the merge revision's own bytes and graph."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_original_run_graph import graph_refusal, watched_refusal
from livespec_dev_tooling._incident_run_types import EvidenceRefusal, ExpectedJob
from livespec_dev_tooling.incident_workflow_graph import derive_graph

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["declared_graph"]

_NOT_A_REVERT = "the revert does not descend from the original merge"
_Git = Callable[[Sequence[str], bytes], bytes]


@impure_safe
def _workflow_source(
    *, registration: ObserverRegistration, revert_sha: str, workflow_path: str, git: _Git
) -> bytes:
    merge = registration.head_sha
    if revert_sha == merge:
        raise ValueError(_NOT_A_REVERT)
    _ = git(["merge-base", "--is-ancestor", merge, revert_sha], b"")
    return git(["cat-file", "blob", f"{merge}:{workflow_path}"], b"")


def declared_graph(
    *,
    registration: ObserverRegistration,
    revert_sha: str,
    workflow_path: str,
    supplied: tuple[ExpectedJob, ...] | None,
    git: _Git,
) -> tuple[bytes, tuple[ExpectedJob, ...]] | EvidenceRefusal:
    """The merge revision's workflow bytes and the graph it declares, if the request agrees."""
    if supplied is not None:
        omitted = watched_refusal(registration=registration, graph=supplied)
        if omitted is not None:
            return omitted
    fetched = _workflow_source(
        registration=registration, revert_sha=revert_sha, workflow_path=workflow_path, git=git
    )
    if not is_successful(fetched):
        return EvidenceRefusal(
            code="incident-original-run-local-revision",
            detail="merge, revert or workflow does not resolve",
        )
    source = unsafe_perform_io(fetched.unwrap())
    graph = derive_graph(source=source)
    if isinstance(graph, EvidenceRefusal):
        return graph
    refusal = graph_refusal(registration=registration, declared=graph, supplied=supplied)
    return refusal if refusal is not None else (source, graph)
