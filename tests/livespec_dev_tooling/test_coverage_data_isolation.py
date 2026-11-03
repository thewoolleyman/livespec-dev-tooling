"""Coverage data files are per aggregate, and an unreadable one fails loudly.

Work-item livespec-dev-tooling-3wz453. check-per-file-coverage died now
and then with `no such table: tracer` / `file is not a database` while
every test passed, leaving a 0-byte `.coverage` in the worktree. The
producer and the consumer of the full-tree coverage pair both ran with
COVERAGE_FILE unset, so every aggregate in a worktree — and any focused
`pytest --cov` run beside it — wrote, combined and read the SAME
repo-root `.coverage`. These tests pin the three halves of the fix:

- the coverage scripts keep each aggregate's data in its own namespace,
  while the tests themselves still run with COVERAGE_FILE unset (the
  clean-env measurement of work-item livespec-dev-tooling-yilyxr.1);
- the dispatcher tells the per-file reader which targets wrote coverage;
- the per-file reader refuses a 0-byte, non-SQLite or table-less data
  file with a diagnostic naming the file and those writers, instead of
  an sqlite traceback, and reports nothing from it.

The script tests drive the real shell scripts against a fake `uv` on
PATH. The fake's `pytest` writes where coverage.py would (COVERAGE_FILE,
else the `data_file` that pyproject.toml expands from
LIVESPEC_COVERAGE_DATA_FILE, else `.coverage`), then meets the other
aggregate at a rendezvous before re-reading its data, so two producers
that share a data file collide on every run rather than by timing.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from coverage import CoverageData

import livespec_dev_tooling.parallel_check_dispatcher as dispatcher
from livespec_dev_tooling.checks import per_file_coverage

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = ("check-coverage.sh", "check-per-file-coverage.sh", "coverage-reuse-id.sh")
_WRITERS = "check-check-coverage-incremental, check-coverage, check-per-file-coverage"
_COVERAGE_TABLES = ("arc", "context", "coverage_schema", "file", "line_bits", "meta", "tracer")
_FAKE_UV = """#!/usr/bin/env bash
set -euo pipefail
data="${COVERAGE_FILE:-${LIVESPEC_COVERAGE_DATA_FILE:-.coverage}}"
case "$1 $2" in
    "run pytest")
        printf 'pytest COVERAGE_FILE=%s\\n' "${COVERAGE_FILE-<unset>}" >> "$UV_LOG"
        mkdir -p "$(dirname "$data")"
        printf '%s\\n' "$PAYLOAD" > "$data"
        touch "$RENDEZVOUS/$PAYLOAD"
        for _ in $(seq 600); do
            arrived=("$RENDEZVOUS"/*)
            [[ "${#arrived[@]}" -ge 2 ]] && break
            sleep 0.05
        done
        [[ "$(cat "$data")" == "$PAYLOAD" ]] || exit 3
        printf 'TOTAL %s 0 100%%\\n' "$PAYLOAD"
        ;;
    "run python")
        printf 'per-file read %s\\n' "$(cat "${COVERAGE_FILE:-.coverage}")"
        ;;
    "run coverage")
        printf 'TOTAL %s 0 100%%\\n' "$(cat "$data")"
        ;;
    *)
        exit 99
        ;;
esac
"""


def _is_host_input(*, key: str) -> bool:
    return key.startswith(("COV_CORE_", "COVERAGE_", "LIVESPEC_COVERAGE_")) or key in {
        "GITHUB_ACTIONS",
    }


def _env(*, tmp_path: Path, extra: dict[str, str]) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not _is_host_input(key=key)}
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
            "RENDEZVOUS": str(tmp_path / "rendezvous"),
            "test_nprocs": "1",
        }
    )
    env.update(extra)
    return env


def _install_worktree(*, tmp_path: Path) -> None:
    scripts = tmp_path / "scripts" / "just"
    scripts.mkdir(parents=True)
    for name in _SCRIPTS:
        _ = shutil.copy2(_REPO_ROOT / "scripts" / "just" / name, scripts / name)
    (tmp_path / "bin").mkdir()
    _ = (tmp_path / "bin" / "uv").write_text(_FAKE_UV, encoding="utf-8")
    (tmp_path / "bin" / "uv").chmod(0o755)
    (tmp_path / "rendezvous").mkdir()
    _ = (tmp_path / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    for args in (["init", "-q", "-b", "master"], ["add", "tracked.py"], ["commit", "-qm", "b"]):
        _ = subprocess.run(
            [*git, *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            env=_env(tmp_path=tmp_path, extra={}),
        )


def _start(*, tmp_path: Path, script: str, extra: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["bash", f"scripts/just/{script}"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=_env(tmp_path=tmp_path, extra=extra),
        text=True,
    )


def _aggregate_env(*, tmp_path: Path, name: str, payload: str) -> dict[str, str]:
    """The env one aggregate's dispatcher hands its full-tree coverage pair."""
    return {
        "COVERAGE_FILE": str(tmp_path / f"covns-full-tree-{name}" / ".coverage"),
        "PAYLOAD": payload,
        "UV_LOG": str(tmp_path / f"uv-{name}.log"),
    }


def test_two_aggregates_started_together_each_report_their_own_verdict(*, tmp_path: Path) -> None:
    """Two aggregates in one worktree never read each other's coverage data.

    Both producers start together and each re-reads its data only after
    the other has written; both consumers then reuse the data their own
    producer left. Every verdict must be the run's own, the tests must
    still run with COVERAGE_FILE unset, and the shared repo-root
    `.coverage` must never be written.
    """
    _install_worktree(tmp_path=tmp_path)
    envs = {
        name: _aggregate_env(tmp_path=tmp_path, name=name, payload=payload)
        for name, payload in (("a", "1111"), ("b", "2222"))
    }

    producers = {
        name: _start(tmp_path=tmp_path, script="check-per-file-coverage.sh", extra=env)
        for name, env in envs.items()
    }
    produced = {name: proc.communicate(timeout=120) for name, proc in producers.items()}
    consumers = {
        name: _start(tmp_path=tmp_path, script="check-coverage.sh", extra=env)
        for name, env in envs.items()
    }
    consumed = {name: proc.communicate(timeout=120) for name, proc in consumers.items()}

    for name, env in envs.items():
        producer_out = produced[name][0]
        consumer_out = consumed[name][0]
        assert producers[name].returncode == 0, f"producer {name} failed:\n{producer_out}"
        assert f"per-file read {env['PAYLOAD']}" in producer_out, producer_out
        assert consumers[name].returncode == 0, f"consumer {name} failed:\n{consumer_out}"
        assert "no duplicate suite run" in consumer_out, consumer_out
        assert f"TOTAL {env['PAYLOAD']} " in consumer_out, consumer_out
        uv_log = Path(env["UV_LOG"]).read_text(encoding="utf-8")
        assert uv_log == "pytest COVERAGE_FILE=<unset>\n", uv_log
        assert not Path(env["COVERAGE_FILE"]).exists(), "the consumer must consume its own data"
    assert not (tmp_path / ".coverage").exists(), "no aggregate may write the shared root file"


def test_dispatcher_exports_the_coverage_writer_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every coverage target learns which targets write coverage in its aggregate."""
    probe = tmp_path / "writers"
    recipes = {
        "check-per-file-coverage": f'printf "%s\\n" "$LIVESPEC_COVERAGE_WRITERS" > {probe}',
        "check-coverage": "true",
        "check-check-coverage-incremental": "true",
        "check-lint": "true",
    }
    _ = (tmp_path / "justfile").write_text(
        "".join(f"{name}:\n    {body}\n\n" for name, body in recipes.items()), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["parallel-check-dispatcher", "--", *recipes])

    rc = dispatcher.main()

    output = capsys.readouterr()
    assert rc == 0, output.out + output.err
    assert probe.read_text(encoding="utf-8") == f"{_WRITERS}\n"


def _coverage_db_without(*, path: Path, tables: tuple[str, ...]) -> None:
    data = CoverageData(basename=str(path), suffix=False)
    data.add_arcs({str(_REPO_ROOT / "pyproject.toml"): [(-1, 1), (1, -1)]})
    data.write()
    with sqlite3.connect(path) as db:
        for table in tables:
            _ = db.execute(f"drop table {table}")


@pytest.mark.parametrize(
    ("raw", "tables"),
    [
        pytest.param(b"", (), id="zero-bytes"),
        pytest.param(b"not a coverage database\n", (), id="not-sqlite"),
        pytest.param(b"SQLite format 3\x00" + b"\x00" * 4096, (), id="sqlite-header-only"),
        pytest.param(None, ("tracer",), id="no-tracer-table"),
        pytest.param(None, ("arc",), id="no-arc-table"),
        pytest.param(None, _COVERAGE_TABLES, id="no-tables"),
    ],
)
def test_unreadable_data_file_fails_naming_the_file_and_its_writers(
    *,
    raw: bytes | None,
    tables: tuple[str, ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A corrupt data file fails with a named diagnostic and no per-file verdict."""
    data_file = tmp_path / "covns-full-tree-x" / ".coverage"
    data_file.parent.mkdir()
    if raw is None:
        _coverage_db_without(path=data_file, tables=tables)
    else:
        _ = data_file.write_bytes(raw)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COVERAGE_FILE", str(data_file))
    monkeypatch.setenv("LIVESPEC_COVERAGE_WRITERS", _WRITERS)

    rc = per_file_coverage.main()

    output = capsys.readouterr()
    combined = output.out + output.err
    assert rc == 1, combined
    assert "coverage data unreadable" in combined, combined
    assert str(data_file) in combined, combined
    assert _WRITERS in combined, combined
    assert "Traceback" not in combined, combined
    assert "no such table" not in combined, combined
    assert "below 100%" not in combined, combined
    assert "no measured files" not in combined, combined
