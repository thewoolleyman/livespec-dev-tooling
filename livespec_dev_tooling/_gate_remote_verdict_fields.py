"""The delegated Job fields emitted with a gate verdict."""

from __future__ import annotations

from livespec_dev_tooling.gate_remote_verdict import GateVerdict

__all__: list[str] = ["verdict_job_fields"]


def verdict_job_fields(*, verdict: GateVerdict) -> dict[str, str]:
    """The verdict's own account of its Job, omitting facts no Job supplied."""
    named = {
        "job_name": verdict.job_name,
        "namespace": verdict.namespace,
        "job_started_at": verdict.job_started_at,
        "job_finished_at": verdict.job_finished_at,
    }
    return {field: value for field, value in named.items() if value is not None}
