"""The fleet manifest, read from livespec master over git, for the operator recipes.

Shared by `adopt_orchestrator_build` and `ensure_plugins_fleet`, which both
need the member set and neither may keep a member list of its own.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.fleet._manifest_git import (
    GitReader,
    GitReadRefused,
    default_git_reader,
    git_file_text,
)
from livespec_dev_tooling.fleet._origin_remote import owner_or_origin
from livespec_dev_tooling.fleet.contract import parse_manifest

# `returns` is vendored. This module is reached from process entry points, so
# it cannot rely on an earlier sibling import having placed it on sys.path.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "MANIFEST_PATH",
    "MANIFEST_REPO",
    "ManifestUnreadable",
    "fetch_master_manifest",
    "manifest_names",
    "master_manifest_source",
]

MANIFEST_REPO = "livespec"
MANIFEST_PATH = ".livespec-fleet-manifest.jsonc"


@dataclass(frozen=True, kw_only=True)
class ManifestUnreadable:
    """Why the manifest read did not yield text."""

    cause: str


def fetch_master_manifest(*, owner: str, read_git: GitReader) -> str | GitReadRefused:
    """The fleet manifest bytes from livespec master, or the refusal that stopped the read."""
    read = git_file_text(run=read_git, owner=owner, repo=MANIFEST_REPO, path=MANIFEST_PATH)
    if isinstance(read, IOFailure):
        return unsafe_perform_io(read.failure())
    return unsafe_perform_io(read.unwrap())


def manifest_names(*, manifest_source: str) -> frozenset[str]:
    """Every repository name in the manifest's `fleet` and `adopters` arrays."""
    parsed = parse_manifest(source=manifest_source).unwrap()
    return frozenset(member.repo for member in parsed.members) | frozenset(
        adopter.repo for adopter in parsed.adopters
    )


def master_manifest_source() -> str | ManifestUnreadable:  # pragma: no cover
    """The manifest text read for this checkout's origin owner, or why it is unreadable."""
    resolved = owner_or_origin(argument=None)
    if isinstance(resolved, IOFailure):
        failure = unsafe_perform_io(resolved.failure())
        return ManifestUnreadable(cause=f"owner unresolvable [{failure.reason}]: {failure.detail}")
    owner = unsafe_perform_io(resolved.unwrap())
    manifest = fetch_master_manifest(owner=owner, read_git=default_git_reader)
    if isinstance(manifest, GitReadRefused):
        where = f"{owner}/{MANIFEST_REPO} master"
        refusal = f"[{manifest.kind}, exit {manifest.returncode}]: {manifest.detail}"
        return ManifestUnreadable(cause=f"fleet manifest unreadable from {where} {refusal}")
    return manifest
