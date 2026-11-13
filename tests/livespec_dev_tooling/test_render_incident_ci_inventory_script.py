"""The render script refuses a wrong input by name and never damages a committed entry.

WHY THIS FILE EXISTS (work item livespec-dev-tooling-6xd3dz, the coordinator's grade
of livespec-dev-tooling#4449). `scripts/just/render-incident-ci-inventory.sh`
writes an adopter's released incident CI inventory from that adopter's own clone.
It runs at build time and never inside the incident CI entrance, so its failures
are silent ones: a render that dies half way must leave the committed entry it
was replacing byte-identical, and a clone of the wrong repository, a commit off
the default branch, or a commit without the two inputs must each be refused by
name before anything is written.

HOW IT STAYS OFF THE NETWORK. Every case renders from a local bare repository,
and every case runs with a stub `uv` first on PATH that exits 1, so no case ever
reaches the real renderer. The refusal cases must stop before `uv` is called;
the render-failure case is the stub itself.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "just" / "render-incident-ci-inventory.sh"
_REPOSITORY = "owner/adopter"
_ENTRY = Path("livespec_dev_tooling/data/incident-ci-inventory") / f"{_REPOSITORY}.json"
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        env={**os.environ, **_GIT_ENV},
    )
    return completed.stdout.strip()


def _clone(*, tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    """A clone whose origin is a bare `owner/adopter.git`, with one commit on main."""
    work = tmp_path / "work"
    work.mkdir()
    _ = _git("init", "--quiet", "--initial-branch=main", cwd=work)
    for name, text in files.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")
    _ = _git("add", "--all", cwd=work)
    _ = _git("commit", "--quiet", "-m", "fixture", cwd=work)
    bare = tmp_path / "remotes" / "owner" / "adopter.git"
    bare.parent.mkdir(parents=True)
    _ = _git("clone", "--quiet", "--bare", str(work), str(bare), cwd=tmp_path)
    clone = tmp_path / "clone"
    _ = _git("clone", "--quiet", str(bare), str(clone), cwd=tmp_path)
    return clone, _git("rev-parse", "HEAD", cwd=clone)


_INPUTS = {
    ".github/workflows/ci.yml": "on: push\njobs: {}\n",
    "check-targets.txt": "check-fast  # incident-timing: fast\n",
}


def _render(
    *, tmp_path: Path, repository: str, clone: Path, commit: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    stub = tmp_path / "stub-bin"
    stub.mkdir(exist_ok=True)
    uv = stub / "uv"
    _ = uv.write_text("#!/usr/bin/env bash\necho 'stub uv: render failed' >&2\nexit 1\n")
    uv.chmod(0o755)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    completed = subprocess.run(
        ["bash", str(_SCRIPT), repository, str(clone), commit],
        cwd=out,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={**os.environ, **_GIT_ENV, "PATH": f"{stub}:{os.environ['PATH']}"},
    )
    return completed, out / _ENTRY


def test_a_failed_render_leaves_the_committed_entry_byte_identical(tmp_path: Path):
    clone, commit = _clone(tmp_path=tmp_path, files=_INPUTS)
    entry = tmp_path / "out" / _ENTRY
    entry.parent.mkdir(parents=True)
    _ = entry.write_text('{"previous": "entry"}\n', encoding="utf-8")
    completed, entry = _render(
        tmp_path=tmp_path, repository=_REPOSITORY, clone=clone, commit=commit
    )
    assert completed.returncode != 0, completed.stderr
    assert (
        entry.read_text(encoding="utf-8") == '{"previous": "entry"}\n'
    ), "a render that failed must leave the committed entry it was replacing intact"


def test_a_clone_whose_origin_does_not_name_the_repository_is_refused(tmp_path: Path):
    clone, commit = _clone(tmp_path=tmp_path, files=_INPUTS)
    completed, entry = _render(
        tmp_path=tmp_path, repository="owner/other", clone=clone, commit=commit
    )
    assert completed.returncode == 2, completed.stderr
    assert "does not name owner/other" in completed.stderr
    assert "adopter.git" in completed.stderr
    assert not entry.exists()


def test_a_commit_off_the_default_branch_is_refused(tmp_path: Path):
    clone, _ = _clone(tmp_path=tmp_path, files=_INPUTS)
    _ = _git("checkout", "--quiet", "-b", "side", cwd=clone)
    _ = (clone / "side.txt").write_text("side\n", encoding="utf-8")
    _ = _git("add", "side.txt", cwd=clone)
    _ = _git("commit", "--quiet", "-m", "side", cwd=clone)
    side = _git("rev-parse", "HEAD", cwd=clone)
    completed, entry = _render(tmp_path=tmp_path, repository=_REPOSITORY, clone=clone, commit=side)
    assert completed.returncode == 2, completed.stderr
    assert f"{side} is not on {_REPOSITORY}'s default branch" in completed.stderr
    assert not entry.exists()


@pytest.mark.parametrize("missing", sorted(_INPUTS))
def test_a_commit_without_a_required_input_is_refused_by_name(tmp_path: Path, missing: str):
    files = {name: text for name, text in _INPUTS.items() if name != missing}
    clone, commit = _clone(tmp_path=tmp_path, files=files)
    completed, entry = _render(
        tmp_path=tmp_path, repository=_REPOSITORY, clone=clone, commit=commit
    )
    assert completed.returncode == 2, completed.stderr
    assert f"{_REPOSITORY}@{commit} has no {missing}" in completed.stderr
    assert not entry.exists()
