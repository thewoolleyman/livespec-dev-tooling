"""Runtime regression coverage for the routed cache-negative shell suite."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "isolation" / "cache-negative-tests.sh"


def _write_stub(*, path: Path, body: str) -> None:
    """Write an executable command substitute used by the isolated suite run."""
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_suite(*, tmp_path: Path, warm_seed: Path) -> subprocess.CompletedProcess[str]:
    """Run the shell suite with its network checks deterministically refused."""
    command_dir = tmp_path / "bin"
    command_dir.mkdir(exist_ok=True)
    _write_stub(path=command_dir / "python3", body="#!/bin/sh\nprintf '%s\\n' '-NOPERM denied'\n")
    _write_stub(path=command_dir / "curl", body="#!/bin/sh\nprintf '403'\n")
    environment = os.environ | {
        "CACHE_NEG_WARM_SEED": str(warm_seed),
        "PATH": f"{command_dir}:{os.environ['PATH']}",
    }
    return subprocess.run(
        ["bash", str(_SUITE)],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )


def test_absent_warm_seed_is_cold_state_but_writable_shared_seed_fails(tmp_path: Path) -> None:
    """Only a present writable shared seed is a warm-cache trust-boundary breach."""
    absent_result = _run_suite(tmp_path=tmp_path, warm_seed=tmp_path / "absent")
    assert absent_result.returncode == 0, absent_result.stdout + absent_result.stderr
    assert "case=warm-seed-private result=pass state: no warm seed" in absent_result.stdout

    warm_seed = tmp_path / "warm"
    warm_seed.mkdir()
    shared = warm_seed / "shared-cache-entry"
    shared.write_text("cache", encoding="utf-8")
    os.link(shared, tmp_path / "generation-entry")
    writable_result = _run_suite(tmp_path=tmp_path, warm_seed=warm_seed)
    assert writable_result.returncode == 1, writable_result.stdout + writable_result.stderr
    assert "case=warm-seed-private result=fail VIOLATION:" in writable_result.stdout
