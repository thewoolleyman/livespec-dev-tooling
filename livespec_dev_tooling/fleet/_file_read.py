"""A sibling's file text at its canonical ref, read at most once per run.

Split out of `_context.py`, which sat at 249 of its 250-LLOC hard ceiling.
The read is the fleet sweep's dominant GitHub consumer: MEASURED 2026-11-15
(`livespec-dev-tooling-bcwf2z`), one `check-fleet-conformance --member-ci`
sweep made 521 core requests on the livespec-ai org App installation, whose
budget is 5,000/h. 405 were per-file `contents/<path>?ref=` reads, and 53% of
the whole sweep repeated a read the same process had already made.

Two things remove that cost, and neither changes what a read ANSWERS:

- A SUCCESSFUL read is memoized by `(repo, path, ref)`. A failed read is not:
  a rate-limited or transient read must stay retryable on the next call, and
  every failing call must still append its own cause to `read_failures`,
  which `_credential_preflight` and the cause reports count per call.
- A member whose tarball this run ALREADY fetched (`snapshot_cache`) at the
  SAME ref serves the file from that extracted tree, with no contents call.
  The ref check is what keeps `file_text` and `tree` pinned to one ref. A path
  the snapshot does not hold as a regular file falls through to the contents
  API, because the snapshot skips symlinks (which the contents API resolves to
  their target's bytes) and an absent path must still be reported the way
  GitHub reports it. An unreadable file is therefore never turned into an
  absent one here: every case the snapshot cannot answer exactly is asked of
  GitHub, as before.

The module is imported BY `_context` and imports nothing from it; the context
surface it needs is the `FileReadContext` protocol below.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._gh_runner import GhRunner, gh_answer  # noqa: E402
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._read_failure import classify_gh_failure  # noqa: E402
from livespec_dev_tooling.fleet._snapshot import SnapshotResult  # noqa: E402

__all__: list[str] = ["remote_file_text"]


class FileReadContext(Protocol):
    """The narrow `FleetContext` surface a remote file read needs."""

    @property
    def owner(self) -> str: ...

    @property
    def run_gh(self) -> GhRunner: ...

    @property
    def snapshot_cache(self) -> dict[str, SnapshotResult]: ...

    @property
    def file_cache(self) -> dict[str, str]: ...

    def canonical_ref(self, *, repo: str) -> str: ...

    def record_not_performed(
        self, *, operation: str, path: str, failure: InvocationNotPerformed
    ) -> None: ...

    def record_read_failure(
        self, *, operation: str, path: str, returncode: int, kind: str, detail: str
    ) -> None: ...


def _snapshot_text(*, ctx: FileReadContext, repo: str, path: str, ref: str) -> str | None:
    """The file from this run's already-fetched `repo` tarball at `ref`, else None.

    None means only "the snapshot cannot answer this exactly" — no snapshot,
    another ref, not a regular file there, or bytes that are not UTF-8 — and
    sends the caller to the contents API. It never means "absent".
    """
    cached = ctx.snapshot_cache.get(repo)
    if not isinstance(cached, IOSuccess):
        return None
    snapshot = unsafe_perform_io(cached.unwrap())
    candidate = snapshot.root / path
    if snapshot.ref != ref or not candidate.is_file():
        return None
    try:
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _contents_text(*, ctx: FileReadContext, repo: str, path: str, ref: str) -> str | None:
    """One `contents/<path>?ref=<ref>` read; None on failure, cause preserved."""
    result = gh_answer(
        outcome=ctx.run_gh(
            args=[
                "api",
                f"repos/{ctx.owner}/{repo}/contents/{path}?ref={ref}",
                "-H",
                "Accept: application/vnd.github.raw",
            ]
        )
    )
    if isinstance(result, InvocationNotPerformed):
        # A file this run never managed to ASK about is not an absent
        # file, and the genuine-absence guard downstream reads this.
        ctx.record_not_performed(operation="contents", path=f"{repo}:{path}", failure=result)
        return None
    if result.returncode != 0:
        ctx.record_read_failure(
            operation="contents",
            path=f"{repo}:{path}",
            returncode=result.returncode,
            kind=classify_gh_failure(stderr=result.stderr),
            detail=result.stderr,
        )
        return None
    return result.stdout


def remote_file_text(*, ctx: FileReadContext, repo: str, path: str) -> str | None:
    """`repo`'s `path` at its canonical ref: memo, then snapshot, then contents API."""
    ref = ctx.canonical_ref(repo=repo)
    key = f"{repo}:{path}@{ref}"
    cached = ctx.file_cache.get(key)
    if cached is not None:
        return cached
    text = _snapshot_text(ctx=ctx, repo=repo, path=path, ref=ref)
    if text is None:
        text = _contents_text(ctx=ctx, repo=repo, path=path, ref=ref)
    if text is not None:
        ctx.file_cache[key] = text
    return text
