"""Repair a Claude marketplace clone whose origin names a stale owner.

After the livespec-ai org move a host's `~/.claude/plugins/marketplaces/<name>`
clone can keep an origin naming the OLD owner while `known_marketplaces.json`
declares `livespec-ai/<repo>`. Claude Code then hides the clone from
`plugin marketplace list` and `ensure-plugins` fails with "not found in
marketplace". This module rewrites ONLY the clone's `origin` URL to the declared
source's canonical form (https stays https, ssh stays ssh; the `github`
shorthand maps to https). It never touches an installed plugin build or a
project's orchestrator/factory dispatch build, and it ignores every marketplace
whose declared repo is outside the livespec-ai org.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

__all__: list[str] = ["OriginReport", "git_origin", "git_set_origin", "repair_marketplace_origins"]

_ORG = "livespec-ai"
_GITHUB_PATH = re.compile(
    r"^(?:https?://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


@dataclass(frozen=True, kw_only=True)
class OriginReport:
    """Notices (rewrites made, sources reported) and findings (rewrites that failed)."""

    notices: tuple[str, ...]
    findings: tuple[str, ...]


def _owner_repo(*, url: str) -> tuple[str, str] | None:
    match = _GITHUB_PATH.match(url.strip())
    return (match["owner"], match["repo"]) if match else None


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _declared_github(*, fields: dict[str, object]) -> tuple[str, str] | str | None:
    repo = str(fields.get("repo", ""))
    owner, _, name = repo.partition("/")
    mapped = (owner, name) if name and "/" not in name else f"malformed github repo {repo!r}"
    return mapped if owner == _ORG else None


def _declared_git(*, fields: dict[str, object]) -> tuple[str, str] | str | None:
    url = str(fields.get("url", ""))
    parsed = _owner_repo(url=url)
    reason = f"git source {url!r} is not a github.com URL" if _ORG in url else None
    return parsed if parsed is not None and parsed[0] == _ORG else reason


def _declared(*, source: object) -> tuple[str, str] | str | None:
    """`(owner, repo)` when mappable, a reason string when livespec-ai but not, else None."""
    fields = _mapping(value=source)
    handlers = {"github": _declared_github, "git": _declared_git}
    handler = handlers.get(str(fields.get("source", "")))
    return handler(fields=fields) if handler is not None else None


def _same_repo(*, current: str, declared: tuple[str, str]) -> bool:
    parsed = _owner_repo(url=current)
    return parsed is not None and parsed[0].lower() == declared[0] and parsed[1] == declared[1]


def _canonical(*, current: str, declared: tuple[str, str]) -> str:
    owner, repo = declared
    if current.strip().startswith(("git@", "ssh://")):
        return f"git@github.com:{owner}/{repo}.git"
    return f"https://github.com/{owner}/{repo}.git"


def repair_marketplace_origins(
    *,
    known_text: str,
    read_origin: Callable[..., str | None],
    set_origin: Callable[..., bool],
) -> OriginReport:
    """Rewrite each livespec-ai marketplace clone's stale origin; touch nothing else."""
    try:
        known = json.loads(known_text)
    except json.JSONDecodeError:
        return OriginReport(notices=(), findings=())
    notices: list[str] = []
    findings: list[str] = []
    for name, entry in _mapping(value=known).items():
        record = _mapping(value=entry)
        declared = _declared(source=record.get("source"))
        location = record.get("installLocation")
        current = (
            read_origin(clone=location)
            if declared is not None and isinstance(location, str)
            else None
        )
        if current is None or declared is None:
            continue
        if isinstance(declared, str):
            notices.append(
                f"marketplace {name}: not repaired, declared source unmappable ({declared})"
            )
            continue
        if _same_repo(current=current, declared=declared):
            continue
        url = _canonical(current=current, declared=declared)
        if set_origin(clone=location, url=url):
            notices.append(f"marketplace {name}: origin {current} rewritten to {url}")
        else:
            findings.append(f"marketplace {name}: could not rewrite origin {current} to {url}")
    return OriginReport(notices=tuple(notices), findings=tuple(findings))


def _git(*, clone: str, args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", clone, *args),
        capture_output=True,
        text=True,
        check=False,
    )


def git_origin(*, clone: str) -> str | None:
    """The clone's `origin` URL, or None when it is not a git clone with an origin."""
    done = _git(clone=clone, args=("remote", "get-url", "origin"))
    return done.stdout.strip() if done.returncode == 0 else None


def git_set_origin(*, clone: str, url: str) -> bool:
    """Point the clone's `origin` at `url`; True when git accepted it."""
    done = _git(clone=clone, args=("remote", "set-url", "origin", url))
    return done.returncode == 0
