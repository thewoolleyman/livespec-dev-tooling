"""The recovery authorization's serving build: the released principal plus its forge bypass.

Recovery authorization has two halves and both must be read. The principal that acts is
the controller's released package, so its serving version is the controller's; and the
consumer's default branch must let exactly one GitHub App bypass the ruleset that guards
it, always. A consumer whose controller is unverified, whose rulesets cannot be read, or
whose bypass list is empty, shared or not a single always-bypass App is unverified.
The forge is read with the operator's own `gh` credential; no consumer is credentialed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from livespec_dev_tooling.budgeted_gh import GhRead, gh_read
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["ForgeReader", "read_recovery_authorization"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
ForgeReader = Callable[..., GhRead]
_DEFAULT_BRANCH_REFS = frozenset({"~DEFAULT_BRANCH", "refs/heads/master", "refs/heads/main"})


def _api(*, read_forge: ForgeReader, path: str) -> object | None:
    answer = read_forge(args=["api", path])
    if answer.returncode != 0:
        return None
    try:
        return cast("object", strict_json(text=answer.stdout, limit=None))
    except (ValueError, IncidentJsonRefusalError):
        return None


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _list(*, value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _bypass_actors(*, read_forge: ForgeReader, base: str) -> list[dict[str, object]]:
    actors: list[dict[str, object]] = []
    for item in _list(value=_api(read_forge=read_forge, path=base)):
        summary = _mapping(value=item)
        if summary.get("enforcement") != "active" or summary.get("target") != "branch":
            continue
        detail = _mapping(value=_api(read_forge=read_forge, path=f"{base}/{summary.get('id')}"))
        ref_name = _mapping(value=_mapping(value=detail.get("conditions")).get("ref_name"))
        if not any(ref in _DEFAULT_BRANCH_REFS for ref in _list(value=ref_name.get("include"))):
            continue
        actors.extend(_mapping(value=a) for a in _list(value=detail.get("bypass_actors")))
    return actors


def read_recovery_authorization(
    *, repository: str, controller: str | None, read_forge: ForgeReader = gh_read
) -> str | None:
    """`<controller serving>+bypass-app-<id>` when exactly one App always bypasses, else None."""
    if controller is None:
        return None
    actors = _bypass_actors(read_forge=read_forge, base=f"repos/{repository}/rulesets")
    app = actors[0].get("actor_id") if len(actors) == 1 else None
    sole = len(actors) == 1 and actors[0].get("actor_type") == "Integration"
    always = len(actors) == 1 and actors[0].get("bypass_mode") == "always"
    return f"{controller}+bypass-app-{app}" if sole and always and type(app) is int else None
