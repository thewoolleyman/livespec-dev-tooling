"""Scheduled, advisory entry point for the Rule-26 mutation kill matrix.

A host scheduler (a systemd timer, cron) runs this; nothing gates on it, and
it is never part of `just check`, a commit hook or a required CI job.  Each
run first retains the previous run's report at `RETAINED_PATH`, then runs the
engine with that report as its previous report, so every scheduled run writes
a fresh report and a what-changed summary at the same documented paths as an
on-demand run.  When no previous report is retained, it says so and writes
the report alone.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from livespec_dev_tooling import mutation_kill_matrix_runner

__all__: list[str] = [
    "RETAINED_PATH",
    "main",
]


RETAINED_PATH = Path("reports/previous/mutation-kill-matrix.json")
_NOTHING_RETAINED = " ".join(
    (
        "mutation-kill-matrix-scheduled: no report from a previous run is retained,",
        "so this run writes its report without a what-changed summary\n",
    )
)


def main(*, argv: list[str] | None = None) -> int:
    """Retain the last report, then run the engine against it."""
    parser = argparse.ArgumentParser(
        description="Run the Rule-26 kill matrix on a schedule, against the last report."
    )
    _ = parser.add_argument("target", type=Path, help="package root to run the kill matrix over")
    arguments, engine_arguments = parser.parse_known_args(argv)
    target = arguments.target.resolve()
    report = target / mutation_kill_matrix_runner.REPORT_PATH
    retained = target / RETAINED_PATH
    if report.is_file():
        retained.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copyfile(report, retained)
    if retained.is_file():
        engine_arguments = [*engine_arguments, "--previous-report", str(retained)]
    else:
        _ = sys.stdout.write(_NOTHING_RETAINED)
    return mutation_kill_matrix_runner.main(argv=[str(target), *engine_arguments])


if __name__ == "__main__":
    raise SystemExit(main())
