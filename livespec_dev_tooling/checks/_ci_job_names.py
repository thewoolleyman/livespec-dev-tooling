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
Per `livespec/SPECIFICATION/non-functional-requirements.md` §"CI as a merge
gate (branch protection)", a required check is legitimate when it matches a
CI matrix leg OR a top-level CI job, and is flagged only when it matches
NEITHER: "A required top-level all-green gate job (the `ci-green`
single-gate model) is a valid required check and is NOT flagged, even
though it is not a matrix leg, because requiring it gates the whole matrix
through its `needs:`."

The parsers are regex line-walks (the package convention) and are PURE — no
IO, no logging — so each caller owns its own file access and diagnostics.
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

# Names in `__all__` mark this private sibling's public surface to its two
# importers — `checks/branch_protection_alignment.py` and
# `fleet/_rows_github.py` — so pyright's per-file analysis does not flag
# them unused across the package boundary.
__all__: list[str] = [
    "parse_ci_matrix",
    "parse_top_level_jobs",
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
