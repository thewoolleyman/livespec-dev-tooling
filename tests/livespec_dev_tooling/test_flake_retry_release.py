"""Unit coverage for version-only release metadata recognition."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling import flake_retry_release as release
from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun

_IDENTITY = ("-c", "user.email=flake@example.invalid", "-c", "user.name=flake")
_PYPROJECT = "[project]\nname = 'example'\nversion = '{version}'\n"
_UV_LOCK = "version = 1\n\n[[package]]\nname = 'example'\nversion = '{version}'\n"


def _base_revision(*, repo_root: Path) -> str | None:
    """Supply a known base for a test that stubs Git's text query."""
    _ = repo_root
    return "base"


def _git(*, repo: Path, args: list[str]) -> None:
    """Run one fixture-local Git command."""
    _ = subprocess.run(
        ["git", *_IDENTITY, *args], cwd=repo, check=True, capture_output=True, text=True
    )


def _repository(*, root: Path) -> Path:
    """Build a repository whose remote master names its release baseline."""
    repo = root / "repo"
    repo.mkdir()
    _git(repo=repo, args=["init", "-q", "-b", "master", "."])
    _ = (repo / "pyproject.toml").write_text(_PYPROJECT.format(version="1"), encoding="utf-8")
    _ = (repo / "uv.lock").write_text(_UV_LOCK.format(version="1"), encoding="utf-8")
    _git(repo=repo, args=["add", "."])
    _git(repo=repo, args=["commit", "-qm", "base"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", "HEAD"])
    return repo


def _commit_release(*, repo: Path, pyproject: str, lockfile: str) -> None:
    """Commit the requested metadata update against the fixture baseline."""
    _ = (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    _ = (repo / "uv.lock").write_text(lockfile, encoding="utf-8")
    _git(repo=repo, args=["add", "pyproject.toml", "uv.lock"])
    _git(repo=repo, args=["commit", "-qm", "release"])


def test_a_real_git_release_delta_is_the_only_allowed_exception(*, tmp_path: Path) -> None:
    """Only the two package version values may differ from the release baseline."""
    repo = _repository(root=tmp_path)
    _commit_release(
        repo=repo,
        pyproject=_PYPROJECT.format(version="2"),
        lockfile=_UV_LOCK.format(version="2"),
    )

    assert release.version_only_release_change(
        repo_root=repo, change_paths={Path("pyproject.toml"), Path("uv.lock")}
    )


def test_a_pyproject_only_release_delta_is_safe_when_its_version_is_the_only_change(
    *, tmp_path: Path
) -> None:
    """A lockfile is optional when only the project version changed."""
    repo = _repository(root=tmp_path)
    _commit_release(
        repo=repo,
        pyproject=_PYPROJECT.format(version="2"),
        lockfile=_UV_LOCK.format(version="1"),
    )

    assert release.version_only_release_change(
        repo_root=repo, change_paths={Path("pyproject.toml")}
    )


def test_no_release_metadata_path_cannot_use_the_exception(*, tmp_path: Path) -> None:
    """The release check is never a general exemption for unrelated changes."""
    assert not release.version_only_release_change(repo_root=tmp_path, change_paths=set())


@pytest.mark.parametrize(
    ("pyproject", "lockfile"),
    [
        ("[project\n", _UV_LOCK.format(version="2")),
        ("[project]\nname = 'example'\n", _UV_LOCK.format(version="2")),
        ("[project]\nname = 'example'\nversion = 2\n", _UV_LOCK.format(version="2")),
        (_PYPROJECT.format(version="2"), "version = 1\npackage = {}\n"),
        (_PYPROJECT.format(version="2"), "version = 1\npackage = [1]\n"),
        (
            _PYPROJECT.format(version="2"),
            "version = 1\n\n[[package]]\nname = 'example'\nversion = 2\n",
        ),
    ],
)
def test_a_release_exception_rejects_malformed_or_wrongly_shaped_metadata(
    *, tmp_path: Path, pyproject: str, lockfile: str
) -> None:
    """Parse failures and values outside the one permitted version field withhold retries."""
    repo = _repository(root=tmp_path)
    _commit_release(repo=repo, pyproject=pyproject, lockfile=lockfile)

    assert not release.version_only_release_change(
        repo_root=repo, change_paths={Path("pyproject.toml"), Path("uv.lock")}
    )


@pytest.mark.parametrize(
    "status",
    [
        "A\tpyproject.toml\n",
        "D\tpyproject.toml\n",
        "R100\tprevious.toml\tpyproject.toml\n",
        "M\tpyproject.toml\nM\tpyproject.toml\n",
    ],
)
def test_non_modification_or_ambiguous_git_status_is_not_a_release_change(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: str
) -> None:
    """Adds, deletes, renames, and unreadable status output fail closed."""

    def status_text(**_: object) -> str:
        return status

    monkeypatch.setattr(release, "_git_text", status_text)
    monkeypatch.setattr(release, "comparison_revision", _base_revision)

    assert not release.version_only_release_change(
        repo_root=tmp_path, change_paths={Path("pyproject.toml")}
    )


def test_an_unavailable_git_status_is_not_a_release_change(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An invocation that does not produce status text withholds the exception."""

    def no_text(**_: object) -> None:
        return None

    monkeypatch.setattr(release, "_git_text", no_text)
    monkeypatch.setattr(release, "comparison_revision", _base_revision)

    assert not release.version_only_release_change(
        repo_root=tmp_path, change_paths={Path("pyproject.toml")}
    )


def test_a_git_invocation_failure_withholds_the_release_exception(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A git process that cannot start is not mistaken for an empty change set."""

    def unavailable(**_: object) -> object:
        return release.Failure(GateCommandNotRun(argv=("git",), detail="not available"))

    monkeypatch.setattr(release, "default_gate_command_runner", unavailable)
    monkeypatch.setattr(release, "comparison_revision", _base_revision)

    assert not release.version_only_release_change(
        repo_root=tmp_path, change_paths={Path("pyproject.toml")}
    )


def test_unreadable_or_uncomparable_release_metadata_withholds_retries(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The release exception requires both on-disk text and a Git baseline."""
    repo = _repository(root=tmp_path)
    _commit_release(
        repo=repo,
        pyproject=_PYPROJECT.format(version="2"),
        lockfile=_UV_LOCK.format(version="2"),
    )
    original_read_text = Path.read_text

    def unreadable(self: Path, *, encoding: str | None = None, errors: str | None = None) -> str:
        if self == repo / "pyproject.toml":
            raise OSError("unreadable")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", unreadable)
    assert unreadable(repo / "uv.lock", encoding="utf-8") == _UV_LOCK.format(version="2")
    assert not release.version_only_release_change(
        repo_root=repo, change_paths={Path("pyproject.toml"), Path("uv.lock")}
    )

    monkeypatch.undo()
    monkeypatch.setattr(release, "comparison_revision", _base_revision)

    def missing_before(*, args: list[str], **_: object) -> str | None:
        return "M\tpyproject.toml\n" if args[0] == "diff" else None

    monkeypatch.setattr(release, "_git_text", missing_before)
    assert not release.version_only_release_change(
        repo_root=repo, change_paths={Path("pyproject.toml")}
    )


@pytest.mark.parametrize(
    "lockfile",
    [
        (
            "version = 1\n\n[[package]]\nname = 'example'\nversion = '2'\n"
            "\n[[package]]\nname = 'example'\nversion = '2'\n"
        ),
        "version = 1\n\n[[package]]\nname = 'other'\nversion = '2'\n",
    ],
)
def test_lockfile_requires_exactly_one_own_package_entry_per_revision(
    *, tmp_path: Path, lockfile: str
) -> None:
    """The lockfile exception cannot hide an added or renamed package entry."""
    repo = _repository(root=tmp_path)
    _commit_release(repo=repo, pyproject=_PYPROJECT.format(version="2"), lockfile=lockfile)

    assert not release.version_only_release_change(
        repo_root=repo, change_paths={Path("pyproject.toml"), Path("uv.lock")}
    )
