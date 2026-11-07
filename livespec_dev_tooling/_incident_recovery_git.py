"""Reference-clone reads the recovery principal derives forge scope and trees from.

Every read goes through `_incident_inverse_git.IsolatedGit`, the same isolated
object view that verifies and builds the inverse, so a source checkout's
configuration, attributes or replacement refs cannot change a landed chain, a
patch digest or an inverse tree entry the principal sends to the forge.
"""

from __future__ import annotations

import hashlib
from functools import partial
from pathlib import Path
from typing import NamedTuple

from livespec_dev_tooling._incident_inverse_git import IsolatedGit

__all__: list[str] = ["LandedFacts", "LandedGit", "TreeChange"]


class LandedFacts(NamedTuple):
    """The complete landed chain the forge merged, read from immutable objects."""

    before_sha: str
    landed_commits: tuple[str, ...]
    landed_trees: tuple[str, ...]
    patch_sha256: str
    changed_paths: tuple[str, ...]
    messages: tuple[str, ...]


class TreeChange(NamedTuple):
    """One path an inverse tree changes against its base commit; sha None deletes it."""

    path: str
    mode: str
    sha: str | None


class LandedGit:
    """Reference-clone reads the recovery principal derives forge scope and trees from."""

    @staticmethod
    def fetch(*, root: Path, branch: str) -> None:
        """Bring the observed branch's objects into the independent reference clone."""
        _ = IsolatedGit.run(
            root=root,
            args=(
                "fetch",
                "--quiet",
                "--no-tags",
                "origin",
                f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
            ),
        )

    @staticmethod
    def facts(*, root: Path, merge_sha: str, count: int) -> LandedFacts:
        """The first-parent chain of `count` commits ending at `merge_sha`, and its patch."""
        with IsolatedGit.view(root=root) as (administration, objects):
            run = partial(
                IsolatedGit.run, root=root, administration=administration, objects=objects
            )
            listed = run(args=("rev-list", "--first-parent", "-n", str(count), merge_sha))
            commits = tuple(reversed(listed.decode().split()))
            before = run(args=("rev-parse", commits[0] + "^")).decode().strip()
            trees = tuple(
                run(args=("rev-parse", commit + "^{tree}")).decode().strip() for commit in commits
            )
            names = run(args=("diff", "--no-renames", "--name-only", "-z", before, merge_sha, "--"))
            messages = tuple(
                run(args=("show", "-s", "--format=%B", commit)).decode().strip()
                for commit in commits
            )
        patch = IsolatedGit.patch(root=root, before=before, merge=merge_sha)
        return LandedFacts(
            before_sha=before,
            landed_commits=commits,
            landed_trees=trees,
            patch_sha256=hashlib.sha256(patch).hexdigest(),
            changed_paths=tuple(sorted(names.decode().rstrip("\0").split("\0"))),
            messages=messages,
        )

    @staticmethod
    def changes(*, root: Path, base: str, tree: str) -> tuple[TreeChange, ...]:
        """Every path whose entry differs between `base`'s tree and `tree`, with modes."""
        with IsolatedGit.view(root=root) as (administration, objects):
            raw = IsolatedGit.run(
                root=root,
                administration=administration,
                objects=objects,
                args=("diff-tree", "-r", "-z", "--no-renames", base, tree),
            )
        fields = raw.decode().split("\0")
        result: list[TreeChange] = []
        for meta, path in zip(fields[0:-1:2], fields[1::2], strict=True):
            old_mode, new_mode, _old_sha, new_sha, status = meta.lstrip(":").split()
            deleted = status == "D"
            result.append(
                TreeChange(
                    path=path,
                    mode=old_mode if deleted else new_mode,
                    sha=None if deleted else new_sha,
                )
            )
        return tuple(result)

    @staticmethod
    def blob(*, root: Path, sha: str) -> bytes:
        """The exact bytes of one blob from the reference clone's object store."""
        with IsolatedGit.view(root=root) as (administration, objects):
            return IsolatedGit.run(
                root=root,
                administration=administration,
                objects=objects,
                args=("cat-file", "blob", sha),
            )
