"""Executable coverage for the tmpfs and capacity extensions to retention."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _ROOT / "ansible" / "roles" / "dev_host_retention"
_RETENTION = _ROLE / "files" / "dev-host-retention.sh"
_CAPACITY = _ROLE / "files" / "dev-host-capacity-check.sh"
_CAPACITY_TIMER = _ROLE / "templates" / "livespec-dev-host-capacity-check.timer.j2"
# The retention period and the ages straddle it by an hour each way, so a run
# slowed by host load cannot age a "new" directory past the period mid-run.
_SCRATCH_RETENTION_SECONDS = 3600
_AGED_SECONDS = 2 * _SCRATCH_RETENTION_SECONDS


def _age(*, path: Path, seconds: int) -> None:
    then = time.time() - seconds
    os.utime(path, (then, then))


def _stub(*, directory: Path, name: str, body: str) -> None:
    target = directory / name
    target.write_text(body, encoding="utf-8")
    target.chmod(0o755)


def _tmp_consumers(*, tmp_root: Path, bulk: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
    dead = tmp_root / "claude-1000" / "project" / "dead"
    live = tmp_root / "claude-1000" / "project" / "live"
    old_pytest = tmp_root / "pytest-of-ubuntu" / "pytest-1"
    new_pytest = tmp_root / "pytest-of-ubuntu" / "pytest-2"
    for directory in (dead, live, old_pytest, new_pytest):
        directory.mkdir(parents=True)
    _age(path=dead, seconds=_AGED_SECONDS)
    _age(path=live, seconds=_AGED_SECONDS)
    _age(path=old_pytest, seconds=_AGED_SECONDS)
    oldest = bulk / "oldest.dump"
    newest = bulk / "newest.dump"
    oldest.write_bytes(b"1234")
    newest.write_bytes(b"5678")
    _age(path=oldest, seconds=20)
    return dead, live, old_pytest, new_pytest, oldest, newest


def _hermetic_env(*, tmp_path: Path, tmp_root: Path, bulk: Path) -> dict[str, str]:
    """The run's environment, confined to the test's own directories.

    Without the checkout-root and uv-cache overrides the script sweeps every
    real checkout under /data/projects and walks the invoking user's real uv
    cache, which made the run load-sensitive and let it touch real state.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(directory=bin_dir, name="docker", body="#!/bin/sh\nexit 0\n")
    _stub(directory=bin_dir, name="uv", body="#!/bin/sh\nexit 0\n")
    checkout_roots = tmp_path / "checkouts"
    checkout_roots.mkdir()
    uv_cache = tmp_path / "uv-cache"
    uv_cache.mkdir()
    return os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LIVESPEC_DEV_HOST_TMP_ROOT": str(tmp_root),
        "LIVESPEC_DEV_HOST_SCRATCH_RETENTION_SECONDS": str(_SCRATCH_RETENTION_SECONDS),
        "LIVESPEC_DEV_HOST_BULK_DUMP_DIR": str(bulk),
        "LIVESPEC_DEV_HOST_BULK_DUMP_CAP_BYTES": "4",
        "LIVESPEC_DEV_HOST_RETENTION_USER": str(os.getuid()),
        "LIVESPEC_DEV_HOST_RETENTION_CHECKOUT_ROOTS": str(checkout_roots),
        "LIVESPEC_DEV_HOST_UV_CACHE_DIR": str(uv_cache),
    }


def test_retention_reclaims_dead_tmp_scratch_pytest_and_oldest_bulk_dumps(
    *, tmp_path: Path
) -> None:
    """One run keeps a live session but bounds every new tmpfs consumer."""
    assert _RETENTION.is_file(), "the committed retention script must implement tmpfs cleanup"
    tmp_root = tmp_path / "tmp"
    # The script refuses a bulk-dump directory on tmpfs, and pytest's base temp
    # is under /tmp, which is tmpfs on the dev host; the checkout's ignored tmp/
    # is on the root filesystem the script requires.
    (_ROOT / "tmp").mkdir(exist_ok=True)
    bulk = Path(tempfile.mkdtemp(prefix="retention-bulk-", dir=_ROOT / "tmp"))
    dead, live, old_pytest, new_pytest, oldest, newest = _tmp_consumers(
        tmp_root=tmp_root, bulk=bulk
    )

    # The live session's process must outlive the run however slow the host
    # is; it is terminated as soon as the run returns.
    child = subprocess.Popen(["sleep", "600"], env=os.environ | {"CLAUDE_CODE_SESSION_ID": "live"})
    try:
        done = subprocess.run(
            ["bash", str(_RETENTION)],
            env=_hermetic_env(tmp_path=tmp_path, tmp_root=tmp_root, bulk=bulk),
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    finally:
        child.terminate()
        _ = child.wait(timeout=30)
        bulk_left = {path.name for path in bulk.iterdir()}
        shutil.rmtree(bulk)

    assert done.returncode == 0, done.stdout + done.stderr
    assert not dead.exists(), done.stdout
    assert live.exists(), done.stdout
    assert not old_pytest.exists(), done.stdout
    assert new_pytest.exists(), done.stdout
    assert oldest.name not in bulk_left, "the bulk cap must remove the oldest file first"
    assert newest.name in bulk_left, "the cap must not remove newer files before older files"
    assert "free space before:" in done.stdout and "/tmp" in done.stdout
    assert "free space after:" in done.stdout


def test_capacity_check_alerts_tmp_once_without_alerting_root(*, tmp_path: Path) -> None:
    """The repeat state prevents a full tmpfs from paging every 15 minutes."""
    assert _CAPACITY.is_file(), "the committed capacity check must exist"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl_log = tmp_path / "curl.log"
    _stub(
        directory=bin_dir,
        name="df",
        body="#!/bin/sh\nprintf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'\n"
        "case \"$3\" in /tmp) printf 'tmpfs 100 75 25 75%% /tmp\\n' ;; *) printf '/dev/root 100 60 40 60%% /\\n' ;; esac\n",
    )
    _stub(directory=bin_dir, name="curl", body=f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {curl_log}\n")
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LIVESPEC_DEV_HOST_CAPACITY_STATE_DIR": str(tmp_path / "state"),
        "LIVESPEC_DEV_HOST_NTFY_TOPIC": "test-topic",
        "LIVESPEC_DEV_HOST_ROOT_THRESHOLD_PERCENT": "85",
        "LIVESPEC_DEV_HOST_TMP_THRESHOLD_PERCENT": "75",
        "LIVESPEC_DEV_HOST_CAPACITY_REPEAT_SECONDS": "3600",
    }

    first = subprocess.run(
        ["bash", str(_CAPACITY)], env=env, capture_output=True, text=True, check=False
    )
    second = subprocess.run(
        ["bash", str(_CAPACITY)], env=env, capture_output=True, text=True, check=False
    )

    assert first.returncode == second.returncode == 0
    notices = curl_log.read_text(encoding="utf-8")
    assert notices.count("/tmp") == 1
    assert "75%" in notices and "25 KiB" in notices
    assert "/ used" not in notices
    assert "OnUnitActiveSec=15min" in _CAPACITY_TIMER.read_text(encoding="utf-8")
