"""Which ci.yml jobs carry a job-level `if:` that names the triggering event or ref.

A TOKEN test, never an evaluation (livespec-dev-tooling-yzr6ad): a job-level `if:`
mentioning any `github.event*`, `github.ref*`, `github.head_ref` or
`github.base_ref`, in dotted or bracket form, marks the job event-bound, and the
incident CI entrance lists that job's members as ones it does not run instead of
running or dropping them. A job gated only on `!cancelled()` or `needs.*.result`
(dev-tooling's coverage and metadata jobs) is not event-bound, so its members
keep running. The expression is read across a block scalar (`>-`, `|`) or a
multi-line plain value, and a trailing YAML comment is not part of it.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.checks._ci_matrix_parse import job_blocks

__all__: list[str] = ["event_bound_jobs"]

_JOB_IF = re.compile(r"^(?P<indent> *)if:(?P<rest>.*)$")
_BLOCK_SCALAR = re.compile(r"^[|>][-+0-9]*$")
_EVENT_OR_REF = r"(?:event|ref|head_ref|base_ref)\w*"
_EVENT_BOUND_TOKEN = re.compile(
    rf"\bgithub(?:\.{_EVENT_OR_REF}|\[\s*['\"]{_EVENT_OR_REF}['\"]\s*\])"
)


def _without_comment(*, text: str) -> str:
    """`text` up to a YAML comment: a `#` outside quotes that follows whitespace."""
    quote = ""
    for index, char in enumerate(text):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index]
    return text


def _job_level_condition(*, body: list[str]) -> str:
    """The job-level `if:` expression's text, or the empty string when there is none."""
    lines = [raw for raw in body if raw.strip() and not raw.strip().startswith("#")]
    indent = len(lines[0]) - len(lines[0].lstrip()) if lines else -1
    for position, raw in enumerate(lines):
        match = _JOB_IF.match(raw)
        if match is None or len(match.group("indent")) != indent:
            continue
        head = _without_comment(text=match.group("rest")).strip()
        continuation: list[str] = []
        for following in lines[position + 1 :]:
            if len(following) - len(following.lstrip()) <= indent:
                break
            continuation.append(following)
        if _BLOCK_SCALAR.match(head):
            return "\n".join(continuation)
        return "\n".join([head, *(_without_comment(text=line) for line in continuation)])
    return ""


def event_bound_jobs(*, source: str) -> frozenset[str]:
    """Names of jobs whose job-level `if:` names the triggering event or ref."""
    return frozenset(
        name
        for name, body in job_blocks(source=source)
        if _EVENT_BOUND_TOKEN.search(_job_level_condition(body=body)) is not None
    )
