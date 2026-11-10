"""Enumerate the first-party `.py` files a coverage data file does not hold.

Coverage.py lists only the modules a test run imported, and `per_file_coverage`
walks only the files coverage measured, so a first-party module that no test
imports is never judged although the ratified rule is 100% line and branch
coverage across the whole first-party surface. A coverage `source` allowlist
would list it, but the non-functional-requirements forbid one: the dev-tooling
checks run as subprocesses from a temporary cwd, where a relative `source`
would drop them. The remedy is this enumeration inside the verifier, against the
declared `source_tree_prefixes`, never a `source` key.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from livespec_dev_tooling.config import (
    GitLsFilesError,
    list_tracked_py,
    load_config,
    role_prefixes,
)

__all__: list[str] = ["find_unmeasured_first_party"]


def _resolved(*, repo_root: Path, name: str) -> Path:
    """Return `name` as an absolute resolved path, anchoring a relative one at the repo."""
    return (repo_root / name).resolve()


def find_unmeasured_first_party(
    *, repo_root: Path, measured_files: Iterable[str]
) -> tuple[str, ...] | None:
    """Return the repo-relative POSIX paths of tracked first-party files coverage never measured.

    A file is first-party when it is a tracked `.py` under one of the repository's
    configured `source_tree_prefixes` and present on disk (the index also lists a
    tracked file deleted from the working tree). A repository that declares no
    prefixes has no first-party surface, so nothing is listed.

    Returns `None` when the tracked files cannot be listed because `repo_root` is
    not a git working tree: an unavailable enumeration is not an empty one, and
    the caller decides what that means.
    """
    config = load_config(repo_root=repo_root)
    prefixes = role_prefixes(role=config.source_tree_prefixes)
    measured = {_resolved(repo_root=repo_root, name=name) for name in measured_files}
    try:
        tracked = list_tracked_py(repo_root=repo_root)
    except GitLsFilesError:
        return None
    first_party = (
        rel.as_posix()
        for rel in tracked
        if rel.as_posix().startswith(prefixes) and (repo_root / rel).is_file()
    )
    return tuple(
        sorted(
            posix
            for posix in first_party
            if _resolved(repo_root=repo_root, name=posix) not in measured
        )
    )
