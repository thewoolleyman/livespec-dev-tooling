"""Resolve WHICH MEMBER this checkout is, from its `origin` remote.

Split out of `_context` to keep that file under the 250-LLOC hard
ceiling the `gh`-seam conversion pushed it past — the same
private-sibling split as `_pin_walk_failure` and `_ci_matrix_parse`.
`_context` re-exports both names, so no consumer import changes.

BOTH RESOLVERS ARE ON THE `IOResult` RAILWAY — livespec-dev-tooling-qndn,
epic 8o8e. They are the ONE `subprocess` caller in the fleet package that
is not behind an injected seam, so they are the I/O boundary itself and
`IOResult` rather than `Result` is the honest container (the same
direct-call-versus-injected-seam reading that keeps `fetch_manifest` on
`Result`).

WHAT THE OLD `str | None` COULD NOT SAY, and it is why this is a
conversion rather than a re-spelling. FOUR outcomes shared one
annotation:

- no origin remote, and
- `git remote get-url origin` failing for any other reason, and
- a remote that is not github.com

all arrived as the SAME `None`, fused one level down by
`_origin_remote_match`. Every caller could only report "the origin
remote is not a github.com URL" — right one time in three.

- `git` absent from PATH did not arrive as a `None` at all: the
  `subprocess.run` was UNGUARDED, so it raised `FileNotFoundError`
  straight out of a function whose annotation promised `str | None`.

WHAT IS AND IS NOT A FAILURE HERE. Every one of the three is a failure:
unlike the git PROBES in `checks/_primary_checkout_git_probes.py`, where
a non-zero exit is frequently an ANSWER ("not a repository", "key
unset"), there is no exit of `git remote get-url origin` that answers
"this checkout has an identity and it is nothing". A caller asking WHICH
MEMBER AM I either gets a name or could not find out.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Carried rather than inherited from an importer: without it the vendored
# `returns` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this
# file. The module that broke the fleet's release fan-out for seven hours on
# 2026-07-30 was in exactly that state until it became a process entry point.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "OriginRemoteUnresolved",
    "owner_or_origin",
    "resolve_owner",
    "resolve_repo_name",
]


# Matches the two canonical github.com remote URL forms emitted by
# `git remote get-url origin`, mirroring the sibling
# `branch_protection_alignment` resolver: the owner identifier comes
# from the local remote rather than a hardcoded constant.
_REMOTE_URL_PATTERN = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$"
)


@dataclass(frozen=True, kw_only=True)
class OriginRemoteUnresolved:
    """`origin` did not yield a github.com owner/repo pair, and WHICH of three reasons.

    `reason` is the discriminator a caller branches on; `detail` is the
    operator-facing evidence, and the two are deliberately separate so a
    diagnostic can name the cause without the caller parsing prose. A bare
    "could not resolve the owner" would be the same manufactured-confidence
    shape this conversion removes, one level up.

    The three are kept apart because they want DIFFERENT operator responses:
    `git-not-run` is a broken environment, `no-origin-remote` is a checkout
    without the remote this derivation reads, and `not-github-remote` is a
    checkout that is fine but is not a fleet member. Collapsed into one
    sentinel they were reported as whichever one the caller's prose guessed.
    """

    reason: Literal["git-not-run", "no-origin-remote", "not-github-remote"]
    detail: str


def _origin_remote_match(
    *, cwd: Path | None = None
) -> IOResult[re.Match[str], OriginRemoteUnresolved]:
    """Match `git remote get-url origin` against the owner/repo pattern.

    One parse shared by `resolve_owner` and `resolve_repo_name`: the two answers
    come from the same remote URL, and a second copy of the pattern-and-subprocess
    dance would be a rule with two copies, which drifts. That sharing is also why
    livespec v179 clause (d) COUPLES the two — converting either alone leaves the
    three failures fused in the other.

    The catch is NARROW and ENUMERATED (`OSError`), which is the sanctioned
    hand-rolled seam lift: `git` absent from PATH, a `git` that cannot be
    exec'd, a fork failure. A bug raised in here still propagates.
    """
    try:
        completed = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
            cwd=None if cwd is None else str(cwd),
        )
    except OSError as unusable:
        return IOFailure(OriginRemoteUnresolved(reason="git-not-run", detail=str(unusable)))
    if completed.returncode != 0:
        # The exit code rides in `detail` because git's stderr is sometimes
        # empty and a diagnostic with neither is unactionable.
        return IOFailure(
            OriginRemoteUnresolved(
                reason="no-origin-remote",
                detail=f"exit {completed.returncode}: {completed.stderr.strip()}",
            )
        )
    url = completed.stdout.strip()
    match = _REMOTE_URL_PATTERN.match(url)
    if match is None:
        return IOFailure(OriginRemoteUnresolved(reason="not-github-remote", detail=url))
    return IOSuccess(match)


def resolve_owner(*, cwd: Path | None = None) -> IOResult[str, OriginRemoteUnresolved]:
    """The GitHub owner from `git remote get-url origin`, or WHICH read failed."""
    return _origin_remote_match(cwd=cwd).map(lambda match: match.group(1))


def owner_or_origin(
    *, argument: str | None, cwd: Path | None = None
) -> IOResult[str, OriginRemoteUnresolved]:
    """An explicit `--owner` when one was supplied, else the origin-derived owner.

    The precedence rule the four fleet CLIs share, in ONE place. It was four
    copies of `cast("str | None", args.owner) or resolve_owner()`, and this
    repo's own `livespec-i04f` finding is that copies of a rule keep agreement
    by copying until they do not. Truthiness rather than `is not None` is
    deliberate and preserves the copies' behavior: `--owner ""` names no owner,
    so it falls through to the remote rather than being taken literally.
    """
    if argument:
        return IOSuccess(argument)
    return resolve_owner(cwd=cwd)


def resolve_repo_name(*, cwd: Path | None = None) -> IOResult[str, OriginRemoteUnresolved]:
    """The repository's short name from `git remote get-url origin`, or WHICH read failed.

    This is the "which member am I RUNNING AS" derivation. It is DERIVED rather
    than configured on purpose: a config key naming the running repo would be a
    second source of truth that can drift from the checkout it describes, and the
    remote already knows the answer. `.git` suffix and trailing slash are stripped
    by the shared pattern, so a member's name matches the manifest entry directly.
    """
    return _origin_remote_match(cwd=cwd).map(lambda match: match.group(2))
