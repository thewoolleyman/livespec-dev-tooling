"""red_green_replay — content-triggered TDD enforcement + commit-range validation.

Content is the trigger; the subject prefix NEVER rejects a commit for
containing product code (user design correction 2026-06-11, follow-up
to work-item livespec-dev-tooling-eld — changing product code as part
of a chore is legitimate; it is simply subject to the same TDD
discipline as bugs and features).

commit-msg mode (argv[1] = path to `.git/COMMIT_EDITMSG`, the lefthook
`commit-msg` hook) — the decision tree:

1. nothing staged / no `.py` in the tests or impl buckets ⇒ pass
   immediately, any prefix (machine checkpoint subjects such as
   `fabro(<run_id>): <node> (<status>)`, docs, and empty commits);
2. tests-only `.py` staged + pytest on the staged tests FAILS ⇒ the
   Red leg records `TDD-Red-*` trailers — ANY prefix may author a
   Red (a behavior-changing chore does Red->Green like a feature);
3. tests-only `.py` staged + pytest PASSES ⇒ `feat:`/`fix:` keeps the
   loud `test-passed-at-red` reject (the author DECLARED a behavior
   change, so their test must fail first); any other prefix is a
   test-only cleanup and takes the green-verified leg;
4. product impl `.py` staged with `TDD-Red-*` trailers WITHOUT
   `TDD-Green-*` trailers at HEAD — a genuine amend-in-progress
   (work-item livespec-dev-tooling-xn0: a completed Red+Green
   commit at HEAD also carries Red trailers, so presence alone
   misroutes fresh commits into this leg) ⇒ the Green leg:
   byte-identical test re-run must pass, `TDD-Green-*` recorded —
   prefix-agnostic;
5. product impl `.py` staged WITHOUT a Red-awaiting-Green HEAD
   (pure refactor / behavior-preserving chore / any prefix incl.
   feat:/fix:, including fresh commits atop completed Red+Green or
   suite-green history) ⇒ the green-verified leg: the FULL pytest
   suite must pass against the staged tree; `TDD-Suite-Green-*`
   trailers are recorded; a failing (or uncollectable) suite
   rejects actionably (`suite-red`).

no-arg mode (the canonical-aggregate / `just check` / pre-push / CI
invocation): validates the commit range `origin/master..HEAD` — every
non-merge commit touching product impl `.py` must carry EITHER the
`TDD-Red-*`/`TDD-Green-*` pair shape OR the `TDD-Suite-Green-*` shape,
regardless of prefix. An unresolvable base ref fails actionably (a
shallow CI checkout needs `fetch-depth: 0`), never silently passes.

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

# Importing from sibling `_*` module for the heavy leg handlers
# (cycle 4c LLOC reduction). The leading underscore in the module
# name marks it as a private helper rather than a check entry
# point.
from _red_green_replay_modes import (  # noqa: E402  — sibling private import
    RED_GREEN_REPLAY_PROTOCOL,
    _handle_green_mode,
    _handle_red_mode,
    _handle_suite_green_mode,
)
from _red_green_replay_trailers import (  # noqa: E402  — sibling private import
    head_red_awaiting_green,
)

__all__: list[str] = []


# The prefix's ONLY remaining semantic: a `feat:`/`fix:` subject
# staging a PASSING test alone declares a behavior change whose test
# must fail first (`test-passed-at-red`). No prefix ever rejects a
# commit for containing product code.
_RED_INTENT_TYPE_RE = re.compile(r"^(feat|fix)(\([^)]+\))?!?:")
_TESTS_PREFIX = "tests/"
# Impl-tree prefixes spanning every livespec-governed sibling repo
# that consumes this check via the pin-and-bump cross-repo mechanism
# (livespec/SPECIFICATION/contracts.md §"Cross-repo coordination —
# pin-and-bump"). Each repo's impl tree lives at a repo-specific
# prefix; without recognition here, commits in those repos that touch
# the package source classify as test-only and dispatch to the wrong
# leg.
#
# livespec (core):             .claude-plugin/scripts/livespec/,
#                              .claude-plugin/scripts/bin/, dev-tooling/
# livespec-runtime:            livespec_runtime/
# livespec-dev-tooling (self): livespec_dev_tooling/
# livespec-orchestrator-git-jsonl: .claude-plugin/scripts/livespec_orchestrator_git_jsonl/
#                              (bin/ for orchestrator-git-jsonl is covered by
#                              .claude-plugin/scripts/bin/)
# livespec-orchestrator-beads-fabro: .claude-plugin/scripts/livespec_orchestrator_beads_fabro/
#                              (bin/ for orchestrator-beads-fabro is covered by
#                              .claude-plugin/scripts/bin/)
#
# The orchestrator-rename wave renamed the impl-side plugin package
# dirs from `livespec_impl_<X>` to `livespec_orchestrator_<X>`:
#   livespec_impl_git_jsonl  -> livespec_orchestrator_git_jsonl
#   livespec_impl_beads      -> livespec_orchestrator_beads_fabro
# `_IMPL_PREFIXES` recognizes the renamed orchestrator package dirs.
# The old `livespec_impl_*` package dirs no longer exist in any repo,
# so their prefixes are not carried.
#
# Bare `livespec/` / `bin/` legacy prefixes remain for paired-test
# fixture compatibility — tmp_path tests synthesize paths like
# `livespec/foo.py`. Production has no top-level `livespec/` or
# `bin/` dirs, so the legacy prefixes contribute zero false
# positives in real repos.
_IMPL_PREFIXES = (
    ".claude-plugin/scripts/livespec/",
    ".claude-plugin/scripts/livespec_orchestrator_git_jsonl/",
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/",
    ".claude-plugin/scripts/bin/",
    "livespec/",
    "livespec_runtime/",
    "livespec_dev_tooling/",
    "bin/",
    "dev-tooling/",
)
_RED_TRAILER_KEY = "TDD-Red-Test-File-Checksum:"
_GREEN_TRAILER_KEY = "TDD-Green-Verified-At:"
_SUITE_TRAILER_KEY = "TDD-Suite-Green-Captured-At:"
_RANGE_BASE = "origin/master"


def _classify_staged(*, paths: list[str]) -> tuple[list[str], list[str]]:
    """Bucket staged `.py` paths into (tests, impl) — other paths are dropped.

    Content is the trigger, so only `.py` files participate: a path
    is a tests-bucket member iff it ends in `.py` AND starts with
    `tests/`; an impl-bucket member iff it ends in `.py` AND starts
    with one of `_IMPL_PREFIXES`. Anything else (config, docs, data
    files — even under an impl prefix) participates in neither
    bucket and cannot trigger leg dispatch.
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
    """Return staged paths, EXCLUDING deletions (`--diff-filter=d`).

    A staged deletion carries no content to Red/Green- or
    suite-verify, so it must drop out of classification entirely.
    `git diff --cached --name-only` alone INCLUDES deletions, which
    routed a deleted `tests/*.py` into the Red leg — whose handler then
    `read_bytes` the absent file and crashed with an uncaught
    FileNotFoundError, so a `.py` deletion could not be committed
    (work-item livespec-zs22.7.9.7). The lowercase `d` filter excludes
    deleted paths while keeping additions and modifications.
    """
    return _git_stdout_lines(args=["diff", "--cached", "--name-only", "--diff-filter=d"])


def _staged_tests_pass(*, tests_paths: list[str]) -> bool:
    """Return True iff pytest passes on the staged tests-tree files.

    Discriminates branch 2 (failing ⇒ the Red leg, any prefix) from
    branch 3 (passing ⇒ `test-passed-at-red` for declared Red intent,
    the green-verified leg otherwise) for tests-only stagings.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *[str(Path.cwd() / p) for p in tests_paths],
            "--tb=no",
            "-q",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _commit_violates(*, sha: str) -> bool:
    """Return True iff `sha` touches product impl `.py` without a valid trailer shape.

    Valid shapes: the `TDD-Red-*`/`TDD-Green-*` pair (a completed
    Red->Green commit) or `TDD-Suite-Green-*` (a green-verified
    behavior-preserving commit). `--root` makes a root commit diff
    against the empty tree, so a range that begins at a repo's first
    commit is still enumerable. `--diff-filter=d` excludes DELETED
    paths (lowercase = exclude): a commit that only deletes product
    impl `.py` carries no Red/Green evidence to require, so the range
    validator must not flag it (work-item livespec-zs22.7.9.7) — the
    same deletion carve-out the commit-msg path applies in
    `_staged_files_list`.
    """
    touched = _git_stdout_lines(
        args=["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "--diff-filter=d", sha],
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
    has_pair_shape = _RED_TRAILER_KEY in message and _GREEN_TRAILER_KEY in message
    has_suite_shape = _SUITE_TRAILER_KEY in message
    return not (has_pair_shape or has_suite_shape)


def _validate_range() -> int:
    """Validate every non-merge commit in `origin/master..HEAD` (no-argv path).

    Content-based: a commit touching product impl `.py` must carry
    EITHER the TDD-Red-*/TDD-Green-* pair shape OR the
    TDD-Suite-Green-* shape, regardless of its subject prefix — the
    load-bearing branch-level gate behind the per-commit commit-msg
    hook (which a rebase, a squash, or a history rewrite can bypass).
    Merge commits are skipped (`--no-merges`): the fleet's protected
    branches enforce linear history, so a merge in the range carries
    no diff of its own. On `master` itself the range is empty and the
    gate trivially passes.
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
        "commits in origin/master..HEAD touch product impl .py without a "
        "valid TDD trailer shape: either the TDD-Red-*/TDD-Green-* pair "
        "(a completed Red->Green commit) or TDD-Suite-Green-* (a "
        "green-verified behavior-preserving commit)",
        check_id="red-green-replay-range-missing-trailers",
        violating_commits=violating,
        hint=(
            "Every commit touching product impl .py must carry evidence, "
            "regardless of subject prefix: author behavior changes via the "
            "Red->Green ritual (pair shape), or behavior-preserving changes "
            "via the green-verified leg (suite shape). Remedy: rewrite the "
            "unmerged feature branch (redo each offending change through the "
            "hook so it earns its trailers) and force-push the branch — the "
            "'never force-push' rule scopes to shared/protected refs, not to "
            "an unmerged feature branch being brought into shape."
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
    staged_paths = _staged_files_list()
    tests_paths, impl_paths = _classify_staged(paths=staged_paths)
    if not impl_paths and not tests_paths:
        # Branch 1 — content trigger absent: nothing the legs can
        # verify. Pass for ANY subject prefix — machine checkpoint
        # subjects and empty commits included.
        return 0
    log = _configure_logger()
    if not impl_paths:
        declares_red_intent = _RED_INTENT_TYPE_RE.match(subject) is not None
        if declares_red_intent or not _staged_tests_pass(tests_paths=tests_paths):
            # Branch 2 (failing tests ⇒ Red leg, any prefix) and
            # branch 3's feat:/fix: arm (declared Red intent: the
            # handler records Red trailers on failure and rejects a
            # passing test with `test-passed-at-red`).
            return _handle_red_mode(msg_path=msg_path, log=log, tests_paths=tests_paths)
        # Branch 3, other prefixes — a passing test-only cleanup is
        # green-verified.
        return _handle_suite_green_mode(msg_path=msg_path, log=log, staged_paths=staged_paths)
    if head_red_awaiting_green():
        # Branch 4 — a genuine amend-in-progress (Red WITHOUT Green at
        # HEAD), prefix-agnostic. Red-trailer PRESENCE alone is not
        # enough: a completed Red+Green commit at HEAD also carries
        # Red trailers (work-item livespec-dev-tooling-xn0).
        return _handle_green_mode(msg_path=msg_path, log=log, impl_paths=impl_paths)
    # Branch 5 — product impl `.py` without a Red awaiting its Green
    # (refactor / behavior-preserving chore / any prefix / fresh
    # commits atop completed history): green-verified.
    return _handle_suite_green_mode(msg_path=msg_path, log=log, staged_paths=staged_paths)


if __name__ == "__main__":
    raise SystemExit(main())
