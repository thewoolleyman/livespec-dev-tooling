"""no_stale_revise_branches — refuse new revise passes while a stale spec branch exists.

Per `SPECIFICATION/proposed_changes/no-stale-revise-branches-check.md`
(child PC of livespec's coordinating-epic-stale-revise-enforcement),
this check enumerates local `refs/heads/spec/*` branches and fails
when any such branch is ahead of the canonical branch by one or more
commits.

Algorithm (per the PC §"`no_stale_revise_branches` check" subsection):

1. Resolve the canonical branch name. Priority:
   a. `.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch`
      (or any other impl-plugin block's `canonical_branch` key when
      `livespec-impl-plaintext` is absent).
   b. `git symbolic-ref --short refs/remotes/origin/HEAD`.
   c. Hard-coded fallback `master`.
2. Enumerate local refs via
   `git for-each-ref --format='%(refname:short)' refs/heads/spec/`.
3. For each branch:
   - Run `git rev-list --left-right --count origin/<canonical>...<branch>`.
   - Parse the output as `behind\tahead`.
   - When `ahead > 0`: collect the branch as stale, also collecting
     the short SHA + subject of the branch HEAD for the user diagnostic.
4. Exit `0` when the stale list is empty, `4` when populated.

Exit codes:

- `0` — no stale `spec/*` branches.
- `2` — usage error (bad CLI invocation).
- `4` — one or more stale branches; structured findings on stderr.

CLI flags:

- `--allow-stale-branches` (optional). When set, the check still
  enumerates and logs the stale branches, but exits `0` with the
  diagnostics surfaced as `info`-level rather than `error`-level.
  Intended for callers that want the visibility without the gate.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path`
at module import time so the check works equally well via
`python -m` and via direct script invocation.

Per `SPECIFICATION/contracts.md` §"Consumer configuration schema",
the canonical-branch input is a project-wide invariant carve-out
(read directly from `.livespec.jsonc`, NOT from the
`[tool.livespec_dev_tooling]` role-key inventory).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_LIVESPEC_JSONC_FILENAME = ".livespec.jsonc"
_DEFAULT_CANONICAL_BRANCH = "master"
_SPEC_BRANCH_REFSPEC = "refs/heads/spec/"
_REV_LIST_LEFT_RIGHT_COUNT_FIELDS = 2


@dataclass(frozen=True, kw_only=True)
class _StaleBranch:
    """One stale-branch finding payload — branch identity + ahead-count diagnostic."""

    branch: str
    canonical: str
    ahead: int
    short_sha: str
    subject: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="no-stale-revise-branches",
        description=(
            "Refuse new /livespec:revise passes while a local `spec/*` branch "
            "is ahead of the canonical branch. Enumerates local refs under "
            "`refs/heads/spec/` and shells out to `git rev-list` for ahead-count."
        ),
    )
    _ = parser.add_argument(
        "--allow-stale-branches",
        action="store_true",
        help=(
            "Exit 0 even when stale branches are present; the findings are "
            "surfaced as info-level rather than error-level."
        ),
    )
    return parser


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("no_stale_revise_branches")


def _canonical_branch_from_jsonc(*, cwd: Path) -> str | None:
    """Read `canonical_branch` from `.livespec.jsonc` impl-plugin blocks.

    Returns the first non-empty string found at
    `<impl-plugin>.canonical_branch`, scanning the document's top-level
    keys for any dict-shaped value carrying a `canonical_branch` field.
    The `livespec-impl-plaintext` block is preferred when present; any
    other impl-plugin block's key is accepted as a fallback so the
    check generalizes to siblings that may register a different impl
    plugin.
    """
    config_path = cwd / _LIVESPEC_JSONC_FILENAME
    if not config_path.is_file():
        return None
    text = config_path.read_text(encoding="utf-8")
    parsed: Any = jsoncomment.loads(text)
    if not isinstance(parsed, dict):
        return None
    preferred = parsed.get("livespec-impl-plaintext")
    if isinstance(preferred, dict):
        value = preferred.get("canonical_branch")
        if isinstance(value, str) and value:
            return value
    for key, value in parsed.items():
        if key == "livespec-impl-plaintext" or not isinstance(value, dict):
            continue
        candidate = value.get("canonical_branch")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _canonical_branch_from_origin_head(*, cwd: Path) -> str | None:
    """Resolve `origin/HEAD`'s symbolic ref to a short branch name.

    Returns None when `origin/HEAD` is not set (e.g., a fresh clone
    where the user has not run `git remote set-head origin --auto`),
    so the caller falls back to the hard-coded default.
    """
    completed = subprocess.run(
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    prefix = "origin/"
    if value.startswith(prefix):
        return value[len(prefix) :]
    return value


def _resolve_canonical_branch(*, cwd: Path) -> str:
    """Resolve the canonical branch via the priority chain.

    Priority: `.livespec.jsonc` impl-plugin key → `origin/HEAD`
    → hard-coded `master`. The first non-empty source wins.
    """
    jsonc_value = _canonical_branch_from_jsonc(cwd=cwd)
    if jsonc_value is not None:
        return jsonc_value
    head_value = _canonical_branch_from_origin_head(cwd=cwd)
    if head_value is not None:
        return head_value
    return _DEFAULT_CANONICAL_BRANCH


def _enumerate_spec_branches(*, cwd: Path) -> list[str]:
    """Enumerate local refs matching `refs/heads/spec/*`.

    Uses `git for-each-ref` with a short-name format so the returned
    strings are usable directly as branch names (e.g., `spec/v003`).
    """
    completed = subprocess.run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short)",
            _SPEC_BRANCH_REFSPEC,
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line]


def _ahead_count(*, cwd: Path, branch: str, canonical: str) -> int | None:
    """Return the ahead-count of `branch` vs `origin/<canonical>`.

    Runs `git rev-list --left-right --count origin/<canonical>...<branch>`
    and parses the `behind\tahead` output. Returns None when the
    command fails (e.g., the canonical remote ref does not exist) so
    the caller can skip the branch with a structured warning rather
    than crashing.
    """
    completed = subprocess.run(
        [
            "git",
            "rev-list",
            "--left-right",
            "--count",
            f"origin/{canonical}...{branch}",
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    parts = completed.stdout.strip().split()
    if len(parts) != _REV_LIST_LEFT_RIGHT_COUNT_FIELDS:
        return None
    ahead_raw = parts[1]
    if not ahead_raw.isdigit():
        return None
    return int(ahead_raw)


def _branch_head_subject(*, cwd: Path, branch: str) -> tuple[str, str]:
    """Return (short_sha, subject) for the branch's HEAD commit.

    Falls back to `("?", "")` when either lookup fails so the
    diagnostic can still surface the branch name and ahead-count.
    """
    sha_completed = subprocess.run(
        ["git", "rev-parse", "--short", branch],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    short_sha = sha_completed.stdout.strip() if sha_completed.returncode == 0 else "?"
    subject_completed = subprocess.run(
        ["git", "log", "-1", "--format=%s", branch],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    subject = subject_completed.stdout.strip() if subject_completed.returncode == 0 else ""
    return short_sha, subject


def _emit_finding(
    *,
    log: structlog.stdlib.BoundLogger,
    finding: _StaleBranch,
    allow_stale: bool,
) -> None:
    message = (
        f"branch '{finding.branch}' is {finding.ahead} commit(s) ahead of "
        f"origin/{finding.canonical}; last commit {finding.short_sha} "
        f'"{finding.subject}"'
    )
    fields = {
        "check_id": "no_stale_revise_branches",
        "branch": finding.branch,
        "canonical_branch": finding.canonical,
        "ahead": finding.ahead,
        "short_sha": finding.short_sha,
        "subject": finding.subject,
        "path": "",
        "line": 0,
    }
    if allow_stale:
        log.info(message, status="info", **fields)
    else:
        log.error(message, status="fail", **fields)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    allow_stale: bool = bool(args.allow_stale_branches)
    log = _configure_logger()
    cwd = Path.cwd()
    canonical = _resolve_canonical_branch(cwd=cwd)
    branches = _enumerate_spec_branches(cwd=cwd)
    stale_count = 0
    for branch in branches:
        ahead = _ahead_count(cwd=cwd, branch=branch, canonical=canonical)
        if ahead is None:
            log.warning(
                "could not compute ahead-count; skipping branch",
                branch=branch,
                canonical_branch=canonical,
                hint=(
                    f"verify origin/{canonical} exists; "
                    "run `git fetch origin` or set canonical_branch in .livespec.jsonc"
                ),
            )
            continue
        if ahead <= 0:
            continue
        stale_count += 1
        short_sha, subject = _branch_head_subject(cwd=cwd, branch=branch)
        finding = _StaleBranch(
            branch=branch,
            canonical=canonical,
            ahead=ahead,
            short_sha=short_sha,
            subject=subject,
        )
        _emit_finding(log=log, finding=finding, allow_stale=allow_stale)
    if stale_count == 0:
        return 0
    if allow_stale:
        return 0
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
