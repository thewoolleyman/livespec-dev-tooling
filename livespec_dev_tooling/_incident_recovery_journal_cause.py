"""The one cause a retained recovery action carries: a failing leaf or a regression reopen.

A failing required leaf of the registered master run and an authenticated
`/recover` for a canonically verified `reverting` generation both key the
registration's single action id. The principal's journal accepts an intent only
when exactly one cause is set and it binds to that registration.
"""

from __future__ import annotations

from typing import Any

from livespec_dev_tooling._incident_observer_types import (
    LeafCompletion,
    RecoveryIntent,
    RegressionReopen,
)
from livespec_dev_tooling._incident_recovery_journal_values import JournalValues

__all__: list[str] = ["decode_completion", "decode_regression", "has_one_cause"]

_FAILURES = frozenset({"failure", "timed_out", "action_required", "startup_failure", "stale"})


def decode_completion(*, raw: Any) -> LeafCompletion:
    """A retained failing master leaf, exactly as the observer persisted it."""
    data = JournalValues.object(value=raw)
    fields = {
        "delivery_id",
        "repository",
        "head_sha",
        "branch",
        "run_id",
        "job_id",
        "job_name",
        "conclusion",
    }
    if not (
        set(data) == fields
        and all(JournalValues.positive(value=data[key]) for key in ("run_id", "job_id"))
        and all(JournalValues.text(value=data[key]) for key in fields - {"run_id", "job_id"})
        and JournalValues.sha(value=data["head_sha"])
        and data["conclusion"] in _FAILURES
    ):
        message = "invalid recovery completion"
        raise ValueError(message)
    return LeafCompletion(**data)


def decode_regression(*, raw: Any) -> RegressionReopen | None:
    """A retained verified regression reopen, or none for a leaf-caused action."""
    if raw is None:
        return None
    data = JournalValues.object(value=raw)
    if not (
        set(data) == {"attempt_id", "operation_id", "generation", "owner", "receipt_digest"}
        and JournalValues.positive(value=data["generation"])
        and all(
            JournalValues.text(value=data[key]) for key in ("attempt_id", "operation_id", "owner")
        )
        and JournalValues.digest(value=data["receipt_digest"])
    ):
        message = "invalid recovery regression"
        raise ValueError(message)
    return RegressionReopen(**data)


def has_one_cause(*, intent: RecoveryIntent) -> bool:
    """A registered master leaf failed, or a later verified generation reopened the attempt."""
    registration, completion, regression = intent.registration, intent.completion, intent.regression
    if completion is None:
        return regression is not None and regression.generation > registration.generation
    return (
        regression is None
        and (completion.repository, completion.head_sha, completion.branch, completion.run_id)
        == (
            registration.repository,
            registration.head_sha,
            registration.branch,
            registration.run_id,
        )
        and completion.job_name in registration.required_jobs
    )
