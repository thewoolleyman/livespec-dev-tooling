"""A workflow- or script-only commit runs the tests that read ci.yml at pre-commit.

Work-item livespec-dev-tooling-cj5dg5 (post-mortem livespec-dev-tooling-npysxq,
candidate I). A commit with no staged `.py` takes
`scripts/just/check-pre-commit-doc-only.sh`, which ran no pytest, so jerpfe's
workflow guard collision reached CI (job 127749278476) after a green commit.
These tests run the real subset script in a scratch repository whose `just` and
`uv` are fakes that log their arguments, so they pin which tests the commit
runs and that a failing one refuses it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = "check-pre-commit-doc-only.sh"
_READER = "tests/test_reads_the_workflow.py"
_FAKE_JUST = """#!/usr/bin/env bash
exit 0
"""
_FAKE_UV = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$UV_LOG"
exit "${FAKE_PYTEST_STATUS:-0}"
"""


def _env(*, tmp_path: Path, pytest_status: int) -> dict[str, str]:
    inherited = {key: value for key, value in os.environ.items() if key != "test_nprocs"}
    return {
        **inherited,
        "HOME": str(tmp_path),
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "UV_LOG": str(tmp_path / "uv.log"),
        "FAKE_PYTEST_STATUS": str(pytest_status),
    }


def _git(*, tmp_path: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=_env(tmp_path=tmp_path, pytest_status=0),
    )


def _write(*, tmp_path: Path, path: str, text: str) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")


def _install(*, tmp_path: Path) -> None:
    (tmp_path / "scripts" / "just").mkdir(parents=True)
    _ = shutil.copy2(
        _REPO_ROOT / "scripts" / "just" / _SCRIPT, tmp_path / "scripts" / "just" / _SCRIPT
    )
    for name, body in (("just", _FAKE_JUST), ("uv", _FAKE_UV)):
        _write(tmp_path=tmp_path, path=f"bin/{name}", text=body)
        (tmp_path / "bin" / name).chmod(0o755)
    _write(tmp_path=tmp_path, path=_READER, text='CI = ".github/workflows/ci.yml"\n')
    _write(tmp_path=tmp_path, path="tests/test_unrelated.py", text="VALUE = 1\n")
    _write(tmp_path=tmp_path, path=".github/workflows/ci.yml", text="name: ci\n")
    _write(tmp_path=tmp_path, path="docs/note.md", text="note\n")
    _git(tmp_path=tmp_path, args=["init", "-q", "-b", "master"])
    _git(tmp_path=tmp_path, args=["add", "."])
    _git(tmp_path=tmp_path, args=["commit", "-q", "-m", "base"])


def _commit_gate(*, tmp_path: Path, staged: str, pytest_status: int) -> tuple[int, list[str]]:
    """Stage one edited path and run the subset; return its exit and the pytest calls."""
    _install(tmp_path=tmp_path)
    _ = (tmp_path / staged).open("a", encoding="utf-8").write("# edited\n")
    _git(tmp_path=tmp_path, args=["add", staged])
    result = subprocess.run(
        ["bash", f"scripts/just/{_SCRIPT}"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        env=_env(tmp_path=tmp_path, pytest_status=pytest_status),
        text=True,
    )
    log = tmp_path / "uv.log"
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result.returncode, [call for call in calls if call.startswith("run pytest")]


@pytest.mark.parametrize("staged", [".github/workflows/ci.yml", f"scripts/just/{_SCRIPT}"])
def test_a_workflow_or_script_commit_runs_exactly_the_ci_yml_readers(
    *, tmp_path: Path, staged: str
) -> None:
    status, pytest_calls = _commit_gate(tmp_path=tmp_path, staged=staged, pytest_status=0)

    assert (status, pytest_calls) == (0, [f"run pytest -q -p no:cacheprovider -n 1 {_READER}"])


def test_a_failing_ci_yml_reader_refuses_the_commit(*, tmp_path: Path) -> None:
    status, pytest_calls = _commit_gate(
        tmp_path=tmp_path, staged=".github/workflows/ci.yml", pytest_status=1
    )

    assert (status != 0, len(pytest_calls)) == (True, 1)


def test_a_commit_touching_neither_runs_no_pytest(*, tmp_path: Path) -> None:
    status, pytest_calls = _commit_gate(tmp_path=tmp_path, staged="docs/note.md", pytest_status=1)

    assert (status, pytest_calls) == (0, [])
