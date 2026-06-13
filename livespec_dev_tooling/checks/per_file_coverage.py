"""per_file_coverage — every covered file at 100% line+branch coverage.

The authoritative coverage gate is **per-file** at 100% line
AND 100% branch — not just total. The existing
`[tool.coverage.report].fail_under = 100` setting in
pyproject.toml is preserved as a belt-and-braces total guard,
but the per-file gate is what fails first when any single
covered file slips below threshold.

Invocation context: this script runs AFTER `pytest --cov
--cov-branch` has produced a combined `.coverage` data file in
the repo's cwd. The justfile's `check-coverage` recipe
sequences pytest then this script. The script reads the
`.coverage` file via the `coverage` Python API (a uv-managed
dependency, NOT a vendored lib — `coverage` itself isn't part
of the shipped livespec runtime, only the dev-tooling test
infrastructure).

Cycle 1 implements the missing-line-coverage rejection: walks
all measured files, generates a JSON report via
`Coverage.json_report(outfile="-")` redirected to an in-memory
buffer, parses the JSON, and fails the first time any file's
`summary.percent_covered` is below 100%. Subsequent cycles
will tighten to also cover `summary.percent_covered_branches`
and to handle the no-data case explicitly.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import
time.
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from coverage import Coverage  # noqa: E402  — uv-managed dep, available post-vendor-path-insert.

__all__: list[str] = []


# Per v033 D2: every covered file must be at 100% line coverage.
# The threshold is policy-set at 100.0 (no carveout); this constant
# names the policy threshold for use in the offender-detection loop.
_FULL_COVERAGE_PCT: float = 100.0

# Default coverage data-file name when COVERAGE_FILE is unset. The
# parallel check dispatcher (work-item livespec-dev-tooling-cmn) exports
# COVERAGE_FILE to point at this target's isolated namespace dir; a
# standalone CI run leaves it unset and falls back to the repo-root
# `.coverage` the recipe's own `pytest --cov` produced.
_DEFAULT_DATA_FILE: str = ".coverage"

# Tier-2 actionable diagnostic (work-item livespec-dev-tooling-cmn).
# When the data file is missing OR loads with zero measured files, the
# coverage report would otherwise emit the cryptic "No data to report".
# This message names the most likely cause (a concurrent/subprocess
# COVERAGE_FILE collision) and the structural fix, instead.
_EMPTY_COVERAGE_HINT: str = (
    "coverage data empty — likely a concurrent/subprocess COVERAGE_FILE "
    "collision; each dispatched target must use an isolated COVERAGE_FILE "
    "(the parallel check dispatcher assigns one per coverage namespace). "
    "See the parallel_check_dispatcher coverage-isolation docstring."
)


def _resolve_data_file(*, cwd: Path) -> Path:
    """Return the coverage data file: COVERAGE_FILE env, else cwd/.coverage.

    The dispatcher points COVERAGE_FILE at the target's isolated
    namespace dir so per-file-coverage reads exactly the data its own
    `pytest --cov` wrote there; an unset env (the CI standalone job)
    falls back to the repo-root default.
    """
    env_file = os.environ.get("COVERAGE_FILE")
    if env_file:
        return Path(env_file)
    return cwd / _DEFAULT_DATA_FILE


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("per_file_coverage")
    cwd = Path.cwd()
    coverage_file = _resolve_data_file(cwd=cwd)
    if not coverage_file.is_file():
        log.error(
            "no coverage data found",
            expected_path=str(coverage_file),
            hint=_EMPTY_COVERAGE_HINT,
        )
        return 1

    cov = Coverage(data_file=str(coverage_file))
    cov.load()

    # Tier-2 empty-data guard (work-item livespec-dev-tooling-cmn): a
    # present-but-empty data file (zero measured files) is the symptom of
    # a concurrent/subprocess COVERAGE_FILE collision whose `coverage
    # combine` swept the data. `Coverage.json_report` raises NoDataError
    # on it (the cryptic "No data to report"); checking measured_files()
    # up front lets us emit the actionable diagnostic WITHOUT a
    # try/except and without crashing on the exception.
    if not cov.get_data().measured_files():
        log.error(
            "coverage data empty (no measured files)",
            data_file=str(coverage_file),
            hint=_EMPTY_COVERAGE_HINT,
        )
        return 1

    buf = io.StringIO()
    with redirect_stdout(buf):
        _ = cov.json_report(outfile="-")
    report = json.loads(buf.getvalue())

    offenders: list[tuple[str, dict[str, object]]] = []
    for fname, file_info in sorted(report["files"].items()):
        summary = file_info["summary"]
        line_pct = summary.get("percent_covered", _FULL_COVERAGE_PCT)
        if line_pct < _FULL_COVERAGE_PCT:
            offenders.append((fname, summary))

    if offenders:
        for fname, summary in offenders:
            log.error(
                "file below 100% coverage",
                file=fname,
                line_percent=summary.get("percent_covered"),
                missing_lines=summary.get("missing_lines"),
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
