"""Shared types + GitHub-access seam for the fleet-membership contract.

Carries the value types every fleet module exchanges (member, row
outcomes, gh results) plus `FleetContext` — the single seam through
which all GitHub state flows. Row functions receive a context and
return outcome VALUES; they never log and never touch `subprocess`
directly, so the obligation table stays hermetically testable with a
canned-response runner. The default runner shells out to the `gh`
CLI (the family precedent for GitHub reads — see
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
    """One manifest entry: a family repo and its repo class."""

    repo: str
    repo_class: str


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
    tree_cache: dict[str, TreeState] = field(default_factory=dict)
    installed_cache: dict[str, frozenset[str] | None] = field(default_factory=dict)
    marker_cache: dict[str, bool] = field(default_factory=dict)

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

    def file_text(self, *, repo: str, path: str) -> str | None:
        """Raw master-tree file content via the contents API; None on failure."""
        result = self.run_gh(
            args=[
                "api",
                f"repos/{self.owner}/{repo}/contents/{path}",
                "-H",
                "Accept: application/vnd.github.raw",
            ]
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def tree(self, *, repo: str) -> TreeState:
        """Memoized recursive master tree for `repo` (one API call per run)."""
        cached = self.tree_cache.get(repo)
        if cached is not None:
            return cached
        payload = self.api_object(path=f"repos/{self.owner}/{repo}/git/trees/master?recursive=1")
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
