"""Executable coverage for the tmpfs and capacity extensions to retention."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _ROOT / "ansible" / "roles" / "dev_host_retention"
_RETENTION = _ROLE / "files" / "dev-host-retention.sh"
_CAPACITY = _ROLE / "files" / "dev-host-capacity-check.sh"
_CAPACITY_TIMER = _ROLE / "templates" / "livespec-dev-host-capacity-check.timer.j2"


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
    _age(path=dead, seconds=25)
    _age(path=live, seconds=25)
    _age(path=old_pytest, seconds=25)
    oldest = bulk / "oldest.dump"
    newest = bulk / "newest.dump"
    oldest.write_bytes(b"1234")
    newest.write_bytes(b"5678")
    _age(path=oldest, seconds=20)
    return dead, live, old_pytest, new_pytest, oldest, newest


def test_retention_reclaims_dead_tmp_scratch_pytest_and_oldest_bulk_dumps(
    *, tmp_path: Path
) -> None:
    """One run keeps a live session but bounds every new tmpfs consumer."""
    assert _RETENTION.is_file(), "the committed retention script must implement tmpfs cleanup"
    tmp_root = tmp_path / "tmp"
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    dead, live, old_pytest, new_pytest, oldest, newest = _tmp_consumers(
        tmp_root=tmp_root, bulk=bulk
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(directory=bin_dir, name="docker", body="#!/bin/sh\nexit 0\n")
    _stub(directory=bin_dir, name="uv", body="#!/bin/sh\nexit 0\n")
    child = subprocess.Popen(["sleep", "30"], env=os.environ | {"CLAUDE_CODE_SESSION_ID": "live"})
    try:
        done = subprocess.run(
            ["bash", str(_RETENTION)],
            env=os.environ
            | {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "LIVESPEC_DEV_HOST_TMP_ROOT": str(tmp_root),
                "LIVESPEC_DEV_HOST_SCRATCH_RETENTION_SECONDS": "10",
                "LIVESPEC_DEV_HOST_BULK_DUMP_DIR": str(bulk),
                "LIVESPEC_DEV_HOST_BULK_DUMP_CAP_BYTES": "4",
                "LIVESPEC_DEV_HOST_RETENTION_USER": str(os.getuid()),
            },
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    finally:
        child.terminate()
        _ = child.wait(timeout=30)

    assert done.returncode == 0, done.stdout + done.stderr
    assert not dead.exists(), done.stdout
    assert live.exists(), done.stdout
    assert not old_pytest.exists(), done.stdout
    assert new_pytest.exists(), done.stdout
    assert not oldest.exists(), "the bulk cap must remove the oldest file first"
    assert newest.exists(), "the cap must not remove newer files before older files"
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
