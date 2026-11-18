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
        --run-id <id> --out <json> [--read-failed] [--repo <owner/name>]

With `--repo` the CLI also raises and closes the master-health alert issues through `gh api`
(the workflow supplies `GH_TOKEN` and `issues: write`); without it only the payload is written.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ldizae

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.budgeted_gh import gh_read
from livespec_dev_tooling.ci_green_required_legs import (
    RunJob,
    leg_gaps,
    required_legs,
)
from livespec_dev_tooling.gate_results import collect_jobs
from livespec_dev_tooling.master_health_publisher import publish_master_health

__all__: list[str] = ["RunRef", "build_payload", "main"]

# A required leg that ran but did not succeed is reported by its status; every other gap (a leg
# never created, an underivable leg set) means ci-green's own read of the run failed.
_LEG_STATUS_FINDING = "status "

# The label every alert issue carries; the publisher raises issues with the same label.
_ALERT_LABEL = "master-green-external-red"


@dataclass(frozen=True, kw_only=True)
class RunRef:
    """The commit and workflow run a master-health payload is published for."""

    head_sha: str
    run_id: int


class _RecordingForge:
    """A forge that records the one check run instead of creating it."""

    def __init__(self) -> None:
        self.created: dict[str, Any] = {}

    def create_check_run(self, **kwargs: Any) -> None:
        self.created = dict(kwargs)


class _IssueForge:
    """A recording forge that also drives the alert issues through `gh api` for one repository."""

    def __init__(self, *, repo: str) -> None:
        self.created: dict[str, Any] = {}
        self._repo = repo

    def create_check_run(self, **kwargs: Any) -> None:
        self.created = dict(kwargs)

    def _gh(self, *args: str) -> str:
        """Run `gh api` through the budgeted boundary; a failure raises, so no alert is guessed."""
        read = gh_read(args=["api", *args])
        if read.returncode != 0:
            detail = read.stderr.strip()
            message = f"gh api {' '.join(args[:3])} failed ({read.returncode}): {detail}"
            raise RuntimeError(message)
        return read.stdout

    def find_open_issues(
        self, *, title: str | None = None, label: str = _ALERT_LABEL
    ) -> list[dict[str, Any]]:
        """Open issues (never pull requests) carrying the label, narrowed to a title if given."""
        out = self._gh(
            "--paginate",
            f"repos/{self._repo}/issues?state=open&labels={label}&per_page=100",
            "--jq",
            ".[]",
        )
        issues = [cast("dict[str, Any]", json.loads(line)) for line in out.splitlines() if line]
        return [
            issue
            for issue in issues
            if not issue.get("pull_request") and (title is None or issue.get("title") == title)
        ]

    def create_issue(self, *, title: str, labels: Sequence[str]) -> None:
        """Raise one issue."""
        _ = self._gh(
            "--method",
            "POST",
            f"repos/{self._repo}/issues",
            "-f",
            f"title={title}",
            *(arg for label in labels for arg in ("-f", f"labels[]={label}")),
        )

    def close_issue(self, *, issue: Mapping[str, Any], comment: str) -> None:
        """Comment on an open alert, then close it."""
        base = f"repos/{self._repo}/issues/{issue['number']}"
        _ = self._gh("--method", "POST", f"{base}/comments", "-f", f"body={comment}")
        _ = self._gh("--method", "PATCH", base, "-f", "state=closed")


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
    run: RunRef,
    repo: str | None = None,
) -> dict[str, Any]:
    """The check-run payload for one run; `run_jobs` None is a read that gave no answer.

    With `repo` the alert issues are raised and closed through the forge as a side effect.
    """
    forge = _RecordingForge() if repo is None else _IssueForge(repo=repo)
    if run_jobs is None:
        _ = publish_master_health(
            forge=forge,
            head_sha=run.head_sha,
            run_id=run.run_id,
            ci_green_passed=False,
            jobs=[],
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
        head_sha=run.head_sha,
        run_id=run.run_id,
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
    _ = parser.add_argument("--repo")
    parsed = parser.parse_args(argv)
    payload = build_payload(
        ci_yaml_text=parsed.workflow.read_text(encoding="utf-8"),
        gate_job=parsed.gate_job,
        run_jobs=None if parsed.read_failed else _read_run_jobs(pages_file=parsed.jobs_pages),
        results_dir=parsed.results_dir,
        run=RunRef(head_sha=parsed.head_sha, run_id=parsed.run_id),
        repo=parsed.repo,
    )
    parsed.out.parent.mkdir(parents=True, exist_ok=True)
    _ = parsed.out.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
