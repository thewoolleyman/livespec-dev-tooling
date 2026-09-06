"""check-coverage reuses a repo-root `.coverage` only under a provenance marker.

Work-item livespec-dev-tooling-sc0z. The consume-once reuse from
livespec-dev-tooling-yilyxr.1 read ANY existing repo-root `.coverage` as
check-per-file-coverage's clean full-suite run. A focused `pytest <one
test> --cov` leaves the same file behind, measuring only what that one
test imported, and reporting it as the suite's verdict produced the 49%
total that refused a Green amend (and, when the narrow set happens to be
fully covered, a vacuous 100% pass). These tests drive the real shell
scripts against a fake `uv` on PATH, so they pin the scripts' control
flow — which file is read, which command runs — without a Python child.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = ("check-coverage.sh", "check-per-file-coverage.sh", "coverage-reuse-id.sh")
_REUSE_STAMP = ".livespec-coverage-reuse-token"
# Inputs the scripts read that a host may already export: a GitHub runner
# sets GITHUB_ACTIONS into every process, which would flip the consumer's
# venue branch for every test below. Stripped so each test owns them.
_HOST_INPUTS = frozenset({"GITHUB_ACTIONS", "COVERAGE_PROCESS_START"})
_PYTEST_LINE = (
    "run pytest -n 1 --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing"
)
_PER_FILE_LINE = "run python -m livespec_dev_tooling.checks.per_file_coverage"
_REPORT_LINE = "run coverage report --fail-under=100"
_FAKE_UV = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$UV_LOG"
case "$1 $2" in
    "run coverage")
        printf 'TOTAL %s 0 100%%\\n' "$(cat .coverage)"
        exit "${FAKE_REPORT_STATUS:-0}"
        ;;
    "run pytest")
        printf '%s\\n' "${FAKE_PYTEST_TOTAL:-1000}" > .coverage
        printf 'TOTAL %s 0 100%%\\n' "${FAKE_PYTEST_TOTAL:-1000}"
        exit "${FAKE_PYTEST_STATUS:-0}"
        ;;
    "run python")
        exit 0
        ;;
esac
exit 99
"""


def _is_host_input(*, key: str) -> bool:
    return key.startswith("COV_CORE_") or key in _HOST_INPUTS


def _env(*, tmp_path: Path, extra: dict[str, str]) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not _is_host_input(key=key)}
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
            "UV_LOG": str(tmp_path / "uv.log"),
            "test_nprocs": "1",
        }
    )
    env.update(extra)
    return env


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=_env(tmp_path=cwd, extra={}),
        text=True,
    )


def _install_harness(*, tmp_path: Path, git_tree: bool) -> None:
    scripts = tmp_path / "scripts" / "just"
    scripts.mkdir(parents=True)
    for name in _SCRIPTS:
        _ = shutil.copy2(_REPO_ROOT / "scripts" / "just" / name, scripts / name)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _ = (bin_dir / "uv").write_text(_FAKE_UV, encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    _ = (tmp_path / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    if git_tree:
        _git(cwd=tmp_path, args=["init", "-q", "-b", "master"])
        _git(cwd=tmp_path, args=["add", "tracked.py"])
        _git(cwd=tmp_path, args=["commit", "-q", "-m", "base"])


def _run(*, tmp_path: Path, script: str, extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", f"scripts/just/{script}"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        env=_env(tmp_path=tmp_path, extra=extra),
        text=True,
    )


def _uv_log(*, tmp_path: Path) -> list[str]:
    return (tmp_path / "uv.log").read_text(encoding="utf-8").splitlines()


def _reported_total(*, output: str) -> str:
    match = re.search(r"^TOTAL\s+(\d+)\s", output, flags=re.MULTILINE)
    assert match is not None, output
    return match.group(1)


def test_stale_narrow_coverage_file_is_discarded_and_the_clean_suite_runs(
    *, tmp_path: Path
) -> None:
    """The sc0z shape: a focused-run leftover must not be reported as the suite's verdict."""
    _install_harness(tmp_path=tmp_path, git_tree=True)
    _ = (tmp_path / ".coverage").write_text("49\n", encoding="utf-8")

    result = _run(
        tmp_path=tmp_path, script="check-coverage.sh", extra={"FAKE_PYTEST_TOTAL": "2222"}
    )

    assert result.returncode == 0, result.stderr
    assert "ignoring existing .coverage without a matching provenance marker" in result.stdout
    assert _reported_total(output=result.stdout) == "2222"
    assert _uv_log(tmp_path=tmp_path) == [_PYTEST_LINE]


def test_stale_green_coverage_file_cannot_vacuously_pass(*, tmp_path: Path) -> None:
    _install_harness(tmp_path=tmp_path, git_tree=True)
    _ = (tmp_path / ".coverage").write_text("9999\n", encoding="utf-8")

    result = _run(tmp_path=tmp_path, script="check-coverage.sh", extra={"FAKE_PYTEST_STATUS": "2"})

    assert result.returncode == 2
    assert _uv_log(tmp_path=tmp_path) == [_PYTEST_LINE]


def test_producer_marker_unlocks_consume_once_reuse(*, tmp_path: Path) -> None:
    _install_harness(tmp_path=tmp_path, git_tree=True)

    producer = _run(
        tmp_path=tmp_path,
        script="check-per-file-coverage.sh",
        extra={"FAKE_PYTEST_TOTAL": "8675309"},
    )
    assert producer.returncode == 0, producer.stderr
    assert (tmp_path / _REUSE_STAMP).read_text(encoding="utf-8").startswith("git-tree:")

    consumer = _run(tmp_path=tmp_path, script="check-coverage.sh", extra={})

    assert consumer.returncode == 0, consumer.stderr
    assert "provenance marker matches the current tracked tree" in consumer.stdout
    assert _reported_total(output=consumer.stdout) == "8675309"
    assert _uv_log(tmp_path=tmp_path) == [_PYTEST_LINE, _PER_FILE_LINE, _REPORT_LINE]
    assert not (tmp_path / ".coverage").exists()
    assert not (tmp_path / _REUSE_STAMP).exists()


def test_marker_is_invalidated_by_a_tracked_tree_change(*, tmp_path: Path) -> None:
    _install_harness(tmp_path=tmp_path, git_tree=True)
    producer = _run(
        tmp_path=tmp_path, script="check-per-file-coverage.sh", extra={"FAKE_PYTEST_TOTAL": "1"}
    )
    assert producer.returncode == 0, producer.stderr
    _ = (tmp_path / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")

    consumer = _run(
        tmp_path=tmp_path, script="check-coverage.sh", extra={"FAKE_PYTEST_TOTAL": "3333"}
    )

    assert consumer.returncode == 0, consumer.stderr
    assert _reported_total(output=consumer.stdout) == "3333"
    assert _uv_log(tmp_path=tmp_path)[-1] == _PYTEST_LINE
    assert not (tmp_path / _REUSE_STAMP).exists()


def test_github_actions_consumer_trusts_the_run_scoped_artifact(*, tmp_path: Path) -> None:
    """The consumer job downloads the producer job's artifact; no marker crosses that boundary."""
    _install_harness(tmp_path=tmp_path, git_tree=True)
    _ = (tmp_path / ".coverage").write_text("4242\n", encoding="utf-8")

    result = _run(tmp_path=tmp_path, script="check-coverage.sh", extra={"GITHUB_ACTIONS": "true"})

    assert result.returncode == 0, result.stderr
    assert _reported_total(output=result.stdout) == "4242"
    assert _uv_log(tmp_path=tmp_path) == [_REPORT_LINE]
    assert not (tmp_path / ".coverage").exists()


def test_producer_outside_a_git_tree_leaves_no_marker(*, tmp_path: Path) -> None:
    _install_harness(tmp_path=tmp_path, git_tree=False)

    producer = _run(
        tmp_path=tmp_path, script="check-per-file-coverage.sh", extra={"FAKE_PYTEST_TOTAL": "1"}
    )

    assert producer.returncode == 0, producer.stderr
    assert "leaving no reuse marker" in producer.stdout
    assert not (tmp_path / _REUSE_STAMP).exists()


def test_env_strips_the_host_inputs_the_scripts_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A GitHub runner exports GITHUB_ACTIONS everywhere; the harness must own that input."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("COV_CORE_SOURCE", "leaked")

    env = _env(tmp_path=tmp_path, extra={})

    assert "GITHUB_ACTIONS" not in env
    assert "COV_CORE_SOURCE" not in env
