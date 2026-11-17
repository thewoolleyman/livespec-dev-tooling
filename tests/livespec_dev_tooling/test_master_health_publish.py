"""The master-health payload CLI ci-green runs, executed as `python -m` would run it.

Work-item livespec-dev-tooling-ldizae, `SPECIFICATION/contracts.md` section
"Master-green gate and external red". ci.yml invoked this module before it existed; every
case below runs the module's `__main__` path, so a missing or unimportable module fails.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ldizae

from __future__ import annotations

import importlib.util
import json
import re
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling.ci_green_required_legs import required_legs
from livespec_dev_tooling.gate_results import artifact_name

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"
_MODULE = "livespec_dev_tooling.master_health_publish"
_RECORD = {"dependency": "github.com", "kind": "forge-5xx", "evidence": "HTTP 503"}


def _legs() -> list[str]:
    text = _WORKFLOW.read_text(encoding="utf-8")
    return [
        leg
        for _job, names in required_legs(ci_yaml_text=text, gate_job="ci-green")
        for leg in names
    ]


def _jobs(*, failed: str | None) -> list[dict[str, Any]]:
    return [
        {
            "name": leg,
            "status": "completed",
            "conclusion": "failure" if leg == failed else "success",
            "run_attempt": 1,
        }
        for leg in _legs()
    ]


def _run(
    *, tmp_path: Path, jobs: list[dict[str, Any]] | None, read_failed: bool = False
) -> dict[str, Any]:
    pages = tmp_path / "pages.json"
    if jobs is not None:
        pages.write_text(json.dumps([{"jobs": jobs}]), encoding="utf-8")
    out = tmp_path / "payload.json"
    argv = [
        _MODULE,
        "--workflow",
        str(_WORKFLOW),
        "--gate-job",
        "ci-green",
        "--jobs-pages",
        str(pages),
        "--results-dir",
        str(tmp_path / "gate-results"),
        "--head-sha",
        "abc123",
        "--run-id",
        "77",
        "--out",
        str(out),
        *(["--read-failed"] if read_failed else []),
    ]
    saved = sys.argv
    sys.argv = argv
    try:
        with pytest.raises(SystemExit) as exited:
            _ = runpy.run_module(_MODULE, run_name="__main__")
    finally:
        sys.argv = saved
    assert exited.value.code == 0
    loaded: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return loaded


def _title(*, payload: dict[str, Any]) -> str:
    return str(payload["output"]["title"])


def test_a_green_run_publishes_a_success_check_run(*, tmp_path: Path) -> None:
    payload = _run(tmp_path=tmp_path, jobs=_jobs(failed=None))
    assert (
        payload["name"],
        payload["head_sha"],
        payload["conclusion"],
        _title(payload=payload),
    ) == (
        "master-health",
        "abc123",
        "success",
        "master-health: green",
    )


def test_a_failed_job_with_an_external_record_reads_external(*, tmp_path: Path) -> None:
    leg = _legs()[0]
    folder = tmp_path / "gate-results" / artifact_name(name=leg, attempt=1)
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(
        json.dumps({"records": [_RECORD], "defect_findings": 0}), encoding="utf-8"
    )
    payload = _run(tmp_path=tmp_path, jobs=_jobs(failed=leg))
    summary = json.loads(payload["output"]["summary"])
    assert (_title(payload=payload), payload["conclusion"], summary["run_id"]) == (
        "master-health: external",
        "neutral",
        77,
    )


def test_a_failed_job_with_no_result_artifact_reads_defect(*, tmp_path: Path) -> None:
    payload = _run(tmp_path=tmp_path, jobs=_jobs(failed=_legs()[0]))
    assert _title(payload=payload) == "master-health: defect"


@pytest.mark.parametrize("read_failed", [True, False])
def test_a_jobs_read_with_no_answer_publishes_defect_never_green(
    *, tmp_path: Path, read_failed: bool
) -> None:
    """`--read-failed`, or a pages file that was never written, fails closed."""
    payload = _run(tmp_path=tmp_path, jobs=None, read_failed=read_failed)
    assert (_title(payload=payload), payload["conclusion"]) == ("master-health: defect", "neutral")


def test_a_missing_gating_leg_reads_defect(*, tmp_path: Path) -> None:
    payload = _run(tmp_path=tmp_path, jobs=_jobs(failed=None)[1:])
    assert _title(payload=payload) == "master-health: defect"


def test_every_python_module_a_workflow_runs_resolves() -> None:
    """A step naming a module that does not exist cannot pass the gate (the ldizae class defect)."""
    pattern = re.compile(r"python3? -m ([A-Za-z_][A-Za-z0-9_.]*)")
    sources = [
        *(_ROOT / ".github" / "workflows").glob("*.y*ml"),
        *(_ROOT / ".github" / "actions").rglob("*.y*ml"),
    ]
    named = {
        name.rstrip(".")
        for path in sources
        for name in pattern.findall(path.read_text(encoding="utf-8"))
        if "." in name and not name.endswith(".")
    }
    missing = sorted(name for name in named if importlib.util.find_spec(name) is None)
    assert (bool(named), missing) == (True, [])
