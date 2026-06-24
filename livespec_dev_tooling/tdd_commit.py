"""tdd_commit — mechanize the Red-commit-then-Green-amend TDD ritual.

The livespec fleet commits product `.py` changes via a 2-step,
single-commit TDD ritual enforced by the `red_green_replay` commit-msg
hook (`livespec_dev_tooling/checks/red_green_replay.py`): the test file
is staged ALONE and committed (Red), then the implementation file(s)
are staged and the commit is amended (Green). The final result is ONE
commit carrying the test, the impl, and both `TDD-Red-*` / `TDD-Green-*`
trailer sets.

Hand-orchestrating that sequence (`git add <test>` → commit → `git add
<impl>` → `git commit --amend`) is error-prone: forgetting to stage the
impl ALONE-vs-together, amending before the Red commit landed, or
running bare `git` so lefthook silently misses the trailer hooks. This
helper mechanizes the two steps so the ritual is a single command:

    python -m livespec_dev_tooling.tdd_commit \\
        --test tests/livespec_dev_tooling/test_foo.py \\
        --impl livespec_dev_tooling/foo.py \\
        --subject "feat: add foo"

Steps:

1. Red — `git add <test>` (the test file ALONE; the impl is left
   UNMODIFIED on disk so the staged tree's pytest fails meaningfully),
   then `git commit -m <subject>`. The commit-msg hook runs pytest on
   the staged tree, observes the failing test, and records the
   `TDD-Red-*` trailers.
2. Green — `git add <impl> [<impl> ...]`, then `git commit --amend
   --no-edit`. The hook re-runs the SAME test (now passing) and records
   the `TDD-Green-*` trailers.

`--impl` is repeatable so a single feature touching several impl files
amends them all into the one Green commit. `--subject` MUST be a
`feat:` or `fix:` Conventional-Commit subject — the only two types the
red-green-replay hook gates; any other type is exempt and does not need
this helper.

Git invocation: by default each git call runs through `mise exec -- git`
so lefthook's commit-msg shim fires and the `TDD-*` trailers are
written. `--no-mise` (or the `LIVESPEC_TDD_COMMIT_GIT` env var) swaps in
a bare `git` invocation — used by the helper's own test suite, which
drives a hook-less throwaway tmp_path repo where no `mise` config or
lefthook gate exists.

Hook-context confinement: each spawned git runs with the GIT_*
hook-passthrough vars (GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE / …)
scrubbed from its environment, so git is confined to the `--repo`
working tree even when the helper is invoked from inside a git hook
(which git decorates with those vars pointing at the SURROUNDING repo).
Without the scrub a nested invocation — notably the helper's own test
suite running under the red-green-replay commit-msg hook — would commit
into the wrong repo.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow
through structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at
module import time.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "main",
    "run_tdd_commit",
]


# Default git invocation prefix. `mise exec -- git` is required in real
# livespec repos so lefthook's commit-msg shim fires and the
# red-green-replay hook writes the `TDD-*` trailers; a bare `git` would
# silently skip the hook (and the trailers).
_MISE_GIT_PREFIX: tuple[str, ...] = ("mise", "exec", "--", "git")
_BARE_GIT_PREFIX: tuple[str, ...] = ("git",)

# Env var that overrides the git invocation prefix entirely (shell-quoted
# argv, parsed via `shlex.split`). Lets the helper's own tests point at a
# bare `git` without `--no-mise`, and lets a non-default toolchain wrap
# git however it needs.
_GIT_OVERRIDE_ENV: str = "LIVESPEC_TDD_COMMIT_GIT"

# GIT_* environment variables that git injects into a hook process (and any
# children it spawns) to pin every nested `git ...` call to the SURROUNDING
# repository. The helper drives git against the caller-supplied `--repo`
# working tree, so any inherited GIT_DIR / GIT_INDEX_FILE / etc. would
# redirect the Red commit + Green amend into the wrong repo (and re-trigger
# the outer repo's hooks). Scrubbing these confines git to `--repo`. This
# matters whenever the helper is invoked from inside a git hook — including
# the helper's OWN test suite, which runs under the red-green-replay
# commit-msg hook when the helper is itself committed via the ritual.
_GIT_ENV_PASSTHROUGH_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)


def _scrubbed_git_env(*, env: dict[str, str]) -> dict[str, str]:
    """Return a copy of `env` with the GIT_* hook-passthrough vars removed.

    Confines a spawned `git` to the helper's `--repo` working tree even when
    the helper runs inside a git hook (which would otherwise leak GIT_DIR /
    GIT_INDEX_FILE / friends pointing at the surrounding repo).
    """
    return {k: v for k, v in env.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("tdd_commit")


def _resolve_git_prefix(*, no_mise: bool, env: dict[str, str]) -> list[str]:
    """Resolve the git-invocation argv prefix.

    Precedence: the `LIVESPEC_TDD_COMMIT_GIT` env override (shell-quoted
    argv) wins; otherwise `--no-mise` selects a bare `git`, and the
    default is `mise exec -- git` so lefthook fires.
    """
    override = env.get(_GIT_OVERRIDE_ENV)
    if override is not None and override.strip():
        return shlex.split(override)
    if no_mise:
        return list(_BARE_GIT_PREFIX)
    return list(_MISE_GIT_PREFIX)


def _run_git(
    *,
    git_prefix: list[str],
    args: list[str],
    repo: Path,
    env: dict[str, str],
    log: structlog.stdlib.BoundLogger,
    step: str,
) -> int:
    """Run one git invocation in `repo`; return its exit code.

    `env` is the base environment for the child git (the GIT_* hook
    passthrough vars are scrubbed first so git is confined to `repo`).
    On a non-zero exit the captured stdout/stderr are surfaced via a
    structured `tdd-commit-git-failed` error so the caller sees the
    underlying git/hook rejection (e.g. a red-green-replay
    `test-passed-at-red`) verbatim.
    """
    argv = [*git_prefix, *args]
    # The argv is a fixed list (the configured git prefix + literal git
    # subcommand flags + caller-supplied file paths); there is no shell
    # interpolation. `shell=False` (the default) keeps it injection-free.
    completed = subprocess.run(  # noqa: S603
        argv,
        cwd=str(repo),
        env=_scrubbed_git_env(env=env),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        log.error(
            "git invocation failed during TDD-commit ritual",
            check_id="tdd-commit-git-failed",
            step=step,
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    return completed.returncode


def run_tdd_commit(
    *,
    repo: Path,
    test_path: str,
    impl_paths: list[str],
    subject: str,
    git_prefix: list[str],
    env: dict[str, str],
) -> int:
    """Drive the Red-commit-then-Green-amend ritual; return an exit code.

    Sequence (each git call is run through `git_prefix`, with the GIT_*
    hook-passthrough vars scrubbed from `env` so git is confined to `repo`):

    1. Red — `git add <test_path>` (test ALONE, impl unmodified on disk)
       then `git commit -m <subject>`. The commit-msg hook records the
       `TDD-Red-*` trailers when the staged test fails.
    2. Green — `git add <impl_paths...>` then `git commit --amend
       --no-edit`. The hook re-runs the now-passing test and records the
       `TDD-Green-*` trailers.

    Returns 0 on success. On any git/hook failure it returns that step's
    non-zero exit code immediately, leaving the repo at whatever state
    git left it (e.g. a landed Red commit) so the operator can inspect
    the rejection and recover.
    """
    log = _configure_logger()
    log.info(
        "tdd-commit-start: driving Red-then-Green ritual",
        check_id="tdd-commit-start",
        test_path=test_path,
        impl_paths=impl_paths,
        subject=subject,
    )
    red_add = _run_git(
        git_prefix=git_prefix,
        args=["add", "--", test_path],
        repo=repo,
        env=env,
        log=log,
        step="red-add-test",
    )
    if red_add != 0:
        return red_add
    red_commit = _run_git(
        git_prefix=git_prefix,
        args=["commit", "-m", subject],
        repo=repo,
        env=env,
        log=log,
        step="red-commit",
    )
    if red_commit != 0:
        return red_commit
    green_add = _run_git(
        git_prefix=git_prefix,
        args=["add", "--", *impl_paths],
        repo=repo,
        env=env,
        log=log,
        step="green-add-impl",
    )
    if green_add != 0:
        return green_add
    green_amend = _run_git(
        git_prefix=git_prefix,
        args=["commit", "--amend", "--no-edit"],
        repo=repo,
        env=env,
        log=log,
        step="green-amend",
    )
    if green_amend != 0:
        return green_amend
    log.info(
        "tdd-commit-done: Red→Green ritual complete (single commit carries test + impl)",
        check_id="tdd-commit-done",
        test_path=test_path,
        impl_paths=impl_paths,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tdd-commit",
        description=(
            "Mechanize the Red-commit-then-Green-amend TDD ritual: stage the "
            "test ALONE and commit (Red), then stage the impl and amend (Green), "
            "producing one commit carrying the test, the impl, and both "
            "TDD-Red-*/TDD-Green-* trailer sets. Use a feat:/fix: --subject."
        ),
    )
    _ = parser.add_argument(
        "--test",
        type=str,
        required=True,
        metavar="PATH",
        help="repo-relative path to the test file staged alone for the Red commit",
    )
    _ = parser.add_argument(
        "--impl",
        type=str,
        action="append",
        required=True,
        metavar="PATH",
        dest="impl",
        help="repo-relative impl path to stage for the Green amend (repeatable)",
    )
    _ = parser.add_argument(
        "--subject",
        type=str,
        required=True,
        metavar="SUBJECT",
        help="feat:/fix: Conventional-Commit subject for the single commit",
    )
    _ = parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        metavar="PATH",
        help="repository working tree to commit in (default: current working directory)",
    )
    _ = parser.add_argument(
        "--no-mise",
        action="store_true",
        default=False,
        help=(
            "invoke a bare `git` instead of `mise exec -- git` (skips lefthook; "
            "for hook-less repos such as the helper's own test fixtures)"
        ),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo: Path = args.repo if args.repo is not None else Path.cwd()
    env = dict(os.environ)
    git_prefix = _resolve_git_prefix(no_mise=bool(args.no_mise), env=env)
    return run_tdd_commit(
        repo=repo,
        test_path=args.test,
        impl_paths=list(args.impl),
        subject=args.subject,
        git_prefix=git_prefix,
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
