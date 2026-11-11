"""Unit coverage for version-only release metadata recognition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import flake_retry_release as release


def test_modified_release_paths_are_required(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Adds, deletes, renames, and unavailable status data cannot pass the exception."""

    def unavailable(**_: object) -> str | None:
        return None

    monkeypatch.setattr(release, "_git_text", unavailable)
    assert not release.version_only_release_change(
        repo_root=tmp_path, change_paths={Path("pyproject.toml")}
    )
    for status in ("A\tpyproject.toml\n", "D\tpyproject.toml\n", "R100\ta\tpyproject.toml\n"):

        def status_text(*, value: str = status, **_: object) -> str | None:
            return value

        monkeypatch.setattr(release, "_git_text", status_text)
        assert not release.version_only_release_change(
            repo_root=tmp_path, change_paths={Path("pyproject.toml")}
        )

    def modified(**_: object) -> str | None:
        return "M\tpyproject.toml\n"

    monkeypatch.setattr(release, "_git_text", modified)
    assert not release.version_only_release_change(
        repo_root=tmp_path, change_paths={Path("pyproject.toml")}
    )


def test_release_recognition_requires_comparable_versions(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The narrow exception accepts a semantic release update and rejects uncertainty."""
    project = {"project": {"name": "example", "version": "2"}}
    lock = {"package": [{"name": "example", "version": "2"}]}

    def base(**_: object) -> str | None:
        return "base"

    def modified(**_: object) -> bool:
        return True

    def unavailable(**_: object) -> str | None:
        return None

    def same_versions(**kwargs: object) -> tuple[dict[str, Any], dict[str, Any]]:
        return (project, project) if kwargs["path"] == Path("pyproject.toml") else (lock, lock)

    monkeypatch.setattr(release, "comparison_revision", base)
    monkeypatch.setattr(release, "_changed_paths_are_modified", modified)
    monkeypatch.setattr(release, "_version_only_file", same_versions)
    assert not release.version_only_release_change(repo_root=tmp_path, change_paths=set())
    assert not release.version_only_release_change(
        repo_root=tmp_path, change_paths={Path("pyproject.toml")}
    )

    before_project = {"project": {"name": "example", "version": "1"}}
    before_lock = {"package": [{"name": "example", "version": "1"}]}

    def changed_versions(**kwargs: object) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            (before_project, project)
            if kwargs["path"] == Path("pyproject.toml")
            else (before_lock, lock)
        )

    monkeypatch.setattr(release, "_version_only_file", changed_versions)
    assert release.version_only_release_change(
        repo_root=tmp_path, change_paths={Path("pyproject.toml"), Path("uv.lock")}
    )
    monkeypatch.setattr(release, "comparison_revision", unavailable)
    assert not release.version_only_release_change(
        repo_root=tmp_path, change_paths={Path("pyproject.toml")}
    )
