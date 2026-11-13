"""Validate and encode the structured coverage-reuse outcome contract.

Coverage consumer job logs carry one ``LIVESPEC_COVERAGE_REUSE_OUTCOME`` JSON
line, optionally behind the timestamp GitHub's job-log endpoint prepends. Its
stable detector fields are ``repository``, ``run_id``, ``job_id``,
``duration_ms`` and ``outcome``. The CI run exporter imports the public helpers
here so its job spans preserve that record without owning its parsing.
"""

from __future__ import annotations

import json
import re
from typing import Final, cast

__all__: list[str] = [
    "COVERAGE_CONSUMER_JOB_ID",
    "coverage_reuse_attributes",
    "coverage_reuse_outcome",
]

COVERAGE_CONSUMER_JOB_ID: Final = "check-coverage"
# GitHub's job-log endpoint prefixes every line with an RFC 3339 timestamp.
_LOG_LINE: Final = re.compile(r"^(?:\S+Z )?LIVESPEC_COVERAGE_REUSE_OUTCOME (?P<record>.*)$")
_FIELDS: Final = frozenset({"repository", "run_id", "job_id", "duration_ms", "outcome"})
_OUTCOMES: Final = frozenset(
    {"reused", "missing_receipt", "data_digest_mismatch", "tree_mismatch", "producer_failed"}
)


def coverage_reuse_outcome(
    *, repo: str, run_id: int, job_name: object, log: str
) -> dict[str, object] | None:
    """Return the one valid consumer outcome from ``log``, or no outcome."""
    try:
        records = [
            json.loads(match["record"])
            for line in log.splitlines()
            if (match := _LOG_LINE.match(line))
        ]
    except json.JSONDecodeError:
        return None
    if len(records) != 1 or not isinstance(records[0], dict):
        return None
    record = cast(dict[str, object], records[0])
    if frozenset(record) != _FIELDS:
        return None
    if (
        record["repository"] != repo
        or record["run_id"] != str(run_id)
        or record["job_id"] != job_name
        or not isinstance(record["duration_ms"], int)
        or record["duration_ms"] < 0
        or record["outcome"] not in _OUTCOMES
    ):
        return None
    return record


def coverage_reuse_attributes(*, outcome: dict[str, object]) -> list[dict[str, object]]:
    """Map every stable reuse field to its OTLP job-span attribute."""
    return [
        _attribute(key="ci.coverage_reuse.repository", value=outcome["repository"]),
        _attribute(key="ci.coverage_reuse.run_id", value=outcome["run_id"], value_type="intValue"),
        _attribute(key="ci.coverage_reuse.job_id", value=outcome["job_id"]),
        _attribute(
            key="ci.coverage_reuse.duration_ms", value=outcome["duration_ms"], value_type="intValue"
        ),
        _attribute(key="ci.coverage_reuse.outcome", value=outcome["outcome"]),
    ]


def _attribute(*, key: str, value: object, value_type: str = "stringValue") -> dict[str, object]:
    """Build one OTLP attribute in the exporter-compatible representation."""
    return {"key": key, "value": {value_type: str(value)}}
