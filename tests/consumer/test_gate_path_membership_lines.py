"""Two gate-path membership tests must give the same verdict on a large input as on a small one.

Governing scenario, `SPECIFICATION/scenarios.md`: "a pipefail script reports
a match in a large input as a match".

THE DEFECT (livespec-dev-tooling-7xv7sy). Each line below tested membership
by piping a captured variable into an early-exiting `grep -q` under
`set -euo pipefail`. bash's builtin `printf` writes line by line, so once
grep matched a line that was not the last, a later write took SIGPIPE, the
pipeline exited 141, and pipefail turned the match into a miss:

- `worktree-lib.sh` `reap`: `! printf ... "$cherry_out" | grep -q '^+'`. A miss
  read a branch carrying UNLANDED commits as patch-id equivalent to the base,
  so the reaper would remove a worktree holding unlanded work.
- the master-health reconciler: `printf ... "${green_shas}" | grep -qx "${sha}"`.
  A miss treated a green commit as a culprit candidate.

Each test lifts the SHIPPED condition line out of its source, verbatim, and
runs it under `set -euo pipefail` against an input whose match is on the
first line and is followed by far more than a pipe buffer of further lines.
That makes the race certain, not intermittent, and it grades the bytes that
ship rather than a restatement of them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_dev_tooling.fleet._reconciler_shim import REUSABLE_RECONCILER_BODY

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKTREE_LIB = _REPO_ROOT / "livespec_dev_tooling" / "worktree_pack" / "worktree-lib.sh"

# Far past any pipe buffer, after the matching first line.
_PADDING_LINES = 200000


def _condition(*, body: str, needles: tuple[str, ...]) -> str:
    """The one `if <condition>; then` line of `body` carrying every needle, as its condition."""
    lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip().startswith("if ") and all(needle in line for needle in needles)
    ]
    assert len(lines) == 1, f"expected one condition line for {needles}; got {lines!r}"
    return lines[0].removeprefix("if ").removesuffix("; then")


def _branch_taken(*, setup: str, condition: str) -> str:
    """Run `condition` after `setup` under `set -euo pipefail`; report which branch ran."""
    script = (
        f"set -euo pipefail\n{setup}\n"
        f"if {condition}; then echo TAKEN; else echo NOT_TAKEN; fi\n"
    )
    completed = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    return completed.stdout.strip() or f"no verdict: rc={completed.returncode}"


def test_reap_reads_a_branch_with_unlanded_commits_as_unmerged_however_long() -> None:
    """A `+` line in `git cherry` output means unlanded work, wherever it sits."""
    condition = _condition(
        body=_WORKTREE_LIB.read_text(encoding="utf-8"), needles=('"$cherry_out"', "'^+'")
    )
    setup = (
        "cherry_out=$(printf '+ %s\\n' 0123456789abcdef0123456789abcdef01234567; "
        f"seq -f '+ %040g' 1 {_PADDING_LINES})"
    )

    verdict = _branch_taken(setup=setup, condition=condition)

    # TAKEN would set merged=1: an unmerged worktree reaped as landed.
    assert verdict == "NOT_TAKEN", f"condition={condition!r} verdict={verdict!r}"


def test_the_reconciler_counts_a_green_sha_as_green_whatever_its_position() -> None:
    """A sha in the green-run set is skipped as a culprit candidate, wherever it sits."""
    condition = _condition(body=REUSABLE_RECONCILER_BODY, needles=("${green_shas}", '"${sha}"'))
    setup = (
        "sha=0123456789abcdef0123456789abcdef01234567\n"
        f"green_shas=$(printf '%s\\n' \"$sha\"; seq -f '%040g' 1 {_PADDING_LINES})"
    )

    verdict = _branch_taken(setup=setup, condition=condition)

    assert verdict == "TAKEN", f"condition={condition!r} verdict={verdict!r}"
