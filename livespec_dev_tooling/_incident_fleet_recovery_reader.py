"""The recovery authorization's serving build: the released principal plus its forge bypass.

Recovery authorization has two halves and both must be read. The principal that acts is
the controller's released package, so its serving version is the controller's; and the
consumer's default branch must let exactly one GitHub App bypass the rulesets that guard
it, always. Every active branch ruleset is evaluated against the default branch the way
GitHub evaluates `conditions.ref_name`: `~DEFAULT_BRANCH`, `~ALL` and `refs/heads/...`
patterns, includes minus excludes. The bypass actors of every ruleset that guards the
default branch are counted together.

The read fails CLOSED. A consumer is unverified when its controller is unverified; when
its repository, its ruleset list or ANY active branch ruleset's detail cannot be read;
when a ruleset's conditions or bypass list cannot be evaluated (an unknown condition, a
pattern this reader cannot match with certainty, an absent bypass list); or when the
bypass actors are not exactly one always-bypass App. An unreadable ruleset is never
taken to be one that does not guard the branch. The forge is read with the operator's
own `gh` credential; no consumer is credentialed.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import cast

from livespec_dev_tooling.budgeted_gh import GhRead, gh_read
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["ForgeReader", "read_recovery_authorization"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
ForgeReader = Callable[..., GhRead]
_BRANCH_TOKENS = frozenset({"~DEFAULT_BRANCH", "~ALL"})
_HEADS = "refs/heads/"
# Repository-scoping conditions of an organization ruleset: the forge listed the ruleset
# for this repository, so they already hold. Any other condition key is not evaluated.
_REPOSITORY_SCOPES = frozenset({"repository_name", "repository_id", "repository_property"})
_UNMATCHABLE = re.compile(r"[\[\]{}\\!]")


def _api(*, read_forge: ForgeReader, path: str) -> object | None:
    answer = read_forge(args=["api", path])
    if answer.returncode != 0:
        return None
    try:
        return cast("object", strict_json(text=answer.stdout, limit=None))
    except (ValueError, IncidentJsonRefusalError):
        return None


def _strings(*, value: object) -> list[str] | None:
    items = cast("list[object]", value) if isinstance(value, list) else None
    if items is None or not all(isinstance(item, str) for item in items):
        return None
    return cast("list[str]", items)


def _pattern_regex(*, pattern: str, star: str) -> re.Pattern[str]:
    parts = (re.escape(part) for part in pattern.replace("**", "\0").split("*"))
    return re.compile(star.join(parts).replace("\0", ".*").replace(r"\?", "[^/]"))


def _matches(*, pattern: str, branch: str) -> bool | None:
    """Whether a ref-name pattern covers the default branch; None when that is uncertain."""
    if pattern in _BRANCH_TOKENS:
        return True
    if not pattern.startswith(_HEADS) or _UNMATCHABLE.search(pattern):
        return None
    ref = f"{_HEADS}{branch}"
    within = _pattern_regex(pattern=pattern, star="[^/]*").fullmatch(ref) is not None
    across = _pattern_regex(pattern=pattern, star=".*").fullmatch(ref) is not None
    return within if within == across else None


def _guards_default_branch(*, conditions: object, branch: str) -> bool | None:
    """Whether `conditions` select the default branch; None when they cannot be evaluated."""
    if not isinstance(conditions, dict):
        return None
    keys = cast("dict[str, object]", conditions)
    ref_name = keys.get("ref_name")
    if set(keys) - _REPOSITORY_SCOPES - {"ref_name"} or not isinstance(ref_name, dict):
        return None
    names = cast("dict[str, object]", ref_name)
    include = _strings(value=names.get("include"))
    exclude = _strings(value=names.get("exclude", []))
    if include is None or exclude is None:
        return None
    included = [_matches(pattern=p, branch=branch) for p in include]
    excluded = [_matches(pattern=p, branch=branch) for p in exclude]
    if None in included or None in excluded:
        return None
    return any(included) and not any(excluded)


def _bypass_actors(*, read_forge: ForgeReader, repository: str) -> list[dict[str, object]] | None:
    """Bypass actors of every ruleset guarding the default branch; None when any read fails."""
    repo = _api(read_forge=read_forge, path=f"repos/{repository}")
    branch = (
        cast("dict[str, object]", repo).get("default_branch") if isinstance(repo, dict) else None
    )
    listed = _api(read_forge=read_forge, path=f"repos/{repository}/rulesets")
    if not isinstance(branch, str) or not branch or not isinstance(listed, list):
        return None
    actors: list[dict[str, object]] = []
    for item in cast("list[object]", listed):
        if not isinstance(item, dict):
            return None
        summary = cast("dict[str, object]", item)
        if summary.get("enforcement") != "active" or summary.get("target") != "branch":
            continue
        detail = _api(
            read_forge=read_forge, path=f"repos/{repository}/rulesets/{summary.get('id')}"
        )
        if not isinstance(detail, dict):
            return None
        ruleset = cast("dict[str, object]", detail)
        guards = _guards_default_branch(conditions=ruleset.get("conditions"), branch=branch)
        bypass = ruleset.get("bypass_actors")
        if guards is None or (guards and not isinstance(bypass, list)):
            return None
        if guards:
            for actor in cast("list[object]", bypass):
                if not isinstance(actor, dict):
                    return None
                actors.append(cast("dict[str, object]", actor))
    return actors


def read_recovery_authorization(
    *, repository: str, controller: str | None, read_forge: ForgeReader = gh_read
) -> str | None:
    """`<controller serving>+bypass-app-<id>` when exactly one App always bypasses, else None."""
    if controller is None:
        return None
    actors = _bypass_actors(read_forge=read_forge, repository=repository)
    if actors is None or len(actors) != 1:
        return None
    actor = actors[0]
    app = actor.get("actor_id")
    sole = actor.get("actor_type") == "Integration" and actor.get("bypass_mode") == "always"
    return f"{controller}+bypass-app-{app}" if sole and type(app) is int else None
