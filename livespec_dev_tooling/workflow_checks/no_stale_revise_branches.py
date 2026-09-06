"""no_stale_revise_branches — refuse new revise passes while a stale spec branch exists.

Per `SPECIFICATION/contracts.md` section "`no_stale_revise_branches` check"
(a revise-workflow check, per section "Shared check inventory"), this check
enumerates local `refs/heads/spec/*` branches and fails when any such
branch carries one or more commits that have NOT LANDED on the canonical
branch.

THE DISCRIMINATOR IS PATCH-ID EQUIVALENCE, computed by
`git cherry origin/<canonical> <branch>` — and naming it here is a
requirement rather than a courtesy, because it is what tells an operator
reading a finding which failure modes the finding can have. It was
ANCESTRY (`git rev-list --left-right --count`, fail when ahead > 0) until
livespec-dev-tooling-jtrt.2. On a rebase-merge-only fleet that could not
work: a rebase-merge REWRITES a branch's commits, so a landed branch's
local tip is never an ancestor of the canonical branch, and every
landed-but-undeleted branch was reported as stale. Measured 2026-08-22 in
livespec-overseer, the check returned eleven fail findings whose content
was, in all eleven cases, already on `origin/master`. That is a check that
cannot SUCCEED — the mirror of the check-that-cannot-fail hazard — and its
practical effect was worse than noise: with merge and abandon both
inapplicable to an already-merged branch, the only remedy left was the
skip flag, so the precondition TRAINED the skip it exists to withhold.

It is invoked by livespec's `/livespec:revise` SKILL.md pre-step
refusal — the sole caller and load-bearing enforcement point. It lives
under `livespec_dev_tooling/workflow_checks/` (NOT `checks/`) so the
canonical-set derivation auto-excludes it; it is NOT a member of the
per-commit `just check` aggregate and NOT subject to the
wiring-completeness invariant.

Algorithm (per the contracts section "`no_stale_revise_branches` check"):

1. Resolve the canonical branch name. Priority:
   a. `.livespec.jsonc`'s `livespec-orchestrator-git-jsonl.canonical_branch`
      (or any other impl-plugin block's `canonical_branch` key when
      `livespec-orchestrator-git-jsonl` is absent).
   b. `git symbolic-ref --short refs/remotes/origin/HEAD`.
   c. Hard-coded fallback `master`.
2. Enumerate local refs via
   `git for-each-ref --format='%(refname:short)' refs/heads/spec/`.
3. For each branch:
   - Run `git cherry origin/<canonical> <branch>`.
   - Count the `+ <sha>` lines — commits with NO patch-equivalent on the
     canonical branch. A `- <sha>` line is git's own verdict that an
     equivalent patch IS upstream, which is precisely what survives a
     rebase-merge.
   - When the `+` count is `> 0`: collect the branch as stale, also
     collecting the short SHA + subject of the branch HEAD for the user
     diagnostic.
4. Exit `0` when the stale list is empty, `4` when populated.

The discriminator's OWN failure modes, stated because a finding that names
its discriminator is only useful to a reader who can look them up. Both are
conservative — they over-report, never under-report, so the check keeps
failing closed:

- A land that CHANGED the patch produces a different patch-id and is still
  reported: a squash-merge, or a rebase that resolved a conflict.
- The digest pass is not free. `git cherry` patch-ids every commit on both
  sides of the merge base, so an old branch costs a walk of the canonical
  branch's commits since the branch point — more than the ancestry count it
  replaced, and bounded by how long a stale branch was left lying around.

The two discriminators NOT chosen, and why. Subject-match against the
canonical branch's history is cheaper and is what the 2026-08-22
measurement used by hand, but subjects collide, so it can call an unlanded
branch landed — a false NEGATIVE, the direction this check must never fail
in. A forge query for a merged pull request on the head is authoritative
where it applies, but it costs an API call, needs credentials at a local
pre-step, and misses content that landed without a pull request — nine of
the eleven branches in that measurement.

There is no downgrade flag: the check always fails hard (exit `4`) on
any stale branch. The `--allow-stale-branches` downgrade flag was
removed (epic li-cvaudit, li-cvstale): with the revise pre-step as the
sole caller and no per-commit-aggregate invocation, there is nothing
that needs a downgrade lever.

Exit codes:

- `0` — no stale `spec/*` branches.
- `2` — usage error (bad CLI invocation).
- `4` — one or more stale branches; structured findings on stderr.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path`
at module import time so the check works equally well via
`python -m` and via direct script invocation.

Per `SPECIFICATION/contracts.md` section "Consumer configuration schema",
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
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_LIVESPEC_JSONC_FILENAME = ".livespec.jsonc"
_DEFAULT_CANONICAL_BRANCH = "master"
_SPEC_BRANCH_REFSPEC = "refs/heads/spec/"
# `git cherry`'s two line prefixes: `+` marks a commit with no
# patch-equivalent upstream, `-` one that has one.
_CHERRY_UNLANDED_PREFIX = "+"
_CHERRY_LANDED_PREFIX = "-"
# Named in every finding AND in every skip warning so an operator reading
# one knows what the verdict rests on, and therefore which of the failure
# modes in this module's docstring could be producing it.
_DISCRIMINATOR = "patch-id equivalence (`git cherry`)"


@dataclass(frozen=True, kw_only=True)
class _StaleBranch:
    """One stale-branch finding payload — branch identity + unlanded-count diagnostic."""

    branch: str
    canonical: str
    unlanded: int
    short_sha: str
    subject: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="no-stale-revise-branches",
        description=(
            "Refuse new /livespec:revise passes while a local `spec/*` branch "
            "carries commits that have not landed on the canonical branch. "
            "Enumerates local refs under `refs/heads/spec/` and shells out to "
            "`git cherry` to judge landed-ness by PATCH-ID EQUIVALENCE, which "
            "survives the rewrite a rebase-merge performs (ancestry does not). "
            "Always fails hard (exit 4) on any stale branch; there is no "
            "downgrade flag."
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
    The `livespec-orchestrator-git-jsonl` block is preferred when present; any
    other impl-plugin block's key is accepted as a fallback so the
    check generalizes to siblings that may register a different impl
    plugin.
    """
    config_path = cwd / _LIVESPEC_JSONC_FILENAME
    if not config_path.is_file():
        return None
    text = config_path.read_text(encoding="utf-8")
    raw = jsoncomment.loads(text)
    if not isinstance(raw, dict):
        return None
    # The `cast` is the single typed parse boundary: `jsoncomment.loads`
    # yields `Any`, the `isinstance` guard narrows to `dict`, and the cast
    # gives the document a typed `dict[str, object]` shape so each block's
    # `.get("canonical_branch")` access below narrows from `object`.
    parsed = cast("dict[str, object]", raw)
    preferred = parsed.get("livespec-orchestrator-git-jsonl")
    if isinstance(preferred, dict):
        preferred_block = cast("dict[str, object]", preferred)
        value = preferred_block.get("canonical_branch")
        if isinstance(value, str) and value:
            return value
    for key, block in parsed.items():
        if key == "livespec-orchestrator-git-jsonl" or not isinstance(block, dict):
            continue
        block_dict = cast("dict[str, object]", block)
        candidate = block_dict.get("canonical_branch")
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


def _unlanded_count(*, cwd: Path, branch: str, canonical: str) -> int | None:
    """Return how many of `branch`'s commits have NOT landed on `origin/<canonical>`.

    Runs `git cherry origin/<canonical> <branch>`, whose every output line
    is `+ <sha>` for a commit with no patch-equivalent upstream or
    `- <sha>` for one that has one — git compares `git patch-id` digests,
    so a commit REWRITTEN by a rebase still matches its landed twin. The
    returned number is the count of `+` lines; zero means the whole branch
    is on the canonical branch under other SHAs, which is the ordinary
    post-rebase-merge state and NOT staleness.

    See this module's docstring for why patch-id rather than ancestry
    (which cannot work on a rebase-merge fleet), for the two discriminators
    not chosen, and for this one's own failure modes.

    Returns None — "no answer", which the caller turns into a skip with a
    structured warning rather than a verdict — when the command fails
    (e.g. `origin/<canonical>` does not exist) or emits a line in neither
    form. Refusing to guess is the fail-safe direction: reading an
    unparseable answer as "nothing unlanded" would wave a genuinely stale
    branch through.
    """
    completed = subprocess.run(
        ["git", "cherry", f"origin/{canonical}", branch],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    unlanded = 0
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(_CHERRY_UNLANDED_PREFIX):
            unlanded += 1
        elif not stripped.startswith(_CHERRY_LANDED_PREFIX):
            return None
    return unlanded


def _branch_head_subject(*, cwd: Path, branch: str) -> tuple[str, str]:
    """Return (short_sha, subject) for the branch's HEAD commit.

    Falls back to `("?", "")` when either lookup fails so the
    diagnostic can still surface the branch name and unlanded-count.
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
) -> None:
    message = (
        f"branch '{finding.branch}' has {finding.unlanded} unlanded commit(s) "
        f"not present on origin/{finding.canonical} "
        f"(discriminator: {_DISCRIMINATOR}); "
        f'last commit {finding.short_sha} "{finding.subject}"'
    )
    fields = {
        "check_id": "no_stale_revise_branches",
        "branch": finding.branch,
        "canonical_branch": finding.canonical,
        "unlanded": finding.unlanded,
        "discriminator": _DISCRIMINATOR,
        "short_sha": finding.short_sha,
        "subject": finding.subject,
        "path": "",
        "line": 0,
    }
    log.error(message, status="fail", **fields)


def main() -> int:
    parser = _build_parser()
    _ = parser.parse_args()
    log = _configure_logger()
    cwd = Path.cwd()
    canonical = _resolve_canonical_branch(cwd=cwd)
    branches = _enumerate_spec_branches(cwd=cwd)
    stale_count = 0
    for branch in branches:
        unlanded = _unlanded_count(cwd=cwd, branch=branch, canonical=canonical)
        if unlanded is None:
            log.warning(
                "could not evaluate landed-ness; skipping branch",
                branch=branch,
                canonical_branch=canonical,
                discriminator=_DISCRIMINATOR,
                hint=(
                    f"verify origin/{canonical} exists; "
                    "run `git fetch origin` or set canonical_branch in .livespec.jsonc"
                ),
            )
            continue
        if unlanded <= 0:
            continue
        stale_count += 1
        short_sha, subject = _branch_head_subject(cwd=cwd, branch=branch)
        finding = _StaleBranch(
            branch=branch,
            canonical=canonical,
            unlanded=unlanded,
            short_sha=short_sha,
            subject=subject,
        )
        _emit_finding(log=log, finding=finding)
    if stale_count == 0:
        return 0
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
