"""red_green_replay — content-triggered TDD enforcement + commit-range validation.

Two invocation modes, one content rule (work-item
livespec-dev-tooling-eld; design decided 2026-06-11): product impl
`.py` is the TRIGGER, the Conventional Commit prefix is a CONSISTENCY
check.

commit-msg mode (argv[1] = path to `.git/COMMIT_EDITMSG`, the lefthook
`commit-msg` hook): staged product impl `.py` requires a `feat:`/`fix:`
subject and dispatches the Red-mode or Green-mode handler in
`_red_green_replay_modes` (test-file SHA-256 checksum, pytest
invocation, trailer authoring); any OTHER prefix staging product impl
`.py` is rejected as a mislabel. With NO product impl `.py` staged the
hook exits 0 immediately regardless of prefix — machine checkpoint
subjects (e.g. `fabro(<run_id>): <node> (<status>)`) and empty commits
pass — except that a `feat:`/`fix:` subject staging tests-only `.py`
enters Red mode (the declared start of the ritual). The prior
exempt-type fallthrough (chore, docs, build, ci, style, test, refactor,
perf, revert exited 0 with no staged-path inspection) is retired.

no-arg mode (the canonical-aggregate / `just check` / pre-push / CI
invocation): validates the commit range `origin/master..HEAD` — every
non-merge commit touching product impl `.py` must carry the full
`TDD-Red-*`/`TDD-Green-*` trailer shape regardless of prefix. An
unresolvable base ref fails actionably (a shallow CI checkout needs
`fetch-depth: 0`), never silently passes.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics
flow through structlog (JSON to stderr); the vendored copy under
`_vendor/` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
# Make the script's own directory importable when this module is
# loaded via `importlib.util.spec_from_file_location` (test path)
# in addition to the natural `python3 dev-tooling/checks/red_green_replay.py`
# subprocess invocation (which adds the dir automatically).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

# Importing from sibling `_*` module for the heavy mode handlers
# (cycle 4c LLOC reduction). The leading underscore in the module
# name marks it as a private helper rather than a check entry
# point.
from _red_green_replay_modes import (  # noqa: E402  — sibling private import
    RED_GREEN_REPLAY_PROTOCOL,
    _handle_green_mode,
    _handle_red_mode,
    _head_has_red_trailers,
)

__all__: list[str] = []


# The ONLY subjects that may stage product impl `.py` — and the
# declared start of the ritual when staging tests-only `.py`.
_RITUAL_TYPE_RE = re.compile(r"^(feat|fix)(\([^)]+\))?!?:")
_TESTS_PREFIX = "tests/"
# Impl-tree prefixes spanning every livespec-governed sibling repo
# that consumes this check via the pin-and-bump cross-repo mechanism
# (livespec/SPECIFICATION/contracts.md §"Cross-repo coordination —
# pin-and-bump"). Each repo's impl tree lives at a repo-specific
# prefix; without recognition here, `feat:`/`fix:` commits in those
# repos that touch the package source classify as test-only and
# incorrectly trip the Red-without-Green diagnostic.
#
# livespec (core):             .claude-plugin/scripts/livespec/,
#                              .claude-plugin/scripts/bin/, dev-tooling/
# livespec-runtime:            livespec_runtime/
# livespec-dev-tooling (self): livespec_dev_tooling/
# livespec-impl-git-jsonl:     .claude-plugin/scripts/livespec_impl_git_jsonl/
#                              (bin/ for impl-git-jsonl is covered by
#                              .claude-plugin/scripts/bin/)
# livespec-impl-beads:         .claude-plugin/scripts/livespec_impl_beads/
#                              (bin/ for impl-beads is covered by
#                              .claude-plugin/scripts/bin/)
#
# Bare `livespec/` / `bin/` legacy prefixes remain for paired-test
# fixture compatibility — tmp_path tests synthesize paths like
# `livespec/foo.py`. Production has no top-level `livespec/` or
# `bin/` dirs, so the legacy prefixes contribute zero false
# positives in real repos.
_IMPL_PREFIXES = (
    ".claude-plugin/scripts/livespec/",
    ".claude-plugin/scripts/livespec_impl_git_jsonl/",
    ".claude-plugin/scripts/livespec_impl_beads/",
    ".claude-plugin/scripts/bin/",
    "livespec/",
    "livespec_runtime/",
    "livespec_dev_tooling/",
    "bin/",
    "dev-tooling/",
)
_RED_TRAILER_KEY = "TDD-Red-Test-File-Checksum:"
_GREEN_TRAILER_KEY = "TDD-Green-Verified-At:"
_RANGE_BASE = "origin/master"


def _classify_staged(*, paths: list[str]) -> tuple[list[str], list[str]]:
    """Bucket staged `.py` paths into (tests, impl) — other paths are dropped.

    Content is the trigger, so only `.py` files participate: a path
    is a tests-bucket member iff it ends in `.py` AND starts with
    `tests/`; an impl-bucket member iff it ends in `.py` AND starts
    with one of `_IMPL_PREFIXES`. Anything else (config, docs, data
    files — even under an impl prefix) participates in neither
    bucket and cannot trigger Red-mode or Green-mode dispatch.
    """
    tests_paths = [p for p in paths if p.endswith(".py") and p.startswith(_TESTS_PREFIX)]
    impl_paths = [p for p in paths if p.endswith(".py") and p.startswith(_IMPL_PREFIXES)]
    return tests_paths, impl_paths


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("red_green_replay")


def _git_stdout_lines(*, args: list[str]) -> list[str]:
    """Run a git command and return its non-empty stdout lines."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line]


def _staged_files_list() -> list[str]:
    return _git_stdout_lines(args=["diff", "--cached", "--name-only"])


def _commit_violates(*, sha: str) -> bool:
    """Return True iff `sha` touches product impl `.py` without the trailer shape.

    `--root` makes a root commit diff against the empty tree, so a
    range that begins at a repo's first commit is still enumerable.
    """
    touched = _git_stdout_lines(
        args=["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha],
    )
    product_paths = [p for p in touched if p.endswith(".py") and p.startswith(_IMPL_PREFIXES)]
    if not product_paths:
        return False
    message_result = subprocess.run(
        ["git", "log", "-1", "--format=%B", sha],
        capture_output=True,
        text=True,
        check=False,
    )
    message = message_result.stdout
    return _RED_TRAILER_KEY not in message or _GREEN_TRAILER_KEY not in message


def _validate_range() -> int:
    """Validate every non-merge commit in `origin/master..HEAD` (no-argv path).

    Content-based: a commit touching product impl `.py` must carry
    the full TDD-Red-*/TDD-Green-* trailer shape regardless of its
    subject prefix — the load-bearing branch-level gate behind the
    per-commit commit-msg hook (which a rebase, a squash, or a
    history rewrite can bypass). Merge commits are skipped
    (`--no-merges`): the family's protected branches enforce linear
    history, so a merge in the range carries no diff of its own. On
    `master` itself the range is empty and the gate trivially passes.
    """
    base_probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", _RANGE_BASE],
        capture_output=True,
        text=True,
        check=False,
    )
    if base_probe.returncode != 0:
        log = _configure_logger()
        log.error(
            "range base origin/master is not resolvable; the commit-range "
            "validation cannot enumerate origin/master..HEAD and MUST NOT "
            "silently pass",
            check_id="red-green-replay-range-base-unresolvable",
            range_base=_RANGE_BASE,
            hint=(
                "Fetch the base ref first (git fetch origin master). In CI, "
                "check out with full history (actions/checkout fetch-depth: 0) "
                "so origin/master and the merge base are present in the clone."
            ),
        )
        return 1
    shas = _git_stdout_lines(args=["rev-list", "--no-merges", f"{_RANGE_BASE}..HEAD"])
    violating = [sha for sha in shas if _commit_violates(sha=sha)]
    if not violating:
        return 0
    log = _configure_logger()
    log.error(
        "commits in origin/master..HEAD touch product impl .py without the "
        "TDD-Red-*/TDD-Green-* trailer shape a completed Red->Green commit "
        "carries",
        check_id="red-green-replay-range-missing-trailers",
        violating_commits=violating,
        hint=(
            "Every commit touching product impl .py must be authored via the "
            "Red->Green ritual regardless of subject prefix. Remedy: rewrite "
            "the unmerged feature branch (redo each offending change as a Red "
            "commit + Green amend) and force-push the branch — the 'never "
            "force-push' rule scopes to shared/protected refs, not to an "
            "unmerged feature branch being brought into shape."
        ),
        protocol=RED_GREEN_REPLAY_PROTOCOL,
    )
    return 1


def main() -> int:
    if len(sys.argv) <= 1:
        # No msg-path argv: the canonical-aggregate / `just check` /
        # pre-push / CI invocation validates the whole branch range
        # rather than a single in-flight commit.
        return _validate_range()
    msg_path = Path(sys.argv[1])
    subject = msg_path.read_text(encoding="utf-8").split("\n", 1)[0]
    tests_paths, impl_paths = _classify_staged(paths=_staged_files_list())
    is_ritual_subject = _RITUAL_TYPE_RE.match(subject) is not None
    if not impl_paths:
        if is_ritual_subject and tests_paths:
            return _handle_red_mode(
                msg_path=msg_path,
                log=_configure_logger(),
                tests_paths=tests_paths,
            )
        # Content trigger absent: no product impl `.py` staged, so the
        # ritual has nothing to verify. Pass for ANY subject prefix —
        # machine checkpoint subjects and empty commits included.
        return 0
    log = _configure_logger()
    if not is_ritual_subject:
        log.error(
            "staged product impl .py under a non-feat:/fix: subject; product "
            "code changes MUST be authored via the Red->Green ritual",
            check_id="red-green-replay-product-mislabel",
            subject=subject,
            impl_paths=impl_paths,
            hint=(
                "Relabel the commit as feat:/fix: and author it as a Red "
                "commit (stage the failing test alone) followed by a Green "
                "amend (stage the impl). If the staged .py is not product "
                "code, move it out of the impl trees instead."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    if _head_has_red_trailers():
        return _handle_green_mode(msg_path=msg_path, log=log, impl_paths=impl_paths)
    return _diagnose_fallthrough(log=log, tests_paths=tests_paths, impl_paths=impl_paths)


def _diagnose_fallthrough(
    *,
    log: structlog.stdlib.BoundLogger,
    tests_paths: list[str],
    impl_paths: list[str],
) -> int:
    """Reject a feat:/fix: product-`.py` staging that fits neither Red nor Green.

    Two classifiable cases remain once product impl `.py` is staged
    under a ritual subject but HEAD carries no Red trailers; each is
    named via a stable check_id so the developer recovers without
    spelunking the source.
    """
    if tests_paths:
        log.error(
            "tests and impl paths both staged without prior Red trailers; "
            "Red mode requires tests-only; Green mode requires impl-only after Red",
            check_id="red-green-replay-mixed-buckets",
            tests_paths=tests_paths,
            impl_paths=impl_paths,
            hint=(
                "Stage the failing test alone and commit (Red), then stage the "
                "impl and amend (Green) — the Green amend produces one final "
                "commit carrying both files plus the R-G trailers."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    log.error(
        "impl staged but HEAD has no Red trailers; " "Green mode requires a preceding Red commit",
        check_id="red-green-replay-green-without-red",
        impl_paths=impl_paths,
        hint=(
            "Author a Red commit first: stage the failing test alone, commit, "
            "then stage the impl and amend (Green). The Green amend reads the "
            "Red trailers from HEAD~0 to verify the test now passes."
        ),
        protocol=RED_GREEN_REPLAY_PROTOCOL,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
