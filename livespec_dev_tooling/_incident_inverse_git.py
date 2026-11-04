"""Git plumbing for a complete incident patch without checking out old files."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from functools import partial
from pathlib import Path

from livespec_dev_tooling._incident_inverse_types import InversePlan, LandedIncident

__all__: list[str] = ["build_inverse", "scope_matches_git"]

_GIT_TIMEOUT = 15


def _git(
    *,
    root: Path,
    args: tuple[str, ...],
    data: bytes | None = None,
    index: str | None = None,
    administration: Path | None = None,
    objects: str | None = None,
) -> bytes:
    # Never inherit another checkout's index, git-dir, config injection or hook env.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1")
    if index is not None:
        environment["GIT_INDEX_FILE"] = index
    if administration is not None:
        environment["GIT_DIR"] = str(administration)
    if objects is not None:
        environment["GIT_OBJECT_DIRECTORY"] = objects
    return subprocess.run(  # noqa: S603 — fixed Git plumbing argv, no shell or candidate command.
        ["git", "-C", str(root), *args],  # noqa: S607 — configured Git executable on PATH.
        input=data,
        capture_output=True,
        check=True,
        timeout=_GIT_TIMEOUT,
        env=environment,
    ).stdout


def _sha(*, value: str) -> bool:
    return re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is not None


def scope_matches_git(*, root: Path, scope: LandedIncident, expected_head: str) -> bool:
    """Verify full chain, trees and binary patch against authenticated forge scope."""
    hashes = (
        scope.before_sha,
        scope.merge_sha,
        scope.original_base_sha,
        scope.original_head_sha,
        expected_head,
        *scope.landed_commits,
        *scope.landed_trees,
    )
    if (
        not all(_sha(value=value) for value in hashes)
        or not scope.landed_commits
        or scope.landed_commits[-1] != scope.merge_sha
        or len(scope.landed_commits) != len(scope.landed_trees)
        or re.fullmatch(r"[0-9a-f]{64}", scope.authority_sha256) is None
    ):
        return False
    chain = (
        _git(root=root, args=("rev-list", "--reverse", f"{scope.before_sha}..{scope.merge_sha}"))
        .decode()
        .splitlines()
    )
    if tuple(chain) != scope.landed_commits:
        return False
    previous = scope.before_sha
    for commit, tree in zip(scope.landed_commits, scope.landed_trees, strict=True):
        parents = (
            _git(root=root, args=("rev-list", "--parents", "-n", "1", commit)).decode().split()
        )
        actual_tree = _git(root=root, args=("rev-parse", commit + "^{tree}")).decode().strip()
        if parents != [commit, previous] or actual_tree != tree:
            return False
        previous = commit
    _ = _git(root=root, args=("merge-base", "--is-ancestor", scope.merge_sha, expected_head))
    patch = _patch(root=root, scope=scope)
    paths = (
        _git(
            root=root,
            args=(
                "diff",
                "--no-renames",
                "--name-only",
                "-z",
                scope.before_sha,
                scope.merge_sha,
                "--",
            ),
        )
        .decode()
        .rstrip("\0")
        .split("\0")
    )
    return (
        bool(patch)
        and hashlib.sha256(patch).hexdigest() == scope.patch_sha256
        and tuple(sorted(paths)) == tuple(sorted(scope.changed_paths))
    )


def _patch(*, root: Path, scope: LandedIncident) -> bytes:
    return _git(
        root=root,
        args=(
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            scope.before_sha,
            scope.merge_sha,
            "--",
        ),
    )


def build_inverse(*, root: Path, scope: LandedIncident, expected_head: str) -> InversePlan:
    """Apply the entire inverse with three-way merge in an isolated scratch index.

    The original index, checkout, branch and untracked files are untouched.
    A same-line conflict leaves only disposable index state and raises Git's
    explicit refusal; there is no fallback to restoring full parent files.
    """
    with tempfile.TemporaryDirectory(prefix="incident-inverse-") as temporary:
        administration = Path(temporary) / "repository.git"
        object_format = _git(root=root, args=("rev-parse", "--show-object-format")).decode().strip()
        objects = (
            _git(root=root, args=("rev-parse", "--path-format=absolute", "--git-path", "objects"))
            .decode()
            .strip()
        )
        _ = _git(
            root=root,
            args=(
                "init",
                "--bare",
                "--template=",
                f"--object-format={object_format}",
                str(administration),
            ),
        )
        (administration / "info").mkdir(exist_ok=True)
        _ = (administration / "info" / "attributes").write_text(
            "* merge=text -filter -ident -text -eol -working-tree-encoding\n", encoding="utf-8"
        )
        index = str(Path(temporary) / "index")
        run = partial(_git, root=root, administration=administration, objects=objects, index=index)
        _ = run(args=("read-tree", expected_head))
        _ = run(
            args=("apply", "--cached", "--reverse", "--3way", "--whitespace=nowarn"),
            data=_patch(root=root, scope=scope),
        )
        tree = run(args=("write-tree",)).decode().strip()
        patch = run(
            args=(
                "diff",
                "--cached",
                "--binary",
                "--full-index",
                "--no-ext-diff",
                "--no-textconv",
                expected_head,
                "--",
            ),
        )
    return InversePlan(scope=scope, expected_head=expected_head, tree_sha=tree, inverse_patch=patch)
