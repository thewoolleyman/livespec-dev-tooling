"""Sharded per-file coverage: the assignment, and the combine half of the producer.

Work-item livespec-dev-tooling-mxjbmi. `scripts/just/coverage-shard.sh` deals the
tracked test files to N shards by measured duration; `check-per-file-coverage.sh`
combines every shard's coverage data (`LIVESPEC_COVERAGE_SHARDS_DIR`) and runs the
unchanged per-file verifier over it. The shards must partition the suite exactly,
and the combined verdict must be the unsharded one: judged over the union of the
shards' data, never over one shard's.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts" / "just"
_SHARD = _SCRIPTS / "coverage-shard.sh"
_PRODUCER = "check-per-file-coverage.sh"
_RECEIPT_ID = "coverage-reuse-id.sh"
_TABLE = _SCRIPTS / "coverage-shard-durations.tsv"
_SHARD_COUNT = 4
_BALANCE_BOUND = 1.25
_PYTEST_RAN = "pytest-ran"

# A fake `uv`: the suite run must never start in combine mode, `coverage combine`
# and the per-file check reach the real interpreter's modules.
_FAKE_UV = """#!/usr/bin/env bash
set -euo pipefail
shift
if [[ "$1" == "pytest" ]]; then
    : > "$PYTEST_RAN_MARKER"
    exit 99
fi
if [[ "$1" == "coverage" ]]; then
    shift
    exec "$REAL_PYTHON" -m coverage "$@"
fi
shift
exec "$REAL_PYTHON" "$@"
"""
_KEPT = """def pick(flag):
    if flag:
        return 1
    return 2
"""
_PYPROJECT = """[tool.coverage.run]
branch = true
data_file = "${LIVESPEC_COVERAGE_DATA_FILE-.coverage}"
"""


def _env(*, tmp_path: Path) -> dict[str, str]:
    inherited = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_", "LIVESPEC_COVERAGE_", "GITHUB_"))
    }
    return {
        **inherited,
        "HOME": str(tmp_path),
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "PYTHONPATH": str(_REPO_ROOT),
        "REAL_PYTHON": sys.executable,
        "PYTEST_RAN_MARKER": str(tmp_path / _PYTEST_RAN),
        "test_nprocs": "1",
    }


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _tracked_tests(*, root: Path, names: list[str]) -> None:
    (root / "tests").mkdir()
    for name in names:
        _ = (root / "tests" / name).write_text("", encoding="utf-8")
    _git(cwd=root, args=["init", "-q", "-b", "master"])
    _git(cwd=root, args=["add", "tests"])
    _git(cwd=root, args=["commit", "-q", "-m", "base"])


def _plan(
    *, cwd: Path, index: str, count: str, table: Path | None
) -> subprocess.CompletedProcess[str]:
    env = {
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("COV_CORE_", "COVERAGE_", "LIVESPEC_COVERAGE_"))
        },
        "LIVESPEC_COVERAGE_SHARD_LIST_ONLY": "1",
    }
    if table is not None:
        env["LIVESPEC_COVERAGE_SHARD_DURATIONS"] = str(table)
    return subprocess.run(
        ["bash", str(_SHARD), index, count],
        cwd=cwd,
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def _shard_files(*, cwd: Path, index: int, count: int, table: Path | None) -> list[str]:
    result = _plan(cwd=cwd, index=str(index), count=str(count), table=table)
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_the_shards_partition_the_tracked_test_files_exactly(*, tmp_path: Path) -> None:
    names = [f"test_{letter}.py" for letter in "abcdefg"]
    _tracked_tests(root=tmp_path, names=[*names, "helper.py"])

    shards = [_shard_files(cwd=tmp_path, index=i, count=3, table=None) for i in (1, 2, 3)]
    dealt = [path for shard in shards for path in shard]

    assert sorted(dealt) == sorted(f"tests/{name}" for name in names)
    assert len(dealt) == len(set(dealt))


def test_the_longest_files_go_to_the_least_loaded_shard(*, tmp_path: Path) -> None:
    _tracked_tests(root=tmp_path, names=[f"test_{letter}.py" for letter in "abcde"])
    table = tmp_path / "durations.tsv"
    rows = {"a": 10, "b": 9, "c": 2, "d": 2, "e": 1}
    table.write_text(
        "".join(f"tests/test_{key}.py\t{value}\n" for key, value in rows.items())
        + "tests/test_ghost.py\t500\n",
        encoding="utf-8",
    )

    first = _shard_files(cwd=tmp_path, index=1, count=2, table=table)
    second = _shard_files(cwd=tmp_path, index=2, count=2, table=table)

    assert first == ["tests/test_a.py", "tests/test_d.py"]
    assert second == ["tests/test_b.py", "tests/test_c.py", "tests/test_e.py"]
    assert _shard_files(cwd=tmp_path, index=1, count=2, table=table) == first


@pytest.mark.parametrize(
    ("index", "count"),
    [("0", "3"), ("4", "3"), ("x", "3"), ("1", "0")],
)
def test_a_malformed_shard_argument_is_refused(*, tmp_path: Path, index: str, count: str) -> None:
    _tracked_tests(root=tmp_path, names=["test_a.py"])

    result = _plan(cwd=tmp_path, index=index, count=count, table=None)

    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_a_repository_with_no_tracked_test_files_is_refused(*, tmp_path: Path) -> None:
    _git(cwd=tmp_path, args=["init", "-q", "-b", "master"])

    result = _plan(cwd=tmp_path, index="1", count="2", table=None)

    assert result.returncode == 1
    assert "no tracked test files" in result.stderr


def test_the_committed_table_balances_this_repositorys_shards() -> None:
    seconds = {
        line.split("\t")[0]: float(line.split("\t")[1])
        for line in _TABLE.read_text(encoding="utf-8").splitlines()
    }
    mean = sum(seconds.values()) / len(seconds)
    shards = [
        _shard_files(cwd=_REPO_ROOT, index=i, count=_SHARD_COUNT, table=None)
        for i in range(1, _SHARD_COUNT + 1)
    ]
    loads = [sum(seconds.get(path, mean) for path in shard) for shard in shards]
    tracked = subprocess.run(
        ["git", "ls-files", "tests/**"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    suite = {path for path in tracked if Path(path).name.startswith("test_")}
    dealt = [path for shard in shards for path in shard]

    assert set(dealt) >= suite
    assert len(dealt) == len(set(dealt))
    assert max(loads) / min(loads) <= _BALANCE_BOUND, loads


def _install_producer(*, root: Path) -> None:
    scripts = root / "scripts" / "just"
    scripts.mkdir(parents=True)
    for name in (_PRODUCER, _RECEIPT_ID):
        _ = shutil.copy2(_SCRIPTS / name, scripts / name)
    (root / "bin").mkdir()
    _ = (root / "bin" / "uv").write_text(_FAKE_UV, encoding="utf-8")
    (root / "bin" / "uv").chmod(0o755)
    _ = (root / "kept.py").write_text(_KEPT, encoding="utf-8")
    _ = (root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    for flag in (True, False):
        _ = (root / f"drive_{flag}.py").write_text(
            f"import kept\n\nkept.pick({flag})\n", encoding="utf-8"
        )
    _git(cwd=root, args=["init", "-q", "-b", "master"])
    _git(cwd=root, args=["add", "scripts", "kept.py", "pyproject.toml"])
    _git(cwd=root, args=["commit", "-q", "-m", "base"])


def _record_shard(*, root: Path, number: int, flag: bool) -> None:
    (root / ".coverage-shards").mkdir(exist_ok=True)
    _ = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--data-file=.coverage-shards/.coverage.shard-{number}",
            f"drive_{flag}.py",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _produce(*, root: Path) -> subprocess.CompletedProcess[str]:
    env = {**_env(tmp_path=root), "LIVESPEC_COVERAGE_SHARDS_DIR": ".coverage-shards"}
    return subprocess.run(
        ["bash", f"scripts/just/{_PRODUCER}"],
        cwd=root,
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def test_the_producer_judges_the_union_of_the_shards_without_running_the_suite(
    *, tmp_path: Path
) -> None:
    _install_producer(root=tmp_path)
    _record_shard(root=tmp_path, number=1, flag=True)
    _record_shard(root=tmp_path, number=2, flag=False)

    result = _produce(root=tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "combining 2 coverage shards" in result.stdout
    assert (tmp_path / ".coverage").is_file()
    assert (tmp_path / ".livespec-coverage-reuse-token").is_file()
    assert not (tmp_path / _PYTEST_RAN).exists()


def test_one_shard_alone_does_not_pass_the_per_file_verdict(*, tmp_path: Path) -> None:
    _install_producer(root=tmp_path)
    _record_shard(root=tmp_path, number=1, flag=True)

    result = _produce(root=tmp_path)

    assert result.returncode != 0
    assert not (tmp_path / _PYTEST_RAN).exists()


def test_a_shards_directory_with_no_shard_data_fails_with_a_receipt(*, tmp_path: Path) -> None:
    _install_producer(root=tmp_path)
    (tmp_path / ".coverage-shards").mkdir()

    result = _produce(root=tmp_path)

    assert result.returncode == 1
    assert "holds no shard data" in result.stderr
    assert (tmp_path / ".livespec-coverage-failure-receipt").is_file()
    assert not (tmp_path / _PYTEST_RAN).exists()
