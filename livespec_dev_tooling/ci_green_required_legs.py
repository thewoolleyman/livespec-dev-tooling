"""ci_green_required_legs — every leg the gate job needs was CREATED and SUCCEEDED.

The aggregate gate job (`ci-green`) is the only context branch protection
requires, so it is the whole merge gate. Its `needs.*.result` expression sees
one result per NEEDED JOB, never per matrix LEG, and a leg the forge never
created contributes nothing to it at all. On 2026-11-09 GitHub created 8 of the
13 jobs of pull-request run 42673814418: `check-types` ran and passed while its
matrix siblings `check-lint` and `check-format` never existed, and neither
`check-per-file-coverage` nor `check-coverage` was created. `ci-green` read no
`failure` and no `cancelled` in its needs, passed, and auto-merge landed the PR
25 seconds later with no lint, format or coverage verdict on its head
(livespec-dev-tooling-nofeol).

This module closes that hole by reading the RUN rather than the needs. It
derives, from the workflow text the run used, the job name every needed leg
reports under:

- a job named `${{ matrix.target }}` reports one leg per `matrix.target` entry;
- any other job reports under its literal `name:`, or its job id without one.

It then compares that set against the run's own job list (the Actions jobs API
read the gate step hands it as JSON lines) and reports a gap for every leg that
is absent, or whose conclusion is anything other than `success`. A needed job
whose leg names cannot be derived is itself a gap: the gate fails closed rather
than checking less than it needs.

The expedited-incident omission path is untouched by construction. Under an
authorized incident the member-holding jobs still RUN and report each omitted
member through an explicit `omitted-by-incident-policy` step, so every leg is
created and concludes `success`, exactly as on any other passing run.

CLI:
    python -m livespec_dev_tooling.ci_green_required_legs \
        --workflow .github/workflows/ci.yml --gate-job ci-green --jobs <jobs.jsonl>

    `<jobs.jsonl>` holds one JSON object per line carrying at least `name`,
    `status` and `conclusion`. Exit 0 when every required leg was created and
    succeeded, 1 otherwise, with one `::error::` annotation per gap.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "GUARD_JOB",
    "NEVER_CREATED",
    "NO_NEEDS",
    "UNDERIVABLE",
    "LegGap",
    "RunJob",
    "leg_gaps",
    "main",
    "parse_run_jobs",
    "required_legs",
]

NEVER_CREATED = "never created in this run"
UNDERIVABLE = "its leg names cannot be derived from the workflow"
NO_NEEDS = "the gate job is absent from the workflow or declares no parseable needs"
_SUCCESS = "success"
_SKIPPED = "skipped"
# The merge-group guard job is a SIGNAL-ONLY need of the gate: the gate lists it so its
# `skip` output reaches the gate step (the jobs API does not expose outputs), and it is
# never itself a required leg. A failed or cancelled guard still fails the gate through
# the needs-result step.
GUARD_JOB = "merge-group-guard"
# A gating job whose `if:` carries this term may be SKIPPED, and only in a run whose
# guard output `skip` is true (livespec-dev-tooling-ymog6r, the merge-group tree-equality skip).
_SKIP_CONDITION = f"needs.{GUARD_JOB}.outputs.skip != 'true'"
_MATRIX_TARGET_NAME = "${{ matrix.target }}"
_MATRIX_REF = re.compile(r"\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}")
_AXIS_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):(.*)")
_QUOTED = re.compile(r"(['\"])(.*)\1")
_BLOCK_ITEM = re.compile(r"-\s+(.*)")
_COMMENT = re.compile(r"\s+#.*$")
_PLAIN_VALUE = re.compile(r"[A-Za-z0-9_./-]+")
_INTEGER = re.compile(r"0|[1-9][0-9]*")
# YAML 1.1 words a loader turns into a non-string, so the rendered name is not the text.
_YAML_WORDS = frozenset({"true", "false", "yes", "no", "on", "off", "y", "n", "null", "~"})
_UNMODELLED_AXES = frozenset({"include", "exclude"})
# The workflow's two-space YAML style: job ids at indent 2, job keys at 4.
_JOB_ID_INDENT = 2
_JOB_KEY_INDENT = 4


@dataclass(frozen=True, kw_only=True)
class RunJob:
    """One job of the run, as the Actions jobs API reports it."""

    name: str
    status: str
    conclusion: str


@dataclass(frozen=True, kw_only=True)
class LegGap:
    """A required leg the gate cannot count as passed, and why."""

    leg: str
    finding: str


def _indent(*, line: str) -> int:
    return len(line) - len(line.lstrip())


def _significant(*, line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _job_blocks(*, ci_yaml_text: str) -> dict[str, tuple[str, ...]]:
    """Map each top-level job id to its body lines."""
    blocks: dict[str, list[str]] = {}
    # Lines before the first job header belong to no job and are discarded.
    current: list[str] = []
    in_jobs = False
    for line in ci_yaml_text.splitlines():
        if line.rstrip() == "jobs:":
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if _significant(line=line) and _indent(line=line) == 0:
            break
        if (
            _indent(line=line) == _JOB_ID_INDENT
            and line.rstrip().endswith(":")
            and _significant(line=line)
        ):
            current = blocks.setdefault(line.strip()[:-1], [])
            continue
        current.append(line)
    return {job: tuple(body) for job, body in blocks.items()}


def _job_key(*, body: tuple[str, ...], key: str) -> str | None:
    """The inline value of a job-level `key:`, or None when the job has none."""
    for line in body:
        if _indent(line=line) == _JOB_KEY_INDENT and line.strip().startswith(f"{key}:"):
            return line.strip()[len(key) + 1 :].strip()
    return None


def _needs(*, value: str) -> tuple[str, ...]:
    inner = value.removeprefix("[").removesuffix("]")
    return tuple(token.strip() for token in inner.split(",") if token.strip())


def _matrix_lines(*, body: tuple[str, ...]) -> tuple[str, ...]:
    """The significant lines nested under the job's `matrix:` key."""
    starts = [index for index, line in enumerate(body) if line.strip() == "matrix:"]
    if not starts:
        return ()
    indent = _indent(line=body[starts[0]])
    nested: list[str] = []
    for line in body[starts[0] + 1 :]:
        if not _significant(line=line):
            continue
        if _indent(line=line) <= indent:
            break
        nested.append(line)
    return tuple(nested)


def _matrix_targets(*, body: tuple[str, ...]) -> tuple[str, ...]:
    """The `matrix.target` entries, or () for any matrix shape this reader does not model.

    Only a matrix whose ONE key is a block-list `target:` names its legs one per
    entry. A second axis (`os:`) makes legs that share a name, and `include:` or
    `exclude:` add or drop legs, so any key other than `target` is underivable:
    the gate fails closed rather than counting a partial leg set.
    """
    nested = _matrix_lines(body=body)
    key_indent = min((_indent(line=line) for line in nested), default=0)
    keys = {line.strip() for line in nested if _indent(line=line) == key_indent}
    if keys != {"target:"}:
        return ()
    return tuple(
        line.strip()[2:].split("#", 1)[0].strip()
        for line in nested[1:]
        if line.strip().startswith("- ")
    )


def _axis_value(*, text: str) -> str | None:
    """One plain scalar axis value as the forge renders it, or None when in doubt."""
    value = _COMMENT.sub("", text.strip()).strip()
    quoted = _QUOTED.fullmatch(value)
    value = quoted.group(2) if quoted else value
    if not _PLAIN_VALUE.fullmatch(value) or value.lower() in _YAML_WORDS:
        return None
    if value[0] in "0123456789+-." and not _INTEGER.fullmatch(value):
        return None
    return value


def _axis_items(*, inline: str, rest: list[str]) -> list[str] | None:
    """The raw item texts of one axis, from a flow list or a block list; None if neither."""
    inline = _COMMENT.sub("", inline.strip()).strip()
    if inline:
        if not (inline.startswith("[") and inline.endswith("]")) or rest:
            return None
        return inline[1:-1].split(",")
    # A line that is not a `- item` becomes a value no plain scalar can match.
    matches = [_BLOCK_ITEM.fullmatch(line.strip()) for line in rest]
    return [found.group(1) if found else "\0" for found in matches]


def _matrix_axes(*, body: tuple[str, ...]) -> dict[str, tuple[str, ...]] | None:
    """Every matrix axis with its rendered values, or None for any shape not modelled.

    Models only plain axes: a key whose value is a flow or block list of distinct plain
    scalars. `include:`/`exclude:`, a dynamic matrix, a duplicate key and any other value
    shape return None, so the caller treats the job's names as underivable.
    """
    nested = _matrix_lines(body=body)
    if not nested:
        return None
    key_indent = min(_indent(line=line) for line in nested)
    groups: list[tuple[str, str, list[str]]] = []
    for line in nested:
        found = _AXIS_LINE.fullmatch(line.strip())
        if _indent(line=line) == key_indent:
            # A top-level line that is not `key:` gets a key no axis can carry.
            groups.append((found.group(1) if found else "\0", found.group(2) if found else "", []))
        else:
            (groups or [("\0", "", [])])[-1][2].append(line)
    axes: dict[str, tuple[str, ...]] = {}
    for key, inline, rest in groups:
        items = _axis_items(inline=inline, rest=rest)
        values = None if items is None else [_axis_value(text=item) for item in items]
        if key in axes or key in _UNMODELLED_AXES or not values or None in values:
            return None
        if len(set(values)) != len(values):
            return None
        axes[key] = tuple(str(value) for value in values)
    return axes


def _render(*, name: str, values: dict[str, str]) -> str:
    return _MATRIX_REF.sub(lambda ref: values[ref.group(1)], name)


def _templated_names(*, name: str, body: tuple[str, ...]) -> tuple[str, ...]:
    """The cross product of the axes rendered into `name`; empty unless certain.

    Every axis must be named in the template (an unused axis makes legs that share a
    name) and no other expression may remain, else the names are not derivable.
    """
    axes = _matrix_axes(body=body)
    used = set(_MATRIX_REF.findall(name))
    if axes is None or not used or used != set(axes) or "${{" in _MATRIX_REF.sub("", name):
        return ()
    names = tuple(
        _render(name=name, values=dict(zip(axes, combo, strict=True)))
        for combo in itertools.product(*axes.values())
    )
    return names if len(set(names)) == len(names) else ()


def _leg_names(*, job: str, body: tuple[str, ...] | None) -> tuple[str, ...]:
    """The job names one needed job's legs report under; empty when underivable."""
    if body is None:
        return ()
    name = _job_key(body=body, key="name")
    if name == _MATRIX_TARGET_NAME:
        return _matrix_targets(body=body)
    if name is None:
        return (job,)
    if "${{" in name:
        return _templated_names(name=name, body=body)
    return (name,)


def required_legs(*, ci_yaml_text: str, gate_job: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Each job the gate needs, with the leg names it must report (empty: underivable)."""
    blocks = _job_blocks(ci_yaml_text=ci_yaml_text)
    gate = blocks.get(gate_job)
    needs_value = None if gate is None else _job_key(body=gate, key="needs")
    needed = () if needs_value is None else _needs(value=needs_value)
    needed = tuple(job for job in needed if job != GUARD_JOB)
    return tuple((job, _leg_names(job=job, body=blocks.get(job))) for job in needed)


def _skippable_jobs(*, ci_yaml_text: str) -> frozenset[str]:
    """The job ids whose `if:` carries the guard's skip condition."""
    return frozenset(
        job
        for job, body in _job_blocks(ci_yaml_text=ci_yaml_text).items()
        if _SKIP_CONDITION in (_job_key(body=body, key="if") or "")
    )


def leg_gaps(
    *, ci_yaml_text: str, gate_job: str, run_jobs: tuple[RunJob, ...], guard_skip: bool = False
) -> tuple[LegGap, ...]:
    """Every required leg that is absent from the run or did not succeed.

    `guard_skip` is the same run's guard output. Only when it is true may a leg of a
    skippable job be absent or `skipped`; every other leg, and every leg of any run
    whose guard did not output skip=true, must still be created and succeed.
    """
    needed = required_legs(ci_yaml_text=ci_yaml_text, gate_job=gate_job)
    skippable: frozenset[str] = (
        _skippable_jobs(ci_yaml_text=ci_yaml_text) if guard_skip else frozenset[str]()
    )
    if not needed:
        return (LegGap(leg=gate_job, finding=NO_NEEDS),)
    gaps: list[LegGap] = []
    for job, legs in needed:
        if not legs:
            gaps.append(LegGap(leg=job, finding=UNDERIVABLE))
        for leg in legs:
            may_skip = job in skippable
            accepted = (_SUCCESS, _SKIPPED) if may_skip else (_SUCCESS,)
            reported = [run_job for run_job in run_jobs if run_job.name == leg]
            if not reported and not may_skip:
                gaps.append(LegGap(leg=leg, finding=NEVER_CREATED))
            gaps.extend(
                LegGap(
                    leg=leg,
                    finding=f"status {run_job.status}, conclusion {run_job.conclusion or 'none'}",
                )
                for run_job in reported
                if run_job.conclusion not in accepted
            )
    return tuple(gaps)


def parse_run_jobs(*, jobs_jsonl: str) -> tuple[RunJob, ...]:
    """Read the jobs API projection: one JSON object per non-blank line."""
    records = [json.loads(line) for line in jobs_jsonl.splitlines() if line.strip()]
    return tuple(
        RunJob(
            name=str(record["name"]),
            status=str(record.get("status") or ""),
            conclusion=str(record.get("conclusion") or ""),
        )
        for record in records
    )


def main(*, argv: list[str] | None = None) -> int:
    """Exit 0 when every required leg of the gate job was created and succeeded."""
    parser = argparse.ArgumentParser(description="ci-green: every needed leg ran and passed")
    _ = parser.add_argument("--workflow", type=Path, required=True)
    _ = parser.add_argument("--gate-job", required=True)
    _ = parser.add_argument("--jobs", type=Path, required=True)
    # The guard job's `skip` output, passed from ci-green's needs context. Only the exact
    # text `true` counts; anything else is a full run.
    _ = parser.add_argument("--guard-skip", default="false")
    parsed = parser.parse_args(argv)
    gaps = leg_gaps(
        ci_yaml_text=parsed.workflow.read_text(encoding="utf-8"),
        gate_job=parsed.gate_job,
        run_jobs=parse_run_jobs(jobs_jsonl=parsed.jobs.read_text(encoding="utf-8")),
        guard_skip=parsed.guard_skip == "true",
    )
    lines = [f"::error::{parsed.gate_job}: required leg {gap.leg}: {gap.finding}\n" for gap in gaps]
    verdict = "FAILED" if gaps else "passed"
    lines.append(f"{parsed.gate_job}: every required leg was created and succeeded: {verdict}\n")
    _ = sys.stdout.write("".join(lines))
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
