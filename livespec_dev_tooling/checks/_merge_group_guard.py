"""Pure recognition of the guarded `merge_group` workflow shape."""

from __future__ import annotations

import re
from dataclasses import dataclass

from livespec_dev_tooling.checks._self_hosted_routing_parse import (
    runs_on_values,
    strip_yaml_comments,
    workflow_triggers,
)

__all__: list[str] = ["guarded_merge_group_is_valid", "routes_merge_group_to_self_hosted"]


_JOB_LINE = re.compile(r"^  (?P<name>[A-Za-z_][\w-]*):\s*$")
_FIELD_LINE = re.compile(r"^    (?P<name>[A-Za-z_-]+):(?P<value>.*)$", re.MULTILINE)
_OUTPUT_REFERENCE = "needs.{guard}.outputs."
_HOSTED_LITERAL = "ubuntu-latest"
_REQUIRED_LEGS_MODULE = "livespec_dev_tooling.ci_green_required_legs"
_MERGE_GROUP = "merge_group"


@dataclass(frozen=True, kw_only=True)
class _Job:
    """The static fields this guard needs from one workflow job."""

    name: str
    body: str
    needs: frozenset[str]
    runs_on: str
    condition: str


def _job_blocks(*, source: str) -> tuple[_Job, ...]:
    """Parse top-level `jobs` blocks from the limited workflow shape we inspect."""
    lines = source.splitlines()
    in_jobs = False
    starts: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        if line == "jobs:":
            in_jobs = True
            continue
        if in_jobs and line and not line.startswith((" ", "\t")):
            break
        if in_jobs:
            match = _JOB_LINE.match(line)
            if match is not None:
                starts.append((match.group("name"), index))
    jobs: list[_Job] = []
    for number, (name, start) in enumerate(starts):
        end = starts[number + 1][1] if number + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start + 1 : end])
        jobs.append(
            _Job(
                name=name,
                body=body,
                needs=_needs(body=body),
                runs_on=_field(body=body, name="runs-on"),
                condition=_field(body=body, name="if"),
            )
        )
    return tuple(jobs)


def _field(*, body: str, name: str) -> str:
    """Return one top-level job field's scalar or block text, if present."""
    for match in _FIELD_LINE.finditer(body):
        if match.group("name") == name:
            return match.group("value").strip()
    return ""


def _needs(*, body: str) -> frozenset[str]:
    """Read a `needs` scalar, flow list, or indented list from a job block."""
    match = re.search(r"^    needs:(?P<value>.*)$", body, re.MULTILINE)
    if match is None:
        return frozenset()
    value = match.group("value").strip()
    if value.startswith("[") and value.endswith("]"):
        return frozenset(
            item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()
        )
    if value:
        return frozenset({value.strip("\"'")})
    following = body[match.end() :].splitlines()
    return frozenset(
        line.strip()[2:].strip().strip("\"'") for line in following if line.startswith("      - ")
    )


def _hosted_read_only_guard(*, job: _Job, labels: frozenset[str]) -> bool:
    """Recognise a hosted guard with only read-level declared permissions."""
    if not job.runs_on or any(label in job.runs_on for label in labels | {"self-hosted"}):
        return False
    if "permissions: read-all" in job.body:
        return True
    permissions = re.search(
        r"^    permissions:\s*$([\s\S]*?)(?=^    [A-Za-z_-]+:|\Z)",
        job.body,
        re.MULTILINE,
    )
    if permissions is None:
        return False
    entries = re.findall(r"^      [A-Za-z_-]+:\s*(\w+)\s*$", permissions.group(1), re.MULTILINE)
    return bool(entries) and all(value == "read" for value in entries)


def _depends_on_guard(
    *, job: _Job, guard: str, jobs: dict[str, _Job], seen: frozenset[str]
) -> bool:
    """Return whether `job` reaches the guard through its declared needs graph."""
    if guard in job.needs:
        return True
    if job.name in seen:
        return False
    return any(
        dependency in jobs
        and _depends_on_guard(job=jobs[dependency], guard=guard, jobs=jobs, seen=seen | {job.name})
        for dependency in job.needs
    )


def _ci_green_reads_required_legs(*, jobs: dict[str, _Job]) -> bool:
    """Recognise the alternative gate that rejects skipped required legs.

    The gate is a job that runs `livespec_dev_tooling.ci_green_required_legs`
    with `--gate-job` naming that job's OWN id. The id must end at a token
    boundary, so `--gate-job ci-green-2` inside job `ci-green` is not it.
    """
    return any(
        _REQUIRED_LEGS_MODULE in job.body
        and re.search(rf"--gate-job\s+{re.escape(job.name)}(?![\w-])", job.body) is not None
        for job in jobs.values()
    )


def guarded_merge_group_is_valid(
    *, source: str, gating_labels: frozenset[str], author_allowlist: tuple[str, ...]
) -> bool:
    """Whether a self-hosted `merge_group` route has every required guard."""
    jobs_in_order = _job_blocks(source=source)
    if not jobs_in_order:
        return False
    guard = jobs_in_order[0]
    jobs = {job.name: job for job in jobs_in_order}
    gating_jobs = tuple(
        job for job in jobs_in_order if any(label in job.runs_on for label in gating_labels)
    )
    output_reference = _OUTPUT_REFERENCE.format(guard=guard.name)
    return (
        bool(author_allowlist)
        and _hosted_read_only_guard(job=guard, labels=gating_labels)
        and all(
            _depends_on_guard(job=job, guard=guard.name, jobs=jobs, seen=frozenset())
            for job in jobs_in_order[1:]
        )
        and bool(gating_jobs)
        and all(
            guard.name in job.needs
            and output_reference in job.runs_on
            and _HOSTED_LITERAL in job.runs_on
            for job in gating_jobs
        )
        and (
            _ci_green_reads_required_legs(jobs=jobs)
            or all("!cancelled()" in job.condition for job in gating_jobs)
        )
    )


def routes_merge_group_to_self_hosted(*, source: str, gating_labels: frozenset[str]) -> bool:
    """Whether a workflow takes `merge_group` and can route a job to a gating label.

    This is the repository-level fact `branch_protection_alignment` reads to
    decide that a repository uses the guarded `merge_group` exception and so
    owes the strictest fork-PR approval setting.
    """
    stripped = strip_yaml_comments(source=source)
    if _MERGE_GROUP not in workflow_triggers(stripped=stripped):
        return False
    values = runs_on_values(stripped=stripped)
    return any(label in value for label in gating_labels for value in values)
