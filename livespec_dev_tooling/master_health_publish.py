"""master_health_publish — build the master-health check-run payload ci-green posts.

Authority: `SPECIFICATION/contracts.md` section "Master-green gate and external red"
(work-item livespec-dev-tooling-ldizae, the entrypoint `ci.yml` has called since
livespec-dev-tooling-bk2d73).

The CLI reads the run's jobs pages and the per-job result artifacts the gating jobs
uploaded, builds the `master-health` check run through `publish_master_health`, and
writes its payload to `--out` for the workflow to post. It never posts and it never
reads the forge itself.

It fails closed. A jobs read that ended without an answer (`--read-failed`), or a jobs
pages file that is missing or unreadable, publishes `defect` over no jobs, never `green`.
The exit status is 0 whenever a payload was written, whatever its verdict, because the
workflow's next step posts that payload; only an unusable invocation exits non-zero.

CLI:
    python3 -m livespec_dev_tooling.master_health_publish --workflow <ci.yml> \
        --gate-job <job> --jobs-pages <json> --results-dir <dir> --head-sha <sha> \
        --run-id <id> --out <json> [--read-failed]
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ldizae

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.ci_green_required_legs import (
    RunJob,
    leg_gaps,
    required_legs,
)
from livespec_dev_tooling.gate_results import collect_jobs
from livespec_dev_tooling.master_health_publisher import publish_master_health

__all__: list[str] = ["build_payload", "main"]

# A required leg that ran but did not succeed is reported by its status; every other gap (a leg
# never created, an underivable leg set) means ci-green's own read of the run failed.
_LEG_STATUS_FINDING = "status "


class _RecordingForge:
    """A forge that records the one check run instead of creating it."""

    def __init__(self) -> None:
        self.created: dict[str, Any] = {}

    def create_check_run(self, **kwargs: Any) -> None:
        self.created = dict(kwargs)


def _read_run_jobs(*, pages_file: Path) -> list[Mapping[str, Any]] | None:
    """Every job of every page, or None when the file is absent or not a page list."""
    try:
        pages: object = json.loads(pages_file.read_text(encoding="utf-8"))
        return [job for page in cast("list[Any]", pages) for job in page["jobs"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def build_payload(
    *,
    ci_yaml_text: str,
    gate_job: str,
    run_jobs: Sequence[Mapping[str, Any]] | None,
    results_dir: Path,
    head_sha: str,
    run_id: int,
) -> dict[str, Any]:
    """The check-run payload for one run; `run_jobs` None is a read that gave no answer."""
    forge = _RecordingForge()
    if run_jobs is None:
        _ = publish_master_health(
            forge=forge, head_sha=head_sha, run_id=run_id, ci_green_passed=False, jobs=[]
        )
        return forge.created
    legs = [
        leg
        for _job, names in required_legs(ci_yaml_text=ci_yaml_text, gate_job=gate_job)
        for leg in names
    ]
    gaps = leg_gaps(
        ci_yaml_text=ci_yaml_text,
        gate_job=gate_job,
        run_jobs=tuple(
            RunJob(
                name=str(job["name"]),
                status=str(job.get("status") or ""),
                conclusion=str(job.get("conclusion") or ""),
            )
            for job in run_jobs
        ),
    )
    _ = publish_master_health(
        forge=forge,
        head_sha=head_sha,
        run_id=run_id,
        ci_green_passed=all(gap.finding.startswith(_LEG_STATUS_FINDING) for gap in gaps),
        jobs=collect_jobs(legs=legs, run_jobs=run_jobs, results_dir=results_dir),
    )
    return forge.created


def main(*, argv: list[str] | None = None) -> int:
    """Write the master-health check-run payload and exit 0."""
    parser = argparse.ArgumentParser(description="ci-green: the master-health check-run payload")
    _ = parser.add_argument("--workflow", type=Path, required=True)
    _ = parser.add_argument("--gate-job", required=True)
    _ = parser.add_argument("--jobs-pages", type=Path, required=True)
    _ = parser.add_argument("--results-dir", type=Path, required=True)
    _ = parser.add_argument("--head-sha", required=True)
    _ = parser.add_argument("--run-id", type=int, required=True)
    _ = parser.add_argument("--out", type=Path, required=True)
    _ = parser.add_argument("--read-failed", action="store_true")
    parsed = parser.parse_args(argv)
    payload = build_payload(
        ci_yaml_text=parsed.workflow.read_text(encoding="utf-8"),
        gate_job=parsed.gate_job,
        run_jobs=None if parsed.read_failed else _read_run_jobs(pages_file=parsed.jobs_pages),
        results_dir=parsed.results_dir,
        head_sha=parsed.head_sha,
        run_id=parsed.run_id,
    )
    parsed.out.parent.mkdir(parents=True, exist_ok=True)
    _ = parsed.out.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
