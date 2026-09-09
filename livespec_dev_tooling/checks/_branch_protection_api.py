"""Reading the default branch's protection state from the forge API.

Extracted from `branch_protection_alignment.py` (R4.S6,
livespec-dev-tooling-ul61), which had reached 248 of its 250-line hard LLOC
ceiling — two lines of headroom, so the next edit to it was always going to be
the one that broke the ceiling. This module is the cohesive half: everything
that TALKS TO THE FORGE and nothing that decides anything. The alignment
verdict, and what an unreadable state costs, stay with the check.

Two reads live here, against two endpoints, because the protection facts the
merge-gate contract names are split across them: the `required_status_checks`
object carries `contexts` and `strict`, and `enforce_admins` has its own
sub-endpoint.

The names stay private and are re-exported by the check module, so a caller —
or a test — still reaches them through `branch_protection_alignment`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import structlog

from livespec_dev_tooling.checks._gate_context import gate_repository

__all__: list[str] = [
    "_AdminEnforcement",
    "_ProtectionAbsent",
    "_RequiredContexts",
    "_fetch_admin_enforcement",
    "_fetch_required_contexts",
    "_resolve_owner_repo",
]

# Match the two canonical github.com remote URL forms emitted by `git remote
# get-url origin`: `https://github.com/<owner>/<repo>(.git)` and
# `git@github.com:<owner>/<repo>(.git)`. The library is consumed across
# every livespec-governed sibling repo, so the consumer's owner/repo
# identifier MUST come from the local git remote rather than a hardcoded
# constant (which would have pinned the check to a single repo).
_REMOTE_URL_PATTERN = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$"
)
# GitHub's branch-protection endpoints return this EXACT 404 message
# body only when an admin-scoped token reads a genuinely unprotected
# branch. A token that lacks the admin scope needed to READ protection
# (the default Actions GITHUB_TOKEN) gets a generic "Not Found" /
# "Resource not accessible by integration" instead, so the presence of
# this literal phrase is the definitive "absent" disambiguator.
_NOT_PROTECTED_MARKER = "Branch not protected"
# `git symbolic-ref refs/remotes/origin/HEAD` answers with a ref of this
# shape when the clone recorded origin's default branch; the branch name
# is the remainder after the prefix.
_ORIGIN_HEAD_PREFIX = "refs/remotes/origin/"
# Last-resort default branch when neither the local symref nor the repo
# object resolves one. Matches the fleet-side resolver's fallback
# (`FleetContext.canonical_ref`): an unresolvable lookup then behaves
# exactly as the pre-17o hardcoded path did.
_FALLBACK_BRANCH = "master"


@dataclass(frozen=True, kw_only=True)
class _ProtectionAbsent:
    """The API definitively reported the default branch is unprotected.

    Distinct from the graceful-skip case (represented by `None`): an
    admin-scoped token read the default branch's protection and GitHub
    answered with the canonical "Branch not protected" 404. This is a
    fail-trigger, not a can't-read skip.
    """


@dataclass(frozen=True, kw_only=True)
class _RequiredContexts:
    """The API succeeded; carries the default branch's required_status_checks.

    `contexts` is the required-checks list; `strict` is the
    require-branches-up-to-date flag, which MUST be OFF per livespec
    `SPECIFICATION/non-functional-requirements.md` section "CI as a merge gate
    (branch protection)".

    `owner_repo` and `branch` are the PROVENANCE of that read — the address
    this object was fetched from, recorded so a caller needing a second read
    against the same branch (`_fetch_admin_enforcement`) addresses it from the
    resolution this one already did rather than repeating a symref lookup and,
    where that misses, a whole repo-object call.
    """

    contexts: frozenset[str]
    strict: bool
    owner_repo: str
    branch: str


@dataclass(frozen=True, kw_only=True)
class _AdminEnforcement:
    """The default branch's `enforce_admins` flag, as the forge reported it.

    Exists only when the flag was actually READ. `None` in place of this
    object is a DIFFERENT answer from `enabled=False` — it says the run did
    not see the flag at all — and the caller reports the two differently.
    """

    enabled: bool


def _resolve_owner_repo(*, log: structlog.stdlib.BoundLogger, env: Mapping[str, str]) -> str | None:
    """Resolve the GitHub owner/repo identifier this run is judging.

    A DELEGATED GATE'S OWN DECLARATION WINS, and is consulted first (R4.S7
    slice B, livespec-dev-tooling-rwmo.2). A gate pod clones from the
    in-cluster git daemon, so the remote below is a `git://` URL with no owner
    segment: asking it would spend a subprocess to learn nothing. Precedence is
    the substantive half — a gate that NAMED the repository it is judging is
    not second-guessed by whatever its transport clone happens to say. Off a
    gate the declaration is inert (`_gate_context.gate_repository`), so this is
    unreachable on a contributor's machine.

    Otherwise the identity comes from `git remote get-url origin`. Returns None
    and logs a warning when git is unavailable, the remote is not set, or the
    URL does not match the canonical github.com pattern — so the calling check
    exits 0 cleanly rather than failing in unusual local configurations (no
    remote, fork remote, gitlab, etc.). Inside a gate that same None is a
    FAILURE at the caller: there, a repository nobody named is a verification
    that cannot be performed, not one that can be skipped.
    """
    declared = gate_repository(env=env)
    if declared is not None:
        return declared
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        log.warning(
            "git remote get-url origin failed; skipping branch-protection alignment check",
            stderr=completed.stderr.strip()[:200],
            hint="run inside a checked-out clone with an `origin` remote configured",
        )
        return None
    url = completed.stdout.strip()
    match = _REMOTE_URL_PATTERN.match(url)
    if match is None:
        log.warning(
            "origin URL did not match github.com pattern; skipping branch-protection alignment",
            url=url[:200],
            hint="branch-protection alignment is github.com-specific",
        )
        return None
    return f"{match.group(1)}/{match.group(2)}"


def _default_branch_from_git() -> str | None:
    """The default branch per the clone's `refs/remotes/origin/HEAD`, or None.

    `git symbolic-ref refs/remotes/origin/HEAD` answers from local state
    (no network); a normal clone records the symref at clone time. None
    when the symref is unset (e.g. a single-ref CI fetch) or the output
    is not a `refs/remotes/origin/<branch>` ref.
    """
    completed = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    ref = completed.stdout.strip()
    branch = ref.removeprefix(_ORIGIN_HEAD_PREFIX)
    if branch == ref or not branch:
        return None
    return branch


def _default_branch_from_api(*, owner_repo: str) -> str | None:
    """The default branch per the GitHub repo object, or None on any failure.

    `GET repos/{owner_repo}` needs only basic repository read access
    (the default Actions GITHUB_TOKEN has it), so this fallback still
    resolves correctly where the symref is unset.
    """
    completed = subprocess.run(
        ["gh", "api", f"repos/{owner_repo}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        return None
    branch = cast("dict[str, object]", parsed).get("default_branch")
    if not isinstance(branch, str) or not branch:
        return None
    return branch


def _resolve_default_branch(*, log: structlog.stdlib.BoundLogger, owner_repo: str) -> str:
    """Resolve the repo's default branch: local symref, then the API, then `master`.

    The check historically hardcoded `master`, so on a main-default
    governed repo it read the protection of a nonexistent branch and
    misreported (livespec-dev-tooling-17o). Default-branch resolution is
    mechanical extraction, not a spec-rule parser, so per the
    livespec-dev-tooling-6cf convention it is implemented locally here
    rather than shared with the fleet modules' `FleetContext.canonical_ref`
    (`checks/` never imports from `fleet/`).
    """
    branch = _default_branch_from_git()
    if branch is not None:
        return branch
    branch = _default_branch_from_api(owner_repo=owner_repo)
    if branch is not None:
        return branch
    log.warning(
        "could not resolve the default branch; falling back to 'master'",
        hint=(
            "record origin's default branch locally (git remote set-head "
            "origin -a) or check gh auth status"
        ),
    )
    return _FALLBACK_BRANCH


def _fetch_required_contexts(
    *, log: structlog.stdlib.BoundLogger, env: Mapping[str, str]
) -> _RequiredContexts | _ProtectionAbsent | None:
    """Fetch the default branch protection's required_status_checks object.

    Three-way result:

    - `_RequiredContexts` — the API succeeded; carries the default
      branch's required-checks list (possibly empty) AND the `strict`
      flag.
    - `_ProtectionAbsent` — the API definitively reported NO protection
      (the canonical "Branch not protected" 404). Fail-trigger.
    - `None` — graceful skip: `gh` is unavailable, the call failed for
      a reason OTHER than definitive-absence (e.g. a permission/
      visibility 404 under a token without admin scope), no repository
      could be named (see `_resolve_owner_repo`), or the success
      payload had an unexpected shape.
      The caller exits 0 so local pre-commit and Actions-token CI runs
      are not blocked, since "can't read" is indistinguishable from
      "absent" without admin read access.
    """
    if shutil.which("gh") is None:
        log.warning(
            "gh CLI not on PATH; skipping branch-protection alignment check",
            hint="install gh CLI or run in CI with GH_TOKEN set",
        )
        return None
    owner_repo = _resolve_owner_repo(log=log, env=env)
    if owner_repo is None:
        return None
    branch = _resolve_default_branch(log=log, owner_repo=owner_repo)
    # Read the full required_status_checks OBJECT (not the bare
    # /contexts sub-endpoint) so the response carries both `strict` and
    # `contexts`: the strict-off assertion needs the `strict` flag, which
    # the /contexts list endpoint does not return.
    api_path = f"repos/{owner_repo}/branches/{branch}/protection/required_status_checks"
    completed = subprocess.run(
        ["gh", "api", api_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        combined = f"{completed.stdout}\n{completed.stderr}"
        if _NOT_PROTECTED_MARKER in combined:
            # Definitive "absent": an admin-scoped token read the default
            # branch and GitHub answered with the canonical "Branch not
            # protected" 404. This is the fail-trigger, NOT a can't-read
            # skip.
            return _ProtectionAbsent()
        log.warning(
            "gh api call failed for a non-definitive reason; "
            "cannot distinguish absent protection from missing read access; "
            "skipping branch-protection alignment check",
            stderr=completed.stderr.strip()[:200],
            hint=(
                "check gh auth status; the default Actions GITHUB_TOKEN "
                "lacks the admin scope needed to read branch protection"
            ),
        )
        return None
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        log.error("unexpected gh api response shape", payload_type=type(parsed).__name__)
        return None
    # The `cast` is the single typed parse boundary: `json.loads` yields
    # `Any`, the `isinstance` guard narrows to `dict`, and the cast gives the
    # object's members a typed `object` shape so the per-element
    # `isinstance(entry, str)` filter and the `bool(...)` strict coercion stay
    # load-bearing runtime guards against a malformed `gh api` payload.
    payload = cast("dict[str, object]", parsed)
    contexts_raw = payload.get("contexts")
    contexts: set[str] = set()
    if isinstance(contexts_raw, list):
        for entry in cast("list[object]", contexts_raw):
            if isinstance(entry, str):
                contexts.add(entry)
    strict = bool(payload.get("strict"))
    return _RequiredContexts(
        contexts=frozenset(contexts),
        strict=strict,
        owner_repo=owner_repo,
        branch=branch,
    )


def _fetch_admin_enforcement(
    *, log: structlog.stdlib.BoundLogger, protection: _RequiredContexts
) -> _AdminEnforcement | None:
    """Read the default branch's `enforce_admins` flag, or None when unread.

    Its OWN endpoint, because the `required_status_checks` object
    `_fetch_required_contexts` reads does not carry the flag at all: a
    repository that turned admin enforcement off — letting exactly the
    accounts that do the merging merge straight past a red required check —
    reads as fully aligned on that endpoint alone
    (livespec-dev-tooling-65c). The address comes from the `protection`
    read that necessarily preceded this one.

    `None` means the flag was NOT READ: the call failed, the body was not an
    object, or the object carried no boolean `enabled`. The caller must not
    treat that as enabled. It is also not the ordinary can't-read case the
    check skips on — reaching here means the required-checks read already
    succeeded, so the token demonstrably holds the admin scope both reads
    need, and a failure on the second endpoint is anomalous.
    """
    api_path = (
        f"repos/{protection.owner_repo}/branches/{protection.branch}/protection/enforce_admins"
    )
    completed = subprocess.run(
        ["gh", "api", api_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        log.warning(
            "gh api call failed reading the enforce_admins sub-endpoint",
            stderr=completed.stderr.strip()[:200],
            api_path=api_path,
        )
        return None
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        return None
    # Same typed parse boundary as the required-checks read above: the
    # `isinstance` narrowing plus the cast keep the `enabled` guard a
    # load-bearing runtime check rather than an `Any` passthrough. It is an
    # IDENTITY test against `bool`, not a truthiness read, so an object
    # missing the key reads as unread instead of as disabled.
    enabled = cast("dict[str, object]", parsed).get("enabled")
    if not isinstance(enabled, bool):
        return None
    return _AdminEnforcement(enabled=enabled)
