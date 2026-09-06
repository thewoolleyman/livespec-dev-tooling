"""The `git diff --name-only` read of a branch range, on the `IOResult` railway.

`check_coverage_incremental` derives the ENTIRE gated set from one
`git diff --name-only --diff-filter=d <range>` invocation, so that one read
decides what the per-file 100% coverage gate measures. It is therefore the
kind of read whose FAILURE must be distinguishable from its EMPTY ANSWER, and
the reason this lives in its own module rather than inline at the call site.

WHAT THE OLD SPELLING COULD NOT SAY. The invocation ran with `check=False` and
only `.stdout` was taken — the `returncode` was never read. Every failure of
the diff therefore yielded an empty string, which the caller filtered to an
empty path list, which `main()` reported as

    no changed impl .py paths derived from git diff; nothing to gate

and returned 0 on. The gate passed VACUOUSLY, while stating in as many words
that it had looked and there was nothing there. **A failed enumeration does
not go quiet; it manufactures a confident empty answer.**

AND IT IS REACHABLE RATHER THAN THEORETICAL. `origin/master` is a
REMOTE-TRACKING ref, not a local branch: it is absent from a shallow clone,
from a fresh clone that has not fetched it, from a checkout whose remote is
named anything but `origin`, and from any CI job cloning at `fetch-depth: 1`.
`git diff origin/master...HEAD` then exits 128 with empty stdout.

WHAT IS AND IS NOT A FAILURE HERE. There is exactly ONE exit of
`git diff --name-only <range>` that legitimately answers "this branch changed
nothing": exit 0 with empty stdout. That read HAPPENED and its emptiness is a
verdict. Every non-zero exit is `git` declining to answer, and so is an
`OSError` from `git` not being runnable at all — neither may be spelled as an
empty diff.

Kept as a `_`-prefixed sibling of the check that uses it, on the same reading
as `_docs_only_change.py`: it shells out to `git` DIRECTLY rather than through
an injected seam, so it IS the I/O boundary and `IOResult` rather than
`Result` is the honest container.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Carried rather than inherited from an importer: without it the vendored
# `returns` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this
# file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "DiffUnavailable",
    "name_only_diff",
]


@dataclass(frozen=True, kw_only=True)
class DiffUnavailable:
    """The diff could not be READ, and WHICH of two reasons.

    `reason` is the discriminator a caller branches on; `detail` is the
    operator-facing evidence, and the two are deliberately separate so a
    diagnostic can name the cause without the caller parsing prose.

    The two are kept apart because they want DIFFERENT operator responses:
    `git-not-run` is a broken environment (no `git` on PATH, a `cwd` that is
    not a directory), while `diff-failed` is a `git` that ran and refused —
    overwhelmingly an unfetched or misnamed base ref, which is fixed by
    fetching it rather than by repairing the toolchain.
    """

    reason: Literal["git-not-run", "diff-failed"]
    detail: str


def name_only_diff(*, diff_range: str, cwd: Path) -> IOResult[str, DiffUnavailable]:
    """The `--name-only` diff of `diff_range` in `cwd`, deletions excluded.

    `IOSuccess` carries the raw newline-separated blob `git` printed — EMPTY
    when the range genuinely holds no non-deleted paths, which is an answer
    `git` gave rather than one this function assumed. `IOFailure` says the
    diff could not be taken at all.

    Deletions are excluded (`--diff-filter=d`) because a deleted path has no
    file left to measure; that filter is part of the question this module
    asks, not a caller-tunable knob.

    The git subprocess is handed an env with every `GIT_*` var stripped: a
    parent process (notably a git commit hook) can inject `GIT_DIR` /
    `GIT_INDEX_FILE` / `GIT_WORK_TREE`, which would override `cwd` and make
    the diff target the WRONG repository. Clearing those keeps the diff
    scoped to the repository at `cwd`.

    The catch is NARROW and ENUMERATED (`OSError`), the sanctioned
    hand-rolled seam lift: `git` absent from PATH, a `git` that cannot be
    exec'd, a `cwd` that is not a directory, a fork failure. A bug raised in
    here still propagates.
    """
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        # S603/S607: argv is a fixed list of literal git args; no shell input.
        completed = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=d", diff_range],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd),
            env=git_env,
        )
    except OSError as unusable:
        return IOFailure(DiffUnavailable(reason="git-not-run", detail=str(unusable)))
    if completed.returncode != 0:
        return IOFailure(
            DiffUnavailable(
                reason="diff-failed",
                detail=(
                    f"{diff_range}: git diff --name-only exited"
                    f" {completed.returncode} ({completed.stderr.strip()})"
                ),
            )
        )
    return IOSuccess(completed.stdout)
