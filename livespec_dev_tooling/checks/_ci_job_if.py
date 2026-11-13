"""Which ci.yml jobs carry a job-level `if:` that names the triggering event or ref.

A TOKEN test, never an evaluation (livespec-dev-tooling-yzr6ad): a job-level `if:`
mentioning any `github.event*`, `github.ref*`, `github.head_ref` or
`github.base_ref` marks the job event-bound, and the incident CI entrance lists
that job's members as not run by it instead of running or dropping them. A job
gated only on `!cancelled()` or `needs.*.result` (dev-tooling's coverage and
metadata jobs) is not event-bound, so its members keep running.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.checks._ci_matrix_parse import job_blocks

__all__: list[str] = ["event_bound_jobs"]

_JOB_IF = re.compile(r"^(?P<indent>\s*)if:\s*(?P<expr>.*?)\s*$")
_EVENT_BOUND_TOKEN = re.compile(r"\bgithub\.(?:event_name|event|ref_name|ref|head_ref|base_ref)\b")


def event_bound_jobs(*, source: str) -> frozenset[str]:
    """Names of jobs whose job-level `if:` names the triggering event or ref."""
    bound: set[str] = set()
    for name, body in job_blocks(source=source):
        lines = [raw for raw in body if raw.strip() and not raw.strip().startswith("#")]
        indent = len(lines[0]) - len(lines[0].lstrip()) if lines else -1
        for raw in lines:
            match = _JOB_IF.match(raw)
            if (
                match is not None
                and len(match.group("indent")) == indent
                and _EVENT_BOUND_TOKEN.search(match.group("expr")) is not None
            ):
                bound.add(name)
    return frozenset(bound)
