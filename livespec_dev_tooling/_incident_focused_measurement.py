"""Run isolated focused tests and touched-file coverage under one process owner."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_focused_types import CoverageDocument, CoverageFile

__all__: list[str] = ["measure"]


def _run(*, argv: list[str], root: Path, env: dict[str, str], timeout: float) -> dict[str, object]:
    process = subprocess.Popen(  # noqa: S603 — interpreter and flags are selected here.
        argv,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        timed_out = True
    return {
        "argv": argv,
        "returncode": process.returncode,
        "output": output,
        "timed_out": timed_out,
    }


def measure(
    *, repo_root: Path, selected: set[str], executable: list[str], timeout: float
) -> tuple[dict[str, object], dict[str, object], dict[str, CoverageFile]]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_")
        and key
        not in {
            "COVERAGE_FILE",
            "COVERAGE_PROCESS_START",
            "COVERAGE_RCFILE",
            "PYTEST_ADDOPTS",
            "EXPEDITED_INCIDENT_RESPONSE",
            "EXPEDITED_INCIDENT_RESPONSE_REVERT",
        }
    }
    with tempfile.TemporaryDirectory(prefix="livespec-incident-focused-") as temp:
        folder = Path(temp)
        env["COVERAGE_FILE"] = str(folder / "coverage.dat")
        config = folder / "coverage.ini"
        _ = config.write_text(
            "[run]\nbranch = True\ncontext = expedited-repair:focused\n[report]\nfail_under = 0\n",
            encoding="utf-8",
        )
        tests = _run(
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-o",
                "addopts=",
                "--cov",
                "--cov-branch",
                f"--cov-config={config}",
                "--cov-report=",
                "--cov-fail-under=0",
                *sorted(selected),
            ],
            root=repo_root,
            env=env,
            timeout=timeout,
        )
        report_path = folder / "coverage.json"
        report = _run(
            argv=[
                sys.executable,
                "-m",
                "coverage",
                "json",
                f"--rcfile={config}",
                "-o",
                str(report_path),
                "--show-contexts",
            ],
            root=repo_root,
            env=env,
            timeout=timeout,
        )
        raw: CoverageDocument = (
            cast("CoverageDocument", json.loads(report_path.read_text()))
            if report_path.is_file()
            else {"files": {}}
        )
        coverage = {name: raw["files"].get(name, {}) for name in executable}
    return tests, report, coverage
