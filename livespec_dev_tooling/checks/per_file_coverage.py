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

Vanished-source rewrite (work-item livespec-dev-tooling-5xh8): a
measured file whose source no longer exists on disk is dropped
from the data file — with a warning naming it — BEFORE the
report is generated. The producing case is a cold-cache CI pod,
where `uv` writes its interpreter-probe script
(`get_interpreter_info.py` plus a vendored `packaging/`) into
`~/.cache/uv/.tmpXXXX/python/`, runs it with the project's venv
interpreter — whose pytest-cov `.pth` hook is armed by
COVERAGE_PROCESS_START for every test subprocess — and deletes
the directory. `Coverage.json_report` raised `NoSource` on the
first such row and failed the gate while the tree itself was at
100%. A measured file with no source can never be first-party
code under test (the check runs in the tree the suite just
executed), so dropping it loosens nothing; rewriting the data
file without it (rather than merely skipping it here) also keeps
the consume-once `check-coverage` reuse read of the SAME file
clean.

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
from coverage import (  # noqa: E402  — uv-managed dep, available post-vendor-path-insert.
    Coverage,
    CoverageData,
)

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


# Vanished-source diagnostic (work-item livespec-dev-tooling-5xh8): a
# measured file with no source on disk at report time is a transient
# artifact some test SUBPROCESS executed and then removed — the known
# producer is uv's interpreter probe under `~/.cache/uv/.tmpXXXX/python/`
# on a cold-cache CI pod. It is dropped rather than reported: it cannot
# be analyzed at all, and it cannot be first-party code under test.
_VANISHED_SOURCE_HINT: str = (
    "measured file has no source on disk at report time; it is a transient "
    "artifact a test subprocess executed and removed (typically uv's "
    "interpreter probe under ~/.cache/uv/.tmpXXXX/python/ on a cold-cache "
    "CI pod) and is dropped from the data file before reporting."
)


def _rewrite_without(*, data: CoverageData, vanished: set[str], data_file: Path) -> None:
    """Rewrite `data_file` with every file in `vanished` dropped.

    `CoverageData.purge_files` deletes a file's line/arc rows but keeps
    its `file` row, so `measured_files()` — which every reporter walks —
    still lists it and `NoSource` still fires. The only public route to a
    file map without the row is a fresh data file: snapshot the kept
    files' arcs (branch data, the real producer's shape) or lines, plus
    their file tracers, erase, and re-add through a NEW `CoverageData`.
    The new object matters: an erased object keeps its has-arcs/has-lines
    memory and skips writing that marker into the recreated file, which
    then reads back as line data with no lines (every file at 0%).
    Dynamic contexts are not carried; neither coverage gate configures any.
    """
    kept = [fname for fname in data.measured_files() if fname not in vanished]
    tracers = {fname: tracer for fname in kept if (tracer := data.file_tracer(fname))}
    has_arcs = data.has_arcs()
    arcs = {fname: data.arcs(fname) or [] for fname in kept}
    lines = {fname: data.lines(fname) or [] for fname in kept}
    data.erase()
    fresh = CoverageData(basename=str(data_file), suffix=False)
    if has_arcs:
        fresh.add_arcs(arcs)
    else:
        fresh.add_lines(lines)
    fresh.add_file_tracers(tracers)
    fresh.write()


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

    # Vanished-source rewrite (work-item livespec-dev-tooling-5xh8): drop
    # every measured file whose source is gone BEFORE json_report walks
    # the data, or the first one raises `NoSource` and kills the gate.
    # The rewrite lands in the data FILE, so the consume-once
    # check-coverage read that follows in the `just check` aggregate sees
    # the sanitized data too; the Coverage object is then reloaded from it.
    vanished = sorted(f for f in cov.get_data().measured_files() if not Path(f).is_file())
    if vanished:
        for fname in vanished:
            log.warning(
                "measured file vanished before report; dropping it",
                file=fname,
                hint=_VANISHED_SOURCE_HINT,
            )
        _rewrite_without(data=cov.get_data(), vanished=set(vanished), data_file=coverage_file)
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
