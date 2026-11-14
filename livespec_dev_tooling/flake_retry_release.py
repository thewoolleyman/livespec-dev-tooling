"""Recognize the narrow release metadata delta safe for flake retries."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.flake_retry_changes import comparison_revision
from livespec_dev_tooling.gate_remote_invocation import Failure, default_gate_command_runner

if sys.version_info >= (3, 11):  # pragma: no cover — the supported floor uses tomli.
    import tomllib as _toml
else:
    _VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
    if str(_VENDOR_DIR) not in sys.path:
        sys.path.insert(0, str(_VENDOR_DIR))
    import tomli as _toml

__all__: list[str] = ["version_only_release_change"]

_RELEASE_PATHS = frozenset({Path("pyproject.toml"), Path("uv.lock")})
_STATUS_FIELDS = 2
_PACKAGE_VERSION_COUNT = 2


def _git_text(*, repo_root: Path, args: list[str]) -> str | None:
    """Read text from git, treating an unavailable comparison as unsafe."""
    invoked = default_gate_command_runner(argv=["git", *args], cwd=repo_root)
    if isinstance(invoked, Failure):
        return None
    completed = invoked.unwrap()
    return completed.stdout if completed.returncode == 0 else None


def _changed_paths_are_modified(*, repo_root: Path, comparison: str, paths: set[Path]) -> bool:
    """Reject additions, deletions, renames, and any change git cannot classify."""
    status = _git_text(
        repo_root=repo_root,
        args=["diff", "--name-status", "--find-renames", comparison, "--", *map(str, paths)],
    )
    if status is None:
        return False
    observed = {
        Path(parts[1])
        for line in status.splitlines()
        if (parts := line.split("\t")) and len(parts) == _STATUS_FIELDS and parts[0] == "M"
    }
    return observed == paths and len(status.splitlines()) == len(paths)


def _parse_toml(*, text: str) -> dict[str, Any] | None:
    """Parse a TOML document without allowing malformed release data through."""
    try:
        return _toml.loads(text)
    except _toml.TOMLDecodeError:
        return None


def _changed_version_only(
    *, before: dict[str, Any], after: dict[str, Any], path: tuple[str, ...]
) -> bool:
    """Return whether the selected version key is the only semantic TOML change."""
    original = deepcopy(before)
    current = deepcopy(after)
    try:
        old_parent: dict[str, Any] = original
        new_parent: dict[str, Any] = current
        for component in path[:-1]:
            old_parent = old_parent[component]
            new_parent = new_parent[component]
        old_version = old_parent.pop(path[-1])
        new_version = new_parent.pop(path[-1])
    except (KeyError, TypeError):
        return False
    return (
        isinstance(old_version, str)
        and isinstance(new_version, str)
        and old_version != new_version
        and original == current
    )


def _own_package_version_only(
    *, before: dict[str, Any], after: dict[str, Any], package_name: str
) -> bool:
    """Compare lockfiles after removing only this repository package's version."""
    original = deepcopy(before)
    current = deepcopy(after)
    raw_packages: tuple[object, object] = (original.get("package"), current.get("package"))
    changed_versions = 0
    for raw_package_list in raw_packages:
        if not isinstance(raw_package_list, list):
            return False
        packages = cast(list[object], raw_package_list)
        for raw_package in packages:
            if not isinstance(raw_package, dict):
                return False
            package = cast(dict[str, Any], raw_package)
            if package.get("name") == package_name:
                version = package.pop("version", None)
                if not isinstance(version, str):
                    return False
                changed_versions += 1
    return changed_versions == _PACKAGE_VERSION_COUNT and original == current


def _version_only_file(
    *, repo_root: Path, comparison: str, path: Path
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Read comparable before/after TOML mappings for one root release file."""
    before = _git_text(repo_root=repo_root, args=["show", f"{comparison}:{path}"])
    try:
        after = (repo_root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if before is None:
        return None
    old_data = _parse_toml(text=before)
    new_data = _parse_toml(text=after)
    return (old_data, new_data) if old_data is not None and new_data is not None else None


def version_only_release_change(*, repo_root: Path, change_paths: set[Path]) -> bool:
    """Allow only root version deltas made by a release commit.

    The check deliberately compares parsed documents and rejects every filesystem
    operation except a normal modification, so unreadable, added, removed, and
    renamed release metadata leaves retries withheld.
    """
    release_paths = change_paths & _RELEASE_PATHS
    if not release_paths:
        return False
    comparison = comparison_revision(repo_root=repo_root)
    if comparison is None or not _changed_paths_are_modified(
        repo_root=repo_root, comparison=comparison, paths=release_paths
    ):
        return False
    pyproject = _version_only_file(
        repo_root=repo_root,
        comparison=comparison,
        path=Path("pyproject.toml"),
    )
    if pyproject is None:
        return False
    before_project, after_project = pyproject
    if Path("pyproject.toml") in release_paths and not _changed_version_only(
        before=before_project, after=after_project, path=("project", "version")
    ):
        return False
    if Path("uv.lock") not in release_paths:
        return True
    package_name = after_project.get("project", {}).get("name")
    lockfile = _version_only_file(repo_root=repo_root, comparison=comparison, path=Path("uv.lock"))
    return (
        isinstance(package_name, str)
        and lockfile is not None
        and _own_package_version_only(
            before=lockfile[0], after=lockfile[1], package_name=package_name
        )
    )
