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
from time import monotonic
from typing import IO, cast

from livespec_dev_tooling._coverage_measure_omitted import measuring_config
from livespec_dev_tooling._incident_focused_types import CoverageDocument, CoverageFile
from livespec_dev_tooling._isolated_coverage import (
    isolated_environment,
    pytest_coverage_arguments,
)
from livespec_dev_tooling.incident_transport import gate_child_environment

__all__: list[str] = ["measure"]

# A caller's shell could otherwise re-point the measurement, add pytest options
# (a `-k` or `--deselect`) the staged tree does not carry, or change which plugins
# load (autoload off unloads pytest-cov, so `--cov` becomes a usage error); the
# data file is set below.
_AMBIENT_OVERRIDES = (
    "COVERAGE_PROCESS_START",
    "COVERAGE_RCFILE",
    "PYTEST_ADDOPTS",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "PYTEST_PLUGINS",
)


# After the group is killed, only a descendant that escaped it can still hold the
# output pipe open; give it this long to drain, then stop waiting on it.
_DRAIN_SECONDS = 0.5


def _run(*, argv: list[str], root: Path, env: dict[str, str], deadline: float) -> dict[str, object]:
    remaining = deadline - monotonic()
    if remaining <= 0:
        return {"argv": argv, "returncode": None, "output": "", "timed_out": True}
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
        output, _ = process.communicate(timeout=remaining)
        timed_out = False
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        try:
            output, _ = process.communicate(timeout=_DRAIN_SECONDS)
        except subprocess.TimeoutExpired as late:
            output = os.fsdecode(late.output or b"")
            _ = process.wait()
            cast("IO[str]", process.stdout).close()
        timed_out = True
    return {
        "argv": argv,
        "returncode": process.returncode,
        "output": output,
        "timed_out": timed_out,
    }


def measure(
    *, repo_root: Path, selected: set[str], executable: list[str], deadline: float
) -> tuple[dict[str, object], dict[str, object], dict[str, CoverageFile]]:
    """Measure under the repository's own pytest and coverage configuration.

    Only the scope, the private data file, the bound and the process ownership
    differ from the normal coverage gates. The bound is one `deadline` the caller
    takes before its own git calls and shares with the test run and the coverage
    report, so the whole collection never outlasts it. The report is limited to
    the touched files, so a measured file that is gone by report time (a temporary
    checkout, say) cannot fail it.
    Ambient pytest and coverage overrides are dropped so the evidence reflects the
    staged tree, not the caller's shell.
    """
    ambient = gate_child_environment(environ=os.environ)
    for name in _AMBIENT_OVERRIDES:
        _ = ambient.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="livespec-incident-focused-") as temp:
        folder = Path(temp)
        env = isolated_environment(environ=ambient, data_file=str(folder / "coverage.dat"))
        config = measuring_config(repo_root=repo_root, names=executable, folder=folder)
        tests = _run(
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *pytest_coverage_arguments(tests=sorted(selected), config=config),
            ],
            root=repo_root,
            env=env,
            deadline=deadline,
        )
        report_path = folder / "coverage.json"
        report = _run(
            argv=[
                sys.executable,
                "-m",
                "coverage",
                "json",
                f"--rcfile={config}",
                "--fail-under=0",
                *(
                    [f"--include={','.join(_resolved(root=repo_root, names=executable))}"]
                    if executable
                    else []
                ),
                "-o",
                str(report_path),
            ],
            root=repo_root,
            env=env,
            deadline=deadline,
        )
        raw: CoverageDocument = (
            cast("CoverageDocument", json.loads(report_path.read_text()))
            if report_path.is_file()
            else {"files": {}}
        )
        coverage = {name: _declared(row=raw["files"].get(name, {})) for name in executable}
    return tests, report, coverage


def _resolved(*, root: Path, names: list[str]) -> list[str]:
    return [str((root / name).resolve()) for name in names]


def _declared(*, row: CoverageFile) -> CoverageFile:
    """Keep only the declared fields: per-line contexts would outgrow one argv string."""
    declared: CoverageFile = {}
    if "summary" in row:
        declared["summary"] = row["summary"]
    if "missing_lines" in row:
        declared["missing_lines"] = row["missing_lines"]
    if "missing_branches" in row:
        declared["missing_branches"] = row["missing_branches"]
    return declared
