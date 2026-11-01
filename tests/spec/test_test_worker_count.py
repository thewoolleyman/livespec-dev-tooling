"""Test-worker sizing follows the CPUs available to the process.

`nproc` already observes the process affinity mask, but a cgroup-v2 CPU quota
does not change that mask. The justfile therefore needs to prefer a finite
`cpu.max` quota before falling back to `nproc`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_executable(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _test_nprocs(*, tmp_path: Path, cpu_max: str, affinity_cpus: int, extra: dict[str, str]) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        path=bin_dir / "cat",
        body="""#!/usr/bin/env bash
if [[ "$1" == "/sys/fs/cgroup/cpu.max" ]]; then
    printf '%s\\n' "$TEST_CPU_MAX"
else
    exec /usr/bin/cat "$@"
fi
""",
    )
    _write_executable(
        path=bin_dir / "nproc",
        body="""#!/usr/bin/env bash
printf '%s\\n' "$TEST_AFFINITY_CPUS"
""",
    )
    environment = dict(os.environ)
    environment.pop("LIVESPEC_CI_LANE", None)
    environment.pop("LIVESPEC_TEST_PARALLELISM", None)
    environment.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
            "TEST_AFFINITY_CPUS": str(affinity_cpus),
            "TEST_CPU_MAX": cpu_max,
            **extra,
        }
    )
    completed = subprocess.run(
        ["just", "--evaluate", "test_nprocs"],
        cwd=str(_REPO_ROOT),
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def test_test_nprocs_prefers_a_cgroup_v2_cpu_quota_over_host_visible_cpus(
    *, tmp_path: Path
) -> None:
    assert (
        _test_nprocs(
            tmp_path=tmp_path,
            cpu_max="400000 100000",
            affinity_cpus=32,
            extra={},
        )
        == "1"
    )


def test_test_nprocs_uses_the_affinity_mask_without_a_cgroup_cpu_quota(*, tmp_path: Path) -> None:
    assert (
        _test_nprocs(
            tmp_path=tmp_path,
            cpu_max="max 100000",
            affinity_cpus=12,
            extra={},
        )
        == "3"
    )


def test_test_nprocs_preserves_an_explicit_parallelism_override(*, tmp_path: Path) -> None:
    assert (
        _test_nprocs(
            tmp_path=tmp_path,
            cpu_max="400000 100000",
            affinity_cpus=32,
            extra={"LIVESPEC_TEST_PARALLELISM": "17"},
        )
        == "17"
    )


def test_test_nprocs_preserves_auto_for_the_hosted_lane(*, tmp_path: Path) -> None:
    assert (
        _test_nprocs(
            tmp_path=tmp_path,
            cpu_max="400000 100000",
            affinity_cpus=32,
            extra={"LIVESPEC_CI_LANE": "hosted", "LIVESPEC_TEST_PARALLELISM": "17"},
        )
        == "auto"
    )
