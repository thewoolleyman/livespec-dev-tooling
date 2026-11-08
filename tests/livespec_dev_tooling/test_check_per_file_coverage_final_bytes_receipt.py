"""The producer's receipt vouches for the FINAL rewritten `.coverage` bytes.

Work-item livespec-dev-tooling-cj5dg5 (post-mortem livespec-dev-tooling-npysxq,
candidate F). The stamp-before-rewrite defect (livespec-dev-tooling-x3lvve)
passed a green PR proof because its only test faked the per-file check. Here the
REAL per-file report runs over real coverage data that measured a source file
deleted before report time, so the vanished-source rewrite really rewrites the
data file. The receipt must equal `scripts/just/coverage-reuse-id.sh` over the
bytes left behind. A copy of the producer with the stamp moved before the
per-file check must fail the same comparison.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRODUCER = "check-per-file-coverage.sh"
_RECEIPT_ID = "coverage-reuse-id.sh"
_STAMP = ".livespec-coverage-reuse-token"
_PER_FILE_BLOCK_START = "per_file_status=0\n"
_STAMP_BLOCK_START = 'if reuse_id="$(scripts/just/coverage-reuse-id.sh)"; then\n'
_STAMP_BLOCK_END = "fi\n"
# The suite stand-in runs real coverage over a driver that executes a kept
# source and a transient one, then deletes the transient tree, the way uv's
# interpreter probe vanishes on a cold-cache CI pod. Every other `uv run`
# (`uv run python ...`) reaches the real interpreter, so the per-file check is
# the shipped module.
_FAKE_UV = """#!/usr/bin/env bash
set -euo pipefail
shift
if [[ "$1" == "pytest" ]]; then
    "$REAL_PYTHON" -m coverage run --branch --data-file="$LIVESPEC_COVERAGE_DATA_FILE" driver.py
    sha256sum "$LIVESPEC_COVERAGE_DATA_FILE" | awk '{ print $1 }' > "$PRE_REWRITE_DIGEST"
    rm -rf transient
    exit 0
fi
shift
exec "$REAL_PYTHON" "$@"
"""
_DRIVER = """import runpy

runpy.run_path("kept.py")
runpy.run_path("transient/gone.py")
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
        "PRE_REWRITE_DIGEST": str(tmp_path / "pre-rewrite.sha256"),
        "test_nprocs": "1",
    }


def _git(*, tmp_path: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=_env(tmp_path=tmp_path),
    )


def _install(*, tmp_path: Path, producer_text: str) -> None:
    scripts = tmp_path / "scripts" / "just"
    scripts.mkdir(parents=True)
    _ = (scripts / _PRODUCER).write_text(producer_text, encoding="utf-8")
    _ = shutil.copy2(_REPO_ROOT / "scripts" / "just" / _RECEIPT_ID, scripts / _RECEIPT_ID)
    (tmp_path / "bin").mkdir()
    _ = (tmp_path / "bin" / "uv").write_text(_FAKE_UV, encoding="utf-8")
    (tmp_path / "bin" / "uv").chmod(0o755)
    _ = (tmp_path / "kept.py").write_text("VALUE = 1\n", encoding="utf-8")
    _ = (tmp_path / "driver.py").write_text(_DRIVER, encoding="utf-8")
    (tmp_path / "transient").mkdir()
    _ = (tmp_path / "transient" / "gone.py").write_text("GONE = 1\n", encoding="utf-8")
    _git(tmp_path=tmp_path, args=["init", "-q", "-b", "master"])
    _git(tmp_path=tmp_path, args=["add", "scripts", "kept.py", "driver.py"])
    _git(tmp_path=tmp_path, args=["commit", "-q", "-m", "base"])


def _receipt_facts(*, tmp_path: Path, producer_text: str) -> dict[str, bool]:
    """Run a producer copy over the vanished-source fixture and judge its receipt."""
    _install(tmp_path=tmp_path, producer_text=producer_text)
    env = _env(tmp_path=tmp_path)
    producer = subprocess.run(
        ["bash", f"scripts/just/{_PRODUCER}"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    final_id = subprocess.run(
        ["bash", f"scripts/just/{_RECEIPT_ID}"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=env,
        text=True,
    ).stdout
    final_digest = hashlib.sha256((tmp_path / ".coverage").read_bytes()).hexdigest()
    pre_rewrite = (tmp_path / "pre-rewrite.sha256").read_text(encoding="utf-8").strip()
    return {
        "producer exits zero": producer.returncode == 0,
        "the rewrite changed the data bytes": final_digest != pre_rewrite,
        "the receipt equals the id of the final bytes": (
            (tmp_path / _STAMP).read_text(encoding="utf-8") == final_id
        ),
    }


def _stamp_moved_before_the_per_file_check(*, producer_text: str) -> str:
    stamp_at = producer_text.index(_STAMP_BLOCK_START)
    stamp_end = producer_text.index(_STAMP_BLOCK_END, stamp_at) + len(_STAMP_BLOCK_END)
    stamp_block = producer_text[stamp_at:stamp_end]
    without = producer_text[:stamp_at] + producer_text[stamp_end:]
    per_file_at = without.index(_PER_FILE_BLOCK_START)
    return without[:per_file_at] + stamp_block + without[per_file_at:]


def test_the_receipt_vouches_for_the_bytes_the_vanished_source_rewrite_left(
    *, tmp_path: Path
) -> None:
    producer_text = (_REPO_ROOT / "scripts" / "just" / _PRODUCER).read_text(encoding="utf-8")

    facts = _receipt_facts(tmp_path=tmp_path, producer_text=producer_text)

    assert all(facts.values()), facts


def test_a_producer_that_stamps_before_the_per_file_check_fails_the_comparison(
    *, tmp_path: Path
) -> None:
    producer_text = (_REPO_ROOT / "scripts" / "just" / _PRODUCER).read_text(encoding="utf-8")
    moved = _stamp_moved_before_the_per_file_check(producer_text=producer_text)

    facts = _receipt_facts(tmp_path=tmp_path, producer_text=moved)

    assert moved != producer_text
    assert facts == {
        "producer exits zero": True,
        "the rewrite changed the data bytes": True,
        "the receipt equals the id of the final bytes": False,
    }, facts
