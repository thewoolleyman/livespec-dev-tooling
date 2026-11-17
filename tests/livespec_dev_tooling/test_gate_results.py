"""A gating job's published result, and ci-green's per-job read of its latest attempt.

Work-item livespec-dev-tooling-bk2d73, `SPECIFICATION/contracts.md` section
"Master-green gate and external red", paragraph "What a failed gating job publishes".
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_dev_tooling.gate_results import (
    artifact_name,
    build_result,
    collect_jobs,
    main,
)

__all__: list[str] = []

_RECORD = {"dependency": "github.com", "kind": "forge-5xx", "evidence": "HTTP 503"}


def _put(*, root: Path, name: str, attempt: int, result: object) -> None:
    folder = root / artifact_name(name=name, attempt=attempt)
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")


def _write_argv(*, tmp_path: Path, attempt: str, records: Path, defects: Path) -> list[str]:
    return [
        "write",
        "--name",
        "check-lint",
        "--attempt",
        attempt,
        "--job-status",
        "failure",
        "--records",
        str(records),
        "--defect-findings",
        str(defects),
        "--out",
        str(tmp_path / "out" / "result.json"),
    ]


def test_the_artifact_is_named_by_job_and_run_attempt() -> None:
    assert artifact_name(name="check-lint", attempt=2) == "gate-result-check-lint-2"


def test_a_failed_job_with_records_and_no_defect_is_external_only() -> None:
    result = build_result(
        name="check-lint",
        attempt=1,
        job_status="failure",
        records=[_RECORD],
        defect_findings=0,
    )
    assert result == {
        "name": "check-lint",
        "attempt": 1,
        "job_status": "failure",
        "records": [_RECORD],
        "defect_findings": 0,
        "external_only": True,
    }


def test_a_defect_finding_a_missing_record_or_a_success_is_never_external_only() -> None:
    cases = [
        ("failure", [_RECORD], 1),
        ("failure", [], 0),
        ("cancelled", [], 0),
        ("success", [_RECORD], 0),
    ]
    facts = [
        build_result(
            name="a", attempt=1, job_status=status, records=records, defect_findings=defects
        )["external_only"]
        for status, records, defects in cases
    ]
    assert facts == [False, False, False, False]


def test_write_reads_the_records_and_the_defect_count_and_writes_the_result(
    tmp_path: Path,
) -> None:
    records = tmp_path / "records.jsonl"
    records.write_text(json.dumps(_RECORD) + "\n\n", encoding="utf-8")
    defects = tmp_path / "defects"
    defects.write_text("0\n", encoding="utf-8")
    code = main(argv=_write_argv(tmp_path=tmp_path, attempt="3", records=records, defects=defects))
    written = json.loads((tmp_path / "out" / "result.json").read_text(encoding="utf-8"))
    assert (code, written["attempt"], written["records"], written["external_only"]) == (
        0,
        3,
        [_RECORD],
        True,
    )


def test_write_with_no_records_file_and_no_defect_file_publishes_no_external_proof(
    tmp_path: Path,
) -> None:
    code = main(
        argv=_write_argv(
            tmp_path=tmp_path,
            attempt="1",
            records=tmp_path / "absent-records",
            defects=tmp_path / "absent-defects",
        )
    )
    written = json.loads((tmp_path / "out" / "result.json").read_text(encoding="utf-8"))
    assert (code, written["records"], written["defect_findings"], written["external_only"]) == (
        0,
        [],
        0,
        False,
    )


def test_collect_reads_the_artifact_of_the_latest_attempt_per_failed_job(tmp_path: Path) -> None:
    _put(root=tmp_path, name="check-lint", attempt=1, result={"records": [], "defect_findings": 4})
    _put(
        root=tmp_path,
        name="check-lint",
        attempt=2,
        result={"records": [_RECORD], "defect_findings": 0},
    )
    run_jobs = [
        {"name": "check-lint", "conclusion": "failure", "run_attempt": 2},
        {"name": "check-types", "conclusion": "success", "run_attempt": 2},
    ]
    jobs = collect_jobs(legs=["check-lint", "check-types"], run_jobs=run_jobs, results_dir=tmp_path)
    assert jobs == [
        {
            "name": "check-lint",
            "result": "failure",
            "external_only": True,
            "defect_findings": 0,
            "records": [_RECORD],
        }
    ]


def test_a_failed_job_with_no_artifact_for_its_latest_attempt_publishes_no_result(
    tmp_path: Path,
) -> None:
    _put(
        root=tmp_path,
        name="check-lint",
        attempt=1,
        result={"records": [_RECORD], "defect_findings": 0},
    )
    run_jobs = [
        {"name": "check-lint", "conclusion": "failure", "run_attempt": 2},
        {"name": "check-format", "conclusion": "cancelled", "run_attempt": 1},
    ]
    jobs = collect_jobs(
        legs=["check-lint", "check-format", "check-absent"],
        run_jobs=run_jobs,
        results_dir=tmp_path,
    )
    no_result = {"external_only": False, "defect_findings": 0, "records": []}
    assert jobs == [
        {"name": "check-lint", "result": "failure", **no_result},
        {"name": "check-format", "result": "cancelled", **no_result},
    ]


def test_an_unreadable_artifact_publishes_no_result_and_a_forged_flag_is_recomputed(
    tmp_path: Path,
) -> None:
    folder = tmp_path / artifact_name(name="check-lint", attempt=1)
    folder.mkdir()
    (folder / "result.json").write_text("{not json", encoding="utf-8")
    _put(
        root=tmp_path,
        name="check-format",
        attempt=1,
        result={"records": [], "defect_findings": 0, "external_only": True},
    )
    run_jobs = [
        {"name": "check-lint", "conclusion": "failure", "run_attempt": 1},
        {"name": "check-format", "conclusion": "failure", "run_attempt": 1},
    ]
    jobs = collect_jobs(
        legs=["check-lint", "check-format"], run_jobs=run_jobs, results_dir=tmp_path
    )
    assert [job["external_only"] for job in jobs] == [False, False]


def test_oversized_evidence_is_truncated_so_the_summary_stays_under_the_limit(
    tmp_path: Path,
) -> None:
    big = [{"dependency": "d", "kind": "k", "evidence": "x" * 5000} for _ in range(40)]
    _put(root=tmp_path, name="check-lint", attempt=1, result={"records": big, "defect_findings": 0})
    run_jobs = [{"name": "check-lint", "conclusion": "failure", "run_attempt": 1}]
    jobs = collect_jobs(legs=["check-lint"], run_jobs=run_jobs, results_dir=tmp_path)
    assert (len(jobs[0]["records"]), len(json.dumps(jobs)) < 50000, jobs[0]["external_only"]) == (
        40,
        True,
        True,
    )


def test_a_failed_job_with_records_and_a_defect_finding_never_reads_external_only(
    tmp_path: Path,
) -> None:
    _put(
        root=tmp_path,
        name="check-lint",
        attempt=1,
        result={"records": [_RECORD], "defect_findings": 2, "external_only": True},
    )
    run_jobs = [{"name": "check-lint", "conclusion": "failure", "run_attempt": 1}]
    jobs = collect_jobs(legs=["check-lint"], run_jobs=run_jobs, results_dir=tmp_path)
    assert (jobs[0]["external_only"], jobs[0]["defect_findings"]) == (False, 2)
