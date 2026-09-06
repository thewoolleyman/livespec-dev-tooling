"""check_failure_digest — restate each failed check's failure mode at the TAIL.

THE DEFECT THIS EXISTS FOR IS PRESENTATION, NOT DETECTION. The checks already
emit good, self-describing findings: a structlog record carrying `status`,
`failure_mode`, `path` and a `hint` that names the exact remedy. What the
operator actually sees from a git hook is different. `just check` runs ~70
targets, the dispatcher streams each one's captured output as it completes,
and the finding that explains the failure scrolls off. Measured 2026-08-20 in
`livespec-console-beads-fabro`: a fresh worktree failed at check-baseline with
`worktree_pack_absent`, whose remedy is one `just bootstrap` away, and the
pre-push hook surfaced a bare `exit status 1` after 313 seconds of output. The
worker then burned a diagnosis cycle deciding whether it was an environmental
failure or a content regression — a question the scrolled-off record had
already answered.

So this module reads the output the dispatcher ALREADY captured and re-renders
the failure modes and remedies as the LAST lines of the run. It adds no
detection, changes no verdict, and invents no remedy text: every string it
prints came out of the check that failed.

WHY IT LIVES IN THE DISPATCHER RATHER THAN IN THE HOOK SCRIPTS. The two local
git-hook gates (`scripts/just/check-pre-push.sh`,
`scripts/just/check-pre-commit.sh`) both reach the aggregate through one bare
`just check` line, and `scripts/just/check.sh` routes that to
`parallel_check_dispatcher`. Putting the tail there gives BOTH hooks the same
presentation with no shell change at all — no `tee`, no wrapper, no second
copy of the invocation to keep in step with the first. The bare invocation is
load-bearing and is pinned by
`tests/livespec_dev_tooling/test_check_failure_digest.py`.

GROUPING, because a digest that reproduces every finding is another wall of
text. Findings are grouped per target by `(failure_mode, hint)`, carrying the
FIRST path seen as the example and a count of the rest — so a target with 40
`keyword_only_args` violations contributes three lines, not 120.

A failed target that emitted no structured finding is reported AS THAT, never
omitted: the digest must not read as "these were all the failures" when it
could only parse some of them.

Output discipline: this module computes lines; the dispatcher writes them.
"""

from __future__ import annotations

import json
from typing import cast

__all__: list[str] = ["failure_digest_lines"]

_DIGEST_HEADER = "--- failure-mode digest (restated at the tail; the findings above scroll off) ---"
_NO_STRUCTURED_FINDING = (
    "failed without a structured failure_mode — read this target's captured output above"
)
_FAIL_STATUS = "fail"


def _fail_record(*, line: str) -> tuple[str, str, str] | None:
    """Return `(failure_mode, hint, path)` for one structlog `fail` line, else `None`.

    `None` means "this line is not a finding", which covers every non-JSON
    line a check prints, every JSON line that is not an object, every record
    that is not a `fail` (the `warning` tier of `file_lloc` is the loud
    example), and a `fail` carrying no failure mode to restate. None of those
    are faults — the dispatcher captures whatever each target wrote, and most
    of it is prose.
    """
    # EVERY line is offered to the parser rather than pre-filtered on a `{`
    # prefix. The prefix test looks like a cheap win and is not: a JSON text
    # that starts with `{` and parses is an object by definition, so the
    # prefix guard would make the not-an-object rejection below UNREACHABLE —
    # a branch no test could cover, sitting in front of untrusted input.
    try:
        parsed = json.loads(line.strip())
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    record = cast("dict[str, object]", parsed)
    if record.get("status") != _FAIL_STATUS:
        return None
    mode = record.get("failure_mode")
    if not isinstance(mode, str) or not mode:
        return None
    hint = record.get("hint")
    path = record.get("path")
    return (mode, hint if isinstance(hint, str) else "", path if isinstance(path, str) else "")


def _mode_groups(*, output: str) -> list[tuple[str, str, str, int]]:
    """Group one target's findings into `(failure_mode, hint, example_path, count)`.

    Keyed on `(failure_mode, hint)` so the same mode with two different
    remedies stays two entries, and ordered by first appearance so the digest
    reads in the order the check narrated. The FIRST path seen wins as the
    example — later ones are counted, not printed, which is what keeps a
    many-file violation to a few lines.
    """
    groups: dict[tuple[str, str], tuple[str, int]] = {}
    order: list[tuple[str, str]] = []
    for line in output.splitlines():
        record = _fail_record(line=line)
        if record is None:
            continue
        mode, hint, path = record
        key = (mode, hint)
        if key not in groups:
            order.append(key)
            groups[key] = (path, 0)
        example, count = groups[key]
        groups[key] = (example, count + 1)
    return [(mode, hint, groups[(mode, hint)][0], groups[(mode, hint)][1]) for mode, hint in order]


def _entry_lines(*, target: str, group: tuple[str, str, str, int]) -> list[str]:
    """Render one grouped finding: the mode line, then its path and remedy."""
    mode, hint, path, count = group
    suffix = "" if count == 1 else f" ({count} findings)"
    lines = [f"  {target}: {mode}{suffix}"]
    if path:
        lines.append(f"      path: {path}")
    if hint:
        lines.append(f"      remedy: {hint}")
    return lines


def failure_digest_lines(*, failures: list[tuple[str, str]]) -> list[str]:
    """Render the tail-of-output digest for the failed targets of one aggregate run.

    `failures` is `(target_name, captured_output)` for each FAILED target, in
    the order the summary lists them. Returns the lines to write, WITHOUT
    trailing newlines, or an empty list when nothing failed — a green run gets
    no digest, because there is no remedy to keep on screen.
    """
    if not failures:
        return []
    lines = ["", _DIGEST_HEADER]
    for target, output in failures:
        groups = _mode_groups(output=output)
        if not groups:
            lines.append(f"  {target}: {_NO_STRUCTURED_FINDING}")
            continue
        for group in groups:
            lines.extend(_entry_lines(target=target, group=group))
    return lines
