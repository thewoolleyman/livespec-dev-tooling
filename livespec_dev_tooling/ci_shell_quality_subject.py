"""ci_shell_quality_subject — does a CI job give `check-shell-quality` its SUBJECT?

THE DEFECT THIS PREDICATE EXISTS FOR (work-item livespec-dev-tooling-y6e2,
measured 2026-08-04 on livespec master run 30939328152). The gate reads the
root justfile through `just --dump`. The worktree-discipline pack's recipe
fragments are GITIGNORED and reach that justfile only through an OPTIONAL
`import?` line, which resolves SILENTLY TO NOTHING when the pack is absent.
So a CI job that runs the gate without first materializing the pack scans a
justfile the pack's recipes have vanished from, finds nothing to convict, and
reports SUCCESS having verified nothing. That job's step list read:

    skipped | Install canonical worktree pack (satisfy invariant)
    success | just check-shell-quality

WHY THIS IS A PREDICATE AND NOT A COMMENT. The remedy — install the pack
before the gate — landed in this repo as livespec-dev-tooling-9ywf and in
eight consumer repos on 2026-08-05, and in every one of the eight the
mechanism of the defect was the SAME: an install step that existed, ran
before the gate, and carried an `if:` naming only the OTHER matrix target
that needs the pack. The invariant was then recorded only in a ci.yml
comment, which no run reads. This module makes it answerable.

WHAT COUNTS AS RUNNING THE GATE, and it is deliberately two forms rather than
one. A job runs the gate when a step's `run:` names the slug literally (this
repo's batched shape), OR when the job's `strategy.matrix.target` list
contains the slug and a step runs `matrix.target` (the shape all eight
consumers used, and the one this repo could return to). Recognising only the
literal form would leave the predicate blind to exactly the arrangement that
produced the defect — the same class of hole it exists to close.

WHAT COUNTS AS A SATISFIED SUBJECT. Some step BEFORE the gate step must run
the canonical installer, and that step must be reachable on the gate's own
leg: unconditional, or carrying an `if:` that names the gate slug. A
condition that does not name the slug is precisely the measured failure — it
is what turns the install step's status to `skipped` while the gate beside it
stays green.

The parser is a line walk over the workflow TEXT and is PURE — no IO, no
logging — so the caller owns its own file access and diagnostics. It is a
MECHANICAL extractor ("give me each job's steps"), which is the half of this
package's bounded parser-duplication convention that permits a local copy;
see `checks/_ci_matrix_parse`'s module docstring for the rule and for why a
SPEC-RULE-ENCODING parser may never be copied. `checks/_ci_matrix_parse`'s
own `CiJob` carries no step list, so there is nothing here to share.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "GATE_SLUG",
    "PACK_INSTALL_ABSENT",
    "PACK_INSTALL_AFTER_GATE",
    "PACK_INSTALL_CONDITIONALLY_SKIPPED",
    "SubjectGap",
    "shell_quality_subject_gaps",
]

GATE_SLUG = "check-shell-quality"

PACK_INSTALL_ABSENT = "pack_install_absent"
PACK_INSTALL_AFTER_GATE = "pack_install_after_gate"
PACK_INSTALL_CONDITIONALLY_SKIPPED = "pack_install_conditionally_skipped"

# The two spellings a fleet CI job uses to materialize the pack. The producer
# invokes the installer module directly; consumers that wire the recipe run it
# through `just`. Both reach the same single canonical-body carrier, so neither
# is preferred here — what matters is that the job runs one of them.
_INSTALL_COMMANDS = (
    "livespec_dev_tooling.install_worktree_pack",
    "just install-worktree-pack",
)
# The expression a matrix job's single run step expands to its leg's slug.
_MATRIX_TARGET_EXPRESSION = "matrix.target"

_JOBS_HEADER = re.compile(r"^jobs:\s*$")
_JOB_HEADER = re.compile(r"^\s*([\w.-]+):\s*$")

_ABSENT_DETAIL = (
    "this job runs `check-shell-quality` and never installs the "
    "worktree-discipline pack, so the gate scans a justfile whose `import? "
    "'dev-tooling/worktree.just'` resolved to nothing — it can only pass"
)
_AFTER_GATE_DETAIL = (
    "this job installs the worktree-discipline pack only AFTER running "
    "`check-shell-quality`, so the gate still read a justfile without the "
    "pack's recipes; move the install step above the gate step"
)
_CONDITIONALLY_SKIPPED_DETAIL = (
    "this job's worktree-pack install step carries an `if:` that never names "
    "`check-shell-quality`, so on the gate's own leg the step reports "
    "`skipped` and the gate reports success having verified nothing; widen "
    "the condition to include the gate target, or make the step unconditional"
)


@dataclass(frozen=True, kw_only=True)
class SubjectGap:
    """One CI job that runs the shell-quality gate without giving it a subject.

    `detail` carries the whole remedy rather than a restatement of the failure
    mode, because the three modes are fixed in three different places — add a
    step, move a step, widen a condition — and a reader who has just been told
    a job "has a gap" still has to be told which.
    """

    job: str
    failure_mode: str
    detail: str


def _indent(*, line: str) -> int:
    return len(line) - len(line.lstrip())


def _significant(*, lines: tuple[str, ...]) -> tuple[str, ...]:
    """Drop blank and comment-only lines.

    Done ONCE, before any indentation is measured, so a full-width comment can
    neither terminate a block walk nor set the indent a block's members are
    recognised at. It also keeps a comment that MENTIONS the gate slug — this
    repo's ci.yml carries one, right above the batch job — from being read as
    a job that runs it.
    """
    return tuple(line for line in lines if line.strip() and not line.strip().startswith("#"))


def _block(*, lines: tuple[str, ...], start: int, indent: int) -> tuple[str, ...]:
    """The run of lines after `start` indented deeper than `indent`."""
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _indent(line=line) <= indent:
            break
        body.append(line)
    return tuple(body)


def _job_blocks(*, lines: tuple[str, ...]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Each top-level `jobs:` entry as `(name, its lines)`.

    A line at the job indent that is not a `name:`-shaped header is not a job
    and is skipped rather than read as one.
    """
    start = next((index for index, line in enumerate(lines) if _JOBS_HEADER.match(line)), None)
    if start is None:
        return ()
    body = _block(lines=lines, start=start, indent=0)
    if not body:
        return ()
    job_indent = _indent(line=body[0])
    headers = [
        (index, match.group(1))
        for index, line in enumerate(body)
        if _indent(line=line) == job_indent and (match := _JOB_HEADER.match(line)) is not None
    ]
    return tuple(
        (name, _block(lines=body, start=index, indent=job_indent)) for index, name in headers
    )


def _key_block(*, block: tuple[str, ...], key: str) -> tuple[str, ...]:
    """The lines under `<key>:` in `block`; empty when the key is absent."""
    start = next((index for index, line in enumerate(block) if line.strip() == f"{key}:"), None)
    if start is None:
        return ()
    return _block(lines=block, start=start, indent=_indent(line=block[start]))


def _steps(*, block: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """A job's steps, each normalized so its keys share one indent.

    The `- ` bullet is rewritten to two spaces on a step's first line, which
    puts `name:` at the same indent as the `if:` and `run:` below it. Without
    that, a step written `- if: ...` would hide its own condition from the key
    lookups, and a hidden condition reads as UNCONDITIONAL — the one direction
    this predicate must never be wrong in.
    """
    body = _key_block(block=block, key="steps")
    if not body:
        return ()
    item_indent = _indent(line=body[0])
    starts = [
        index
        for index, line in enumerate(body)
        if _indent(line=line) == item_indent and line.strip().startswith("- ")
    ]
    return tuple(
        (" " * (item_indent + 2) + body[start].strip()[2:], *body[start + 1 : end])
        for start, end in zip(starts, [*starts[1:], len(body)], strict=True)
    )


def _key_value(*, step: tuple[str, ...], key: str) -> str:
    """A step key's value: its inline text plus any block-scalar continuation.

    One reader for both `run:` and `if:`, because both are written inline in
    some jobs and as a `|` / `>-` block in others, and a reader that knew only
    the inline form would read a folded condition as absent.
    """
    at = next(
        (index for index, line in enumerate(step) if line.strip().startswith(f"{key}:")), None
    )
    if at is None:
        return ""
    inline = step[at].strip().removeprefix(f"{key}:").strip()
    tail = _block(lines=step, start=at, indent=_indent(line=step[at]))
    return " ".join([inline, *(line.strip() for line in tail)]).strip()


def _runs_gate(*, step: tuple[str, ...], matrix_runs_gate: bool) -> bool:
    """Whether this step RUNS the gate — read from `run:`, never from the step's text.

    Reading the whole step would let the FIXED install step — whose `if:`
    names the gate slug precisely because it must run on that leg — be
    mistaken for the gate step itself, and the fix would then report as the
    defect.
    """
    run = _key_value(step=step, key="run")
    return GATE_SLUG in run or (matrix_runs_gate and _MATRIX_TARGET_EXPRESSION in run)


def _installs_pack(*, step: tuple[str, ...]) -> bool:
    run = _key_value(step=step, key="run")
    return any(command in run for command in _INSTALL_COMMANDS)


def _matrix_runs_gate(*, block: tuple[str, ...]) -> bool:
    """Whether the job fans out over a matrix leg for the gate slug."""
    strategy = _key_block(block=block, key="strategy")
    return any(line.strip() == f"- {GATE_SLUG}" for line in strategy)


def _job_gaps(*, job: str, block: tuple[str, ...]) -> tuple[SubjectGap, ...]:
    """The subject gap this one job carries, if any.

    A pre-gate install step satisfies the job when ANY of them is reachable on
    the gate's leg, so a job may carry a second, narrowly-conditioned install
    step for some other target without that reading as the defect.
    """
    steps = _steps(block=block)
    matrix_runs_gate = _matrix_runs_gate(block=block)
    gate_at = next(
        (
            index
            for index, step in enumerate(steps)
            if _runs_gate(step=step, matrix_runs_gate=matrix_runs_gate)
        ),
        None,
    )
    if gate_at is None:
        return ()
    before = [index for index in range(gate_at) if _installs_pack(step=steps[index])]
    if not before:
        installs_later = any(_installs_pack(step=step) for step in steps[gate_at:])
        mode = PACK_INSTALL_AFTER_GATE if installs_later else PACK_INSTALL_ABSENT
        detail = _AFTER_GATE_DETAIL if installs_later else _ABSENT_DETAIL
        return (SubjectGap(job=job, failure_mode=mode, detail=detail),)
    conditions = [_key_value(step=steps[index], key="if") for index in before]
    if any(not condition or GATE_SLUG in condition for condition in conditions):
        return ()
    return (
        SubjectGap(
            job=job,
            failure_mode=PACK_INSTALL_CONDITIONALLY_SKIPPED,
            detail=_CONDITIONALLY_SKIPPED_DETAIL,
        ),
    )


def shell_quality_subject_gaps(*, ci_yaml_text: str) -> tuple[SubjectGap, ...]:
    """Every CI job that runs `check-shell-quality` without materializing its subject.

    THE public entry point, and pure by construction: it takes the workflow
    TEXT, so the same predicate answers for a checkout on disk and for a
    member's committed ci.yml read over an API. An empty tuple means every
    gate-running job installs the pack first, on the gate's own leg.
    """
    jobs = _job_blocks(lines=_significant(lines=tuple(ci_yaml_text.splitlines())))
    return tuple(gap for name, block in jobs for gap in _job_gaps(job=name, block=block))
