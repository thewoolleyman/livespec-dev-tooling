"""`scripts/just/check.sh` warms pyright ONCE, serially, before the parallel fan-out.

Work-item livespec-dev-tooling-tqloqv. The aggregate ran `uv sync
--all-groups` and then went straight to `parallel_check_dispatcher`, so
on a COLD pyright cache its two pyright-invoking targets — `check-types`
and `check-no-shadow-ledger-body-typechecks` — could start the
`pyright==<pin>` wrapper's first node/typeshed fetch TOGETHER and leave
it half-written. That surfaces as pyright's "Stub file not found for
'typing'", which is what livespec-dev-tooling-v572ul's hp run
01M5C054VFF7 reported as 24,727 missing-stub errors on a tree whose only
change was a markdown file. The justfile's `warm-typecheck` recipe
(`uv run pyright --version`) exists for exactly that reason, but only
the delegated gate pod ran it.

These tests drive the REAL `scripts/just/check.sh` against a fake `uv`
on PATH — the harness shape `test_check_coverage_reuse_stamp.py`
established — so they pin the script's control flow (which command runs,
in which order, and what stops it) without spawning a Python child.

The fake `uv` MODELS pyright's first-fetch dependency: its `run pyright`
arm populates `PYRIGHT_PYTHON_CACHE_DIR`, and its dispatcher arm fails
the way a cold fan-out fails when that directory is still empty. That
makes the cold-cache assertion deterministic and offline. It is a model,
not pyright itself: the real cold-cache run (an empty
`PYRIGHT_PYTHON_CACHE_DIR`, the aggregate restricted to the two
pyright-invoking targets) is captured as acceptance evidence on the
work-item rather than paid for by every suite run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = "check.sh"
# The two targets that invoke pyright, and the only inventory the
# cold-cache assertion needs: `check.sh` validates its literal argv
# byte-for-entry against `check-targets.txt`, so the harness writes an
# inventory holding exactly these and passes them as the argv.
_TARGETS = ("check-types", "check-no-shadow-ledger-body-typechecks")
_SYNC_LINE = "sync --all-groups"
_WARMUP_LINE = "run pyright --version"
_DISPATCHER_MODULE = "livespec_dev_tooling.parallel_check_dispatcher"
# Inputs `check.sh` reads that a host may already export: the three
# just-variable tokens reroute the aggregate (`skip` / `red_staged` /
# `hook_gate`), and `UV_NO_SYNC` is the script's own export. Stripped so
# each test owns them.
_HOST_INPUTS = frozenset(
    {"skip", "red_staged", "hook_gate", "UV_NO_SYNC", "COVERAGE_PROCESS_START"}
)
# The fake `uv`. Its `run pyright` arm is the pyright-python wrapper's
# first-fetch, modelled: it POPULATES the cache dir. Its dispatcher arm
# is the parallel fan-out, modelled: with that cache still empty it dies
# the way a raced first fetch dies.
_FAKE_UV = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$UV_LOG"
case "$1 $2" in
    "sync --all-groups")
        exit "${FAKE_SYNC_STATUS:-0}"
        ;;
    "run pyright")
        mkdir -p "$PYRIGHT_PYTHON_CACHE_DIR/typeshed-fallback"
        printf 'pyright 1.1.391\\n'
        exit "${FAKE_WARMUP_STATUS:-0}"
        ;;
    "run python")
        if [[ "$*" == *parallel_check_dispatcher* && ! -d "$PYRIGHT_PYTHON_CACHE_DIR/typeshed-fallback" ]]; then
            printf 'error: Stub file not found for "typing"\\n' >&2
            exit 1
        fi
        exit 0
        ;;
esac
exit 99
"""


def _env(*, tmp_path: Path, extra: dict[str, str]) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not _is_host_input(key=key)}
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
            "UV_LOG": str(tmp_path / "uv.log"),
            "PYRIGHT_PYTHON_CACHE_DIR": str(tmp_path / "pyright-cache"),
        }
    )
    env.update(extra)
    return env


def _is_host_input(*, key: str) -> bool:
    return key.startswith("COV_CORE_") or key in _HOST_INPUTS


def _install_harness(*, tmp_path: Path) -> None:
    scripts = tmp_path / "scripts" / "just"
    scripts.mkdir(parents=True)
    _ = shutil.copy2(_REPO_ROOT / "scripts" / "just" / _SCRIPT, scripts / _SCRIPT)
    inventory = "# Canonical check inventory for the harness.\n" + "".join(
        f"{target}\n" for target in _TARGETS
    )
    _ = (tmp_path / "check-targets.txt").write_text(inventory, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _ = (bin_dir / "uv").write_text(_FAKE_UV, encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    # An EMPTY pyright cache dir: present, so the fake's `-d` probe reads
    # the half-written-fetch state rather than a missing-parent state.
    (tmp_path / "pyright-cache").mkdir()


def _run(*, tmp_path: Path, extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", f"scripts/just/{_SCRIPT}", *_TARGETS],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        env=_env(tmp_path=tmp_path, extra=extra),
        text=True,
    )


def _uv_log(*, tmp_path: Path) -> list[str]:
    return (tmp_path / "uv.log").read_text(encoding="utf-8").splitlines()


def _dispatcher_lines(*, lines: list[str]) -> list[str]:
    return [line for line in lines if _DISPATCHER_MODULE in line]


def test_warmup_runs_once_after_sync_and_before_the_dispatcher(*, tmp_path: Path) -> None:
    """Assertion 1: one serial `uv run pyright --version` between sync and fan-out."""
    _install_harness(tmp_path=tmp_path)

    result = _run(tmp_path=tmp_path, extra={})

    assert result.returncode == 0, result.stderr
    lines = _uv_log(tmp_path=tmp_path)
    assert lines.count(_WARMUP_LINE) == 1, lines
    assert lines.index(_SYNC_LINE) < lines.index(_WARMUP_LINE), lines
    dispatched = _dispatcher_lines(lines=lines)
    assert len(dispatched) == 1, lines
    assert lines.index(_WARMUP_LINE) < lines.index(dispatched[0]), lines


def test_failed_warmup_stops_the_aggregate_before_any_target_starts(*, tmp_path: Path) -> None:
    """Assertion 2: a non-zero warm-up aborts with an ERROR line naming it."""
    _install_harness(tmp_path=tmp_path)

    result = _run(tmp_path=tmp_path, extra={"FAKE_WARMUP_STATUS": "2"})

    assert result.returncode == 1, result.stdout
    assert "ERROR" in result.stderr
    assert "pyright warm-up" in result.stderr
    assert "uv run pyright --version" in result.stderr
    assert _dispatcher_lines(lines=_uv_log(tmp_path=tmp_path)) == []


def test_cold_pyright_cache_aggregate_of_both_pyright_targets_exits_zero(*, tmp_path: Path) -> None:
    """Assertion 3: an empty `PYRIGHT_PYTHON_CACHE_DIR` no longer reaches the fan-out cold."""
    _install_harness(tmp_path=tmp_path)
    cache_dir = tmp_path / "pyright-cache"
    assert list(cache_dir.iterdir()) == []

    result = _run(tmp_path=tmp_path, extra={})

    assert result.returncode == 0, result.stderr + result.stdout
    assert (cache_dir / "typeshed-fallback").is_dir()
