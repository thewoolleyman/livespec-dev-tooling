"""The local-or-remote whole-tree read shared by fleet conformance rows."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

# `returns` is vendored, so this module must establish the package-local path
# itself rather than relying on whichever sibling happened to import first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOSuccess  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._snapshot import (  # noqa: E402
    GhDownloader,
    SnapshotResult,
    SnapshotUnavailable,
    TreeSnapshot,
    memoized_snapshot,
)
from livespec_dev_tooling.fleet._tree_state import TreeState  # noqa: E402

__all__: list[str] = ["member_tree_snapshot"]


class SnapshotContext(Protocol):
    """The narrow `FleetContext` surface the whole-tree read needs."""

    @property
    def local_repo(self) -> str | None: ...

    @property
    def local_root(self) -> Path | None: ...

    @property
    def owner(self) -> str: ...

    @property
    def download_gh(self) -> GhDownloader: ...

    @property
    def snapshot_cache(self) -> dict[str, SnapshotResult]: ...

    def tree(self, *, repo: str) -> TreeState: ...

    def canonical_ref(self, *, repo: str) -> str: ...

    def record_read_failure(
        self, *, operation: str, path: str, returncode: int, kind: str, detail: str
    ) -> None: ...


def member_tree_snapshot(*, ctx: SnapshotContext, repo: str) -> SnapshotResult:
    """Return the self checkout or a sibling's canonical-ref archive once per run."""
    cached = ctx.snapshot_cache.get(repo)
    if cached is not None:
        return cached
    if ctx.local_root is not None and repo == ctx.local_repo:
        tree = ctx.tree(repo=repo)
        if not tree.readable:
            unavailable = SnapshotUnavailable(
                repo=repo,
                ref="local-checkout",
                returncode=0,
                kind="local_tree_unreadable",
                detail="git could not read the checked-out commit tree",
            )
            ctx.record_read_failure(
                operation="local_tree",
                path=f"{repo}@local-checkout",
                returncode=unavailable.returncode,
                kind=unavailable.kind,
                detail=unavailable.detail,
            )
            result = IOFailure(unavailable)
        else:
            result = IOSuccess(
                TreeSnapshot(
                    repo=repo,
                    ref="local-checkout",
                    root=ctx.local_root,
                    file_count=len(tree.paths),
                )
            )
        ctx.snapshot_cache[repo] = result
        return result
    return memoized_snapshot(
        cache=ctx.snapshot_cache,
        download=ctx.download_gh,
        owner=ctx.owner,
        repo=repo,
        ref=ctx.canonical_ref(repo=repo),
        record=ctx.record_read_failure,
    )
