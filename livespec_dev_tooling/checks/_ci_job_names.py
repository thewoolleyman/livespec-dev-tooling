"""_ci_job_names — the ci.yml names a required status check may legitimately match.

Shared by BOTH the repo-local `branch_protection_alignment` check (which
reads the working tree's own ci.yml) and the central
`assert_branch_protection` fleet obligation row (which reads each member's
ci.yml over the GitHub contents API), so the "is this required check real?"
grammar has ONE definition.

That single definition is the point. The two surfaces previously carried
independent line-walk copies, and the copies DRIFTED: the fleet copy knew
only about `matrix.target` legs, so the single top-level aggregate gate job
the contract mandates read as a phantom required check on every member.
Per `livespec/SPECIFICATION/non-functional-requirements.md` section "CI as a merge
gate (branch protection)", a required check is legitimate when it matches a
CI matrix leg OR a top-level CI job, and is flagged only when it matches
NEITHER: "A required top-level all-green gate job (the `ci-green`
single-gate model) is a valid required check and is NOT flagged, even
though it is not a matrix leg, because requiring it gates the whole matrix
through its `needs:`."

The parsers are regex line-walks and are PURE — no IO, no logging — so
each caller owns its own file access and diagnostics. This module is the
sharing half of the package's BOUNDED parser-duplication convention (see
`_ci_matrix_parse`'s module docstring): these parsers encode a spec rule
and carry its citation, so they MUST live here, shared — never re-copied
per check.
This is deliberately NOT the richer job model in `_ci_matrix_parse`, whose
`parse_ci_jobs` serves `ci_matrix_completeness`'s `needs:`-fan-in
assertions and does not carry a job's literal `name:` value (the context a
non-matrix job actually reports under).

The leading underscore marks this a private sibling module: entry-point
check scripts under `livespec_dev_tooling/checks/` carry no underscore
prefix, so this file is neither a canonical slug (`canonical_check_slugs`
skips `_`-prefixed modules) nor a mirror-paired module.
"""

from __future__ import annotations

import re

# Names in `__all__` mark this private sibling's public surface to its
# importers — `checks/branch_protection_alignment.py`, `fleet/_rows_github.py`,
# and `fleet/_ci_workflow_source.py` (which reads a member's non-ci.yml
# pull_request(_target) workflows) — so pyright's per-file analysis does not
# flag them unused across the package boundary.
__all__: list[str] = [
    "parse_ci_matrix",
    "parse_top_level_jobs",
    "workflow_triggers_pull_request",
]

# `matrix.target` anchors: the `matrix:` table, its `target:` key, and the
# bullet entries that look like job slugs (`- check-foo`).
_MATRIX_HEADER = re.compile(r"^\s*matrix:\s*$")
_MATRIX_TARGET_KEY = re.compile(r"^\s*target:\s*$")
_MATRIX_TARGET_LINE = re.compile(r"^\s*-\s*([\w-]+)\s*$")
# Top-level job recognition, for the single-gate model where branch
# protection requires only an aggregate gate job (e.g. `ci-green`) that is
# a TOP-LEVEL job — not a matrix leg. `_JOBS_HEADER` marks the `jobs:`
# block; `_JOB_ID_LINE` matches a job key at the 2-space job indent
# (`  ci-green:` → `ci-green`); `_JOB_NAME_LINE` matches a job's `name:`
# value (a non-matrix job's reported status-check context is its `name:`,
# falling back to the job id when `name:` is absent). `_JOB_NAME_LINE`'s
# leading-`\s+`-then-`name:` shape deliberately does NOT match step-level
# `- name:` lines (those carry a `- ` prefix before `name:`).
_JOBS_HEADER = re.compile(r"^jobs:\s*$")
_JOB_ID_LINE = re.compile(r"^  ([A-Za-z0-9_-]+):")
_JOB_NAME_LINE = re.compile(r"^\s+name:\s*(.+?)\s*$")
# Workflow-trigger recognition, for the phantom-check rule's SECOND source
# of legitimate required-check reporters. A required status check may be
# reported by a workflow OTHER than ci.yml — but only one that runs on a
# pull request: an `on:` including `pull_request` or its base-branch-side
# sibling `pull_request_target` (the shape a base-branch gate uses to run
# the BASE branch's definition against an untrusted head). `_ON_KEY_LINE`
# matches the top-level `on:` key — quoted or bare, since some YAML linters
# rewrite the truthy `on` key to `"on":` — capturing any inline value; the
# block form is a bare `on:` followed by indented event lines. A plain
# `pull_request` substring test covers BOTH events, since `pull_request` is
# a prefix of `pull_request_target`.
_ON_KEY_LINE = re.compile(r"""^["']?on["']?:\s*(.*?)\s*$""")
_PR_EVENT_TOKEN = "pull_request"


def parse_ci_matrix(*, source: str) -> set[str]:
    """Extract the `matrix.target` job names from a ci.yml source text.

    Walks the file line-by-line looking for the `matrix:` table, then the
    `target:` key, then bullet entries that look like job slugs
    (`- check-foo`). Stops collecting once a non-bullet non-comment line
    outside the bullet block is hit.
    """
    targets: set[str] = set()
    in_matrix = False
    in_target_list = False
    for raw in source.splitlines():
        if _MATRIX_HEADER.match(raw):
            in_matrix = True
            in_target_list = False
            continue
        if not in_matrix:
            continue
        if _MATRIX_TARGET_KEY.match(raw):
            in_target_list = True
            continue
        if in_target_list:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _MATRIX_TARGET_LINE.match(raw)
            if match is None:
                # End of bullet list (next YAML key or section).
                in_target_list = False
                continue
            targets.add(match.group(1))
    return targets


def parse_top_level_jobs(*, source: str) -> set[str]:
    """Extract the top-level job identifiers and literal `name:` values from ci.yml.

    Under the single-gate model, branch protection requires only an
    aggregate gate job (e.g. `ci-green`) that is a TOP-LEVEL job, not a
    matrix leg — so `parse_ci_matrix` alone cannot see it. This parser
    collects, from within the `jobs:` block:

    - each 2-space-indented job KEY (`  ci-green:` → `ci-green`), and
    - each job's literal `name:` VALUE, because a non-matrix job's
      reported status-check context is its `name:` (falling back to the
      job id when `name:` is absent).

    Templated `name:` values (`name: ${{ matrix.target }}`) are SKIPPED:
    matrix legs report under `${{ matrix.target }}` and are already
    covered by `parse_ci_matrix`. Step-level `- name:` lines (a `- `
    prefix) are not matched. Scanning stops at the next column-0 key
    after `jobs:`.
    """
    names: set[str] = set()
    in_jobs = False
    for raw in source.splitlines():
        if _JOBS_HEADER.match(raw):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if raw and not raw[0].isspace():
            # A column-0 key ends the `jobs:` block.
            in_jobs = False
            continue
        job_match = _JOB_ID_LINE.match(raw)
        if job_match is not None:
            names.add(job_match.group(1))
            continue
        name_match = _JOB_NAME_LINE.match(raw)
        if name_match is not None:
            value = name_match.group(1)
            if "${{" not in value:
                names.add(value)
    return names


def workflow_triggers_pull_request(*, source: str) -> bool:
    """True when a workflow's `on:` includes pull_request or pull_request_target.

    A required status check reported by such a workflow — not only by ci.yml —
    is a LEGITIMATE reporter under livespec NFR section "CI as a merge gate
    (branch protection)": a base-branch-side gate kept deliberately outside
    ci.yml (so the BASE branch's definition runs against an untrusted head via
    `pull_request_target`) reports a real required check, not a phantom. A rule
    that knew only ci.yml read that check as a phantom and would deadlock every
    merge on the member, with no ci.yml change able to satisfy it.

    Handles the inline scalar (`on: pull_request`), inline flow sequence
    (`on: [push, pull_request]`), and block map / sequence forms. The scan is
    confined to the top-level `on:` block, so a job id, step, or `name:` whose
    own text contains `pull_request` is never mistaken for a trigger.
    """
    in_on_block = False
    for raw in source.splitlines():
        inline = _ON_KEY_LINE.match(raw)
        if inline is not None:
            value = inline.group(1)
            if value and not value.startswith("#"):
                # Inline scalar or flow sequence: the whole trigger set is on
                # this one line, so it decides on its own.
                return _PR_EVENT_TOKEN in value
            # A bare `on:` (empty value, or a trailing comment): the events
            # follow as indented lines below.
            in_on_block = True
            continue
        if in_on_block:
            if raw and not raw[0].isspace():
                # The next top-level key ends the `on:` block.
                in_on_block = False
                continue
            if _PR_EVENT_TOKEN in raw:
                return True
    return False
