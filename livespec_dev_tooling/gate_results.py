"""gate_results — a gating job's published result and ci-green's per-job read of it.

Authority: `SPECIFICATION/contracts.md` section "Master-green gate and external red",
paragraph "What a failed gating job publishes" (work-item livespec-dev-tooling-bk2d73).

A gating job writes one result (`write`): the external-cause records produced during
its run, its count of defect findings and an `external_only` verdict. It uploads that
result as the workflow artifact `artifact_name(name=<job>, attempt=<run attempt>)`, on
every outcome. `ci-green` reads, per job, the artifact of the attempt the jobs read
reports as the latest (`collect_jobs`), so a re-run neither collides with an earlier
upload nor leaves a stale result, and a failed job with no readable artifact for its
latest attempt publishes no result, which counts as `external_only: false`.

CLI:
    python3 -m livespec_dev_tooling.gate_results write --name <job> --attempt <n> \
        --job-status <status> --records <jsonl> --defect-findings <file> --out <json>

The records file holds one external-cause record `{dependency, kind, evidence}` per
line and the defect-findings file one integer; either may be absent (no records, zero).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

__all__: list[str] = ["artifact_name", "build_result", "collect_jobs", "main"]

_ARTIFACT_PREFIX = "gate-result"
_RESULT_FILE = "result.json"
_PASSED = frozenset({"success", "skipped"})
# `output.summary` must stay under 60000 characters; the jobs array shares it with the
# rest of the summary object, so the records are fitted into this smaller budget.
_RECORDS_BUDGET = 50000
_EVIDENCE_START = 400


def artifact_name(*, name: str, attempt: int) -> str:
    """The workflow artifact a gating job's result is uploaded as, named by job and attempt."""
    return f"{_ARTIFACT_PREFIX}-{name}-{attempt}"


def build_result(
    *,
    name: str,
    attempt: int,
    job_status: str,
    records: list[dict[str, str]],
    defect_findings: int,
) -> dict[str, Any]:
    """One job's result. `external_only` needs a failed job, a record and no defect finding."""
    failed = job_status not in _PASSED
    return {
        "name": name,
        "attempt": attempt,
        "job_status": job_status,
        "records": records,
        "defect_findings": defect_findings,
        "external_only": failed and bool(records) and defect_findings == 0,
    }


def _read_records(*, path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _read_defect_findings(*, path: Path) -> int:
    return int(path.read_text(encoding="utf-8").strip() or "0") if path.is_file() else 0


def _read_result(*, results_dir: Path, name: str, attempt: int) -> dict[str, Any] | None:
    path = results_dir / artifact_name(name=name, attempt=attempt) / _RESULT_FILE
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cast("dict[str, Any]", loaded) if isinstance(loaded, dict) else None


def _fit(*, records: list[dict[str, str]]) -> list[dict[str, str]]:
    """Truncate each record's evidence until the records fit the summary budget."""
    cap = _EVIDENCE_START
    fitted = records
    while len(json.dumps(fitted)) > _RECORDS_BUDGET and cap > 0:
        fitted = [
            {**record, "evidence": str(record.get("evidence", ""))[:cap]} for record in records
        ]
        cap //= 2
    return fitted


def collect_jobs(
    *,
    legs: Sequence[str],
    run_jobs: Sequence[Mapping[str, Any]],
    results_dir: Path,
) -> list[dict[str, Any]]:
    """Each failed gating leg with the result of its latest attempt, or no result."""
    jobs: list[dict[str, Any]] = []
    for leg in legs:
        for run_job in (job for job in run_jobs if job["name"] == leg):
            conclusion = str(run_job.get("conclusion") or "none")
            if conclusion in _PASSED:
                continue
            result = _read_result(
                results_dir=results_dir, name=leg, attempt=int(run_job.get("run_attempt") or 1)
            )
            records: list[dict[str, str]] = [] if result is None else list(result["records"])
            defects = 0 if result is None else int(result["defect_findings"])
            jobs.append(
                {
                    "name": leg,
                    "result": conclusion,
                    "external_only": bool(records) and defects == 0,
                    "defect_findings": defects,
                    "records": _fit(records=records),
                }
            )
    return jobs


def _write(*, parsed: argparse.Namespace) -> int:
    result = build_result(
        name=parsed.name,
        attempt=parsed.attempt,
        job_status=parsed.job_status,
        records=_read_records(path=parsed.records),
        defect_findings=_read_defect_findings(path=parsed.defect_findings),
    )
    parsed.out.parent.mkdir(parents=True, exist_ok=True)
    _ = parsed.out.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def main(*, argv: list[str] | None = None) -> int:
    """Write one gating job's result file."""
    parser = argparse.ArgumentParser(description="a gating job's published result")
    commands = parser.add_subparsers(dest="command", required=True)
    write = commands.add_parser("write")
    _ = write.add_argument("--name", required=True)
    _ = write.add_argument("--attempt", type=int, required=True)
    _ = write.add_argument("--job-status", required=True)
    _ = write.add_argument("--records", type=Path, required=True)
    _ = write.add_argument("--defect-findings", type=Path, required=True)
    _ = write.add_argument("--out", type=Path, required=True)
    return _write(parsed=parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
