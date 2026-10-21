"""Canonical remote-ref resolution shared by fleet context reads."""

from __future__ import annotations

from typing import Protocol, cast

__all__: list[str] = ["resolve_canonical_ref"]


_CANONICAL_REF = "master"


class CanonicalRefContext(Protocol):
    """The narrow context surface canonical-ref resolution needs."""

    @property
    def owner(self) -> str: ...

    @property
    def ref_cache(self) -> dict[str, str]: ...

    def api_object(self, *, path: str, operation: str = "api") -> object | None: ...


def resolve_canonical_ref(*, ctx: CanonicalRefContext, repo: str) -> str:
    """Resolve and memoize `repo`'s default branch, falling back to `master`."""
    cached = ctx.ref_cache.get(repo)
    if cached is not None:
        return cached
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{repo}", operation="repo_metadata")
    resolved = _CANONICAL_REF
    if isinstance(payload, dict):
        branch = cast("dict[str, object]", payload).get("default_branch")
        if isinstance(branch, str) and branch:
            resolved = branch
    ctx.ref_cache[repo] = resolved
    return resolved
