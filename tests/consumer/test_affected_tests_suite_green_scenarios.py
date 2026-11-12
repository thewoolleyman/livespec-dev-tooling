"""Consumer-tier coverage for affected-tests suite-green replay scope."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AFFECTED_HEADING = (
    "## Scenario: an in-turn sandbox commit whose affected-tests gate passed on the same tree "
    "runs only those tests"
)
_FALLBACK_HEADING = (
    "## Scenario: an affected-tests record outside a sandbox, or for a failed, empty or "
    "different run, leaves the full suite in place"
)


def _run(*, repo: Path, argv: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a Git or shipped-module command in the fixture consumer."""
    environment = {**os.environ, "PYTHONPATH": str(_REPO_ROOT)}
    return subprocess.run(
        argv,
        cwd=str(repo),
        env=environment,
        capture_output=True,
        text=True,
        check=check,
    )


def _git(*args: str, repo: Path) -> str:
    """Run Git and return its stdout for the fixture repository."""
    return _run(repo=repo, argv=["git", *args]).stdout.strip()


def _consumer(*, tmp_path: Path, sandbox: bool) -> tuple[Path, Path]:
    """Create a staged behaviour-preserving consumer commit and its message path."""
    repo = tmp_path / "consumer"
    repo.mkdir()
    _ = (repo / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["livespec"]\n',
        encoding="utf-8",
    )
    tests = repo / "tests"
    tests.mkdir()
    _ = (repo / "livespec").mkdir()
    _ = (repo / "livespec" / "widget.py").write_text("VALUE = 1\n", encoding="utf-8")
    _ = (tests / "test_alpha.py").write_text(
        "def test_alpha() -> None:\n    assert True\n", encoding="utf-8"
    )
    _ = (tests / "test_beta.py").write_text(
        "def test_beta() -> None:\n    assert True\n", encoding="utf-8"
    )
    sentinel = repo / "full-suite-ran"
    unselected_body = f"""from pathlib import Path


def test_unselected() -> None:
    Path({str(sentinel)!r}).write_text("ran\\n", encoding="utf-8")
"""
    _ = (tests / "test_unselected.py").write_text(
        unselected_body,
        encoding="utf-8",
    )
    _ = _git("init", "-q", repo=repo)
    _ = _git("config", "user.email", "test@example.test", repo=repo)
    _ = _git("config", "user.name", "Test User", repo=repo)
    _ = _git("add", ".", repo=repo)
    _ = _git("commit", "-q", "-m", "chore: baseline", repo=repo)
    if sandbox:
        _ = _git("config", "livespec.sandboxExempt", "true", repo=repo)
    _ = (repo / "livespec" / "widget.py").write_text("VALUE = 2\n", encoding="utf-8")
    _ = _git("add", "livespec/widget.py", repo=repo)
    message = repo / "COMMIT_EDITMSG"
    _ = message.write_text("chore: behaviour-preserving change\n", encoding="utf-8")
    return repo, message


def _record_gate(
    *, repo: Path, paths: tuple[str, ...], command: list[str]
) -> subprocess.CompletedProcess[str]:
    """Run the shipped affected-tests recording entry point for this index tree."""
    selected = repo / "selected-tests.txt"
    _ = selected.write_text("".join(f"{path}\n" for path in paths), encoding="utf-8")
    return _run(
        repo=repo,
        argv=[
            sys.executable,
            "-m",
            "livespec_dev_tooling.affected_tests_record",
            "--paths-file",
            str(selected),
            "--",
            *command,
        ],
        check=False,
    )


def _suite_green(*, repo: Path, message: Path) -> subprocess.CompletedProcess[str]:
    """Run the shipped commit-message check exactly as a consumer hook does."""
    return _run(
        repo=repo,
        argv=[sys.executable, "-m", "livespec_dev_tooling.checks.red_green_replay", str(message)],
        check=False,
    )


def test_sandbox_same_tree_passing_record_runs_only_the_selected_tests(*, tmp_path: Path) -> None:
    """A sandbox consumer replays a qualifying record instead of its full suite."""
    repo, message = _consumer(tmp_path=tmp_path, sandbox=True)
    recorded = _record_gate(
        repo=repo,
        paths=("tests/test_alpha.py", "tests/test_beta.py"),
        command=[sys.executable, "-m", "pytest", "-q", "tests/test_alpha.py", "tests/test_beta.py"],
    )

    assert recorded.returncode == 0, recorded.stderr
    replay = _suite_green(repo=repo, message=message)

    assert replay.returncode == 0, replay.stderr
    assert not (repo / "full-suite-ran").exists()
    trailers = message.read_text(encoding="utf-8")
    assert "TDD-Suite-Green-Scope: affected-tests" in trailers
    assert "TDD-Suite-Green-Producer: affected-tests:" in trailers
    assert "TDD-Suite-Green-Scope: full-suite" not in trailers


@pytest.mark.parametrize("case", ["host", "failed", "empty", "different-tree"])
def test_unqualified_records_leave_the_full_suite_in_place(*, tmp_path: Path, case: str) -> None:
    """A host, failed, empty, or stale record cannot scope a consumer replay."""
    repo, message = _consumer(tmp_path=tmp_path, sandbox=case != "host")
    command = (
        [sys.executable, "-c", "raise SystemExit(7)"]
        if case == "failed"
        else [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_alpha.py",
        ]
    )
    recorded = _record_gate(
        repo=repo,
        paths=() if case == "empty" else ("tests/test_alpha.py",),
        command=command,
    )
    if case == "failed":
        assert recorded.returncode == 7
    else:
        assert recorded.returncode == 0, recorded.stderr
    if case == "different-tree":
        _ = (repo / "livespec" / "widget.py").write_text("VALUE = 3\n", encoding="utf-8")
        _ = _git("add", "livespec/widget.py", repo=repo)

    replay = _suite_green(repo=repo, message=message)

    assert replay.returncode == 0, replay.stderr
    assert (repo / "full-suite-ran").read_text(encoding="utf-8") == "ran\n"
    assert "TDD-Suite-Green-Scope: full-suite" in message.read_text(encoding="utf-8")


def test_governing_scenarios_are_registered_to_this_consumer_coverage() -> None:
    """The scenario registry directs both governing headings to these real consumer tests."""
    registry = (Path("tests") / "heading-coverage.json").read_text(encoding="utf-8")

    assert _AFFECTED_HEADING in registry
    assert _FALLBACK_HEADING in registry
    assert '"test": "tests.consumer.test_affected_tests_suite_green_scenarios.' in registry
