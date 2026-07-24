"""Shared types + GitHub-access seam for the fleet-membership contract.

Carries the value types every fleet module exchanges (member, row
outcomes, gh results) plus `FleetContext` — the single seam through
which all GitHub state flows. Row functions receive a context and
return outcome VALUES; they never log and never touch `subprocess`
directly, so the obligation table stays hermetically testable with a
canned-response runner. The default runner shells out to the `gh`
CLI (the fleet precedent for GitHub reads — see
`checks/branch_protection_alignment.py`).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

__all__: list[str] = [
    "Adopter",
    "FleetContext",
    "FleetMember",
    "GhResult",
    "GhRunner",
    "RowFinding",
    "RowOutcome",
    "RowPass",
    "RowSkip",
    "TreeState",
    "default_gh_runner",
    "resolve_owner",
]


@dataclass(frozen=True, kw_only=True)
class GhResult:
    """Outcome of one `gh` invocation (exit code + captured streams)."""

    returncode: int
    stdout: str
    stderr: str


class GhRunner(Protocol):
    """Callable seam for `gh` invocations; `args` excludes the leading `gh`."""

    def __call__(self, *, args: list[str], stdin: str | None = None) -> GhResult: ...


@dataclass(frozen=True, kw_only=True)
class FleetMember:
    """One manifest entry: a fleet repo and its repo class."""

    repo: str
    repo_class: str


@dataclass(frozen=True, kw_only=True)
class Adopter:
    """One manifest adopter entry: a repo, its profile layers, and its posture."""

    repo: str
    profile: tuple[str, ...]
    posture: str


@dataclass(frozen=True, kw_only=True)
class RowPass:
    """The member satisfies the obligation row."""

    note: str = ""


@dataclass(frozen=True, kw_only=True)
class RowFinding:
    """The member definitively violates the obligation row."""

    message: str
    severity: str = "error"


@dataclass(frozen=True, kw_only=True)
class RowSkip:
    """The row could not be definitively evaluated (can't-read is not absent)."""

    reason: str


RowOutcome = RowPass | RowFinding | RowSkip


@dataclass(frozen=True, kw_only=True)
class TreeState:
    """A member's recursive master tree: paths, gitlink entries, read status."""

    readable: bool
    truncated: bool = False
    paths: frozenset[str] = frozenset()
    gitlink_paths: tuple[str, ...] = ()


# Matches the two canonical github.com remote URL forms emitted by
# `git remote get-url origin`, mirroring the sibling
# `branch_protection_alignment` resolver: the owner identifier comes
# from the local remote rather than a hardcoded constant.
_REMOTE_URL_PATTERN = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$"
)
_GITLINK_MODE = "160000"
# Fallback ref when a repo's default branch cannot be resolved. The single
# source of truth for a repo's canonical ref is `FleetContext.canonical_ref`,
# resolved and memoized PER REPO: `file_text` and `tree` BOTH route through it
# so the genuine-absence guard — which reads a member's file (file_text) and
# then its tree (tree) to tell genuine absence from transient unreadability —
# can never evaluate the two against divergent branches. Resolving per repo
# (rather than pinning one global branch) is what lets a governed repo whose
# default branch is not `master` be evaluated at all instead of skipping every
# row; memoizing the FALLBACK too keeps the two reads together even when the
# lookup fails mid-run.
_CANONICAL_REF = "master"


def default_gh_runner(*, args: list[str], stdin: str | None = None) -> GhResult:
    """Run `gh <args>`; a missing `gh` binary yields a synthetic failure result."""
    if shutil.which("gh") is None:
        return GhResult(returncode=127, stdout="", stderr="gh CLI not on PATH")
    completed = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        input=stdin,
    )
    return GhResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def resolve_owner(*, cwd: Path | None = None) -> str | None:
    """Resolve the GitHub owner from `git remote get-url origin`, or None."""
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
    )
    if completed.returncode != 0:
        return None
    match = _REMOTE_URL_PATTERN.match(completed.stdout.strip())
    if match is None:
        return None
    return match.group(1)


def _parse_tree_payload(*, payload: object) -> TreeState:
    """Map a `git/trees` JSON payload onto a `TreeState` value."""
    if not isinstance(payload, dict):
        return TreeState(readable=False)
    mapping = cast("dict[str, object]", payload)
    entries = mapping.get("tree")
    if not isinstance(entries, list):
        return TreeState(readable=False)
    paths: set[str] = set()
    gitlinks: list[str] = []
    for entry in cast("list[object]", entries):
        if not isinstance(entry, dict):
            continue
        record = cast("dict[str, object]", entry)
        path = record.get("path")
        if not isinstance(path, str):
            continue
        paths.add(path)
        if record.get("mode") == _GITLINK_MODE:
            gitlinks.append(path)
    return TreeState(
        readable=True,
        truncated=bool(mapping.get("truncated")),
        paths=frozenset(paths),
        gitlink_paths=tuple(sorted(gitlinks)),
    )


@dataclass(frozen=True, kw_only=True)
class FleetContext:
    """Owner + gh seam + per-run memo caches shared by every row function."""

    owner: str
    run_gh: GhRunner
    # True when this run emits per-member verdicts — i.e. it is the fan-out
    # preflight, whose findings the livespec-f73t dispatch-matrix filter
    # consumes as per-member exclusions rather than as a halt. Rows use it to
    # scope severity by CONTEXT: a persisting pin gap is an error HERE (the
    # filter excludes that member and propagation continues) and a warning in
    # ordinary per-PR CI, where a sibling's stall would otherwise red this
    # repo's unrelated and repair PRs alike. Derived from the existing
    # `--emit-member-verdicts` invocation, never from a lever or env var.
    # Defaults False so every other construction site keeps warning behavior.
    filter_consuming_preflight: bool = False
    tree_cache: dict[str, TreeState] = field(default_factory=dict)
    installed_cache: dict[str, frozenset[str] | None] = field(default_factory=dict)
    marker_cache: dict[str, bool] = field(default_factory=dict)
    ref_cache: dict[str, str] = field(default_factory=dict)

    def api(self, *, path: str, method: str = "GET", body: str | None = None) -> GhResult:
        """Issue one `gh api` call; non-GET methods stream `body` via stdin."""
        args = ["api", path]
        if method != "GET":
            args.extend(["--method", method, "--input", "-"])
        return self.run_gh(args=args, stdin=body)

    def api_object(self, *, path: str) -> object | None:
        """GET `path` and parse the JSON payload; None on any failure."""
        result = self.api(path=path)
        if result.returncode != 0:
            return None
        try:
            return cast("object", json.loads(result.stdout))
        except json.JSONDecodeError:
            return None

    def canonical_ref(self, *, repo: str) -> str:
        """Memoized default branch of `repo`; the `master` fallback when unresolvable.

        Resolving the ref per repo is what lets a governed repo whose default
        branch is not `master` be evaluated at all — reading it on the wrong
        branch makes every row skip. The result (fallback included) is memoized
        so `file_text` and `tree` always agree on one ref for a given repo
        within a run. Falling back rather than failing preserves the historical
        behavior: an unresolvable lookup yields a can't-read skip downstream,
        never a false pass.
        """
        cached = self.ref_cache.get(repo)
        if cached is not None:
            return cached
        payload = self.api_object(path=f"repos/{self.owner}/{repo}")
        resolved = _CANONICAL_REF
        if isinstance(payload, dict):
            branch = cast("dict[str, object]", payload).get("default_branch")
            if isinstance(branch, str) and branch:
                resolved = branch
        self.ref_cache[repo] = resolved
        return resolved

    def file_text(self, *, repo: str, path: str) -> str | None:
        """Raw file content at `repo`'s canonical ref via the contents API.

        The ref is pinned EXPLICITLY (`?ref=<canonical_ref>`) to match `tree`'s
        pin, so a guard that reads a file and then the tree never resolves the
        two against divergent branches. None on failure.
        """
        result = self.run_gh(
            args=[
                "api",
                f"repos/{self.owner}/{repo}/contents/{path}?ref={self.canonical_ref(repo=repo)}",
                "-H",
                "Accept: application/vnd.github.raw",
            ]
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def tree(self, *, repo: str) -> TreeState:
        """Memoized recursive canonical-ref tree for `repo` (one API call per run)."""
        cached = self.tree_cache.get(repo)
        if cached is not None:
            return cached
        ref = self.canonical_ref(repo=repo)
        payload = self.api_object(path=f"repos/{self.owner}/{repo}/git/trees/{ref}?recursive=1")
        state = (
            TreeState(readable=False) if payload is None else _parse_tree_payload(payload=payload)
        )
        self.tree_cache[repo] = state
        return state

    def installed_repos(self) -> frozenset[str] | None:
        """Repos visible to the current App installation token; None = can't read.

        `GET /installation/repositories` only answers under a GitHub App
        installation token (the scheduled fleet workflow and the release
        fan-out preflight mint one); under a user PAT it fails and the
        app-installation row skips rather than guessing.
        """
        cached = self.installed_cache.get("installation")
        if "installation" in self.installed_cache:
            return cached
        payload = self.api_object(path="installation/repositories?per_page=100")
        names: frozenset[str] | None = None
        if isinstance(payload, dict):
            repositories = cast("dict[str, object]", payload).get("repositories")
            if isinstance(repositories, list):
                names = frozenset(
                    cast("str", cast("dict[str, object]", entry).get("name"))
                    for entry in cast("list[object]", repositories)
                    if isinstance(entry, dict)
                    and isinstance(cast("dict[str, object]", entry).get("name"), str)
                )
        self.installed_cache["installation"] = names
        return names

    def once(self, *, key: str) -> bool:
        """True exactly once per run for `key` (dedupes multi-row side effects)."""
        if self.marker_cache.get(key):
            return False
        self.marker_cache[key] = True
        return True
