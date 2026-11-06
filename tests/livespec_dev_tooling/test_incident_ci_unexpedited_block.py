"""An unexpedited PR that retains an incident block runs the normal policy — asserted by test.

Work-item livespec-dev-tooling-z3wy33, assertion 4: "A master push and an
unexpedited factory follow-up pull request run the complete normal policy with
both incident flags forced off, regardless of any retained body block." The
plan's Guardrail 3 says the same of the follow-up. A repayment PR keeps the
`<!-- livespec-incident-ci` block in its body but carries no
`expedited-incident-response` label, so the released plan selects the `normal`
mode. The entrance step used to REFUSE that case (`::error::` and `exit 1`),
which turned `incident-ci` and therefore `ci-green` red, so such a PR could
never merge.

The step's shell is lifted out of the committed `.github/workflows/ci.yml` and
executed with bash against a stub released interpreter, so the test holds what
the step DOES, not how it is spelled:

- a `normal`-mode plan is a no-op: exit 0, a notice, no `run` or `aggregate`,
  and `omitted` unwritten (the same as the no-block path);
- a plan refusal still fails the job (label + block but no current authority);
- an `expedited-repair` plan still reaches `run` and `aggregate` and writes
  `omitted` (the control that proves the no-op is keyed on the mode).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

# The stub stands in for the released venv's interpreter. Its `-I -c` calls
# (the step's JSON projections) go to the real interpreter; its `-I -m
# <module> <verb>` calls record the verb and answer as the released entrance
# would.
_STUB = """#!/usr/bin/env bash
if [ "$1" = "-I" ] && [ "$2" = "-c" ]; then
  exec "$REAL_PYTHON" "$@"
fi
verb="$4"
echo "$verb" >> "$CALLS"
case "$verb" in
  plan)
    if [ -n "$PLAN_JSON" ]; then printf '%s' "$PLAN_JSON"; exit 0; fi
    printf '%s' 'no current authority'; exit 1 ;;
  run) exit 0 ;;
  aggregate) printf '%s' '{"status":"passed","deferred":[]}'; exit 0 ;;
esac
exit 2
"""


def _entrance_run() -> str:
    workflow = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    steps = [s for s in workflow["jobs"]["incident-ci"]["steps"] if s.get("id") == "entrance"]
    assert len(steps) == 1, steps
    return str(steps[0]["run"])


def _execute(*, tmp_path: Path, plan: dict[str, object] | None) -> dict[str, object]:
    stub = tmp_path / "released-python"
    _ = stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(0o755)
    calls = tmp_path / "calls"
    calls.touch()
    output = tmp_path / "github-output"
    output.touch()
    summary = tmp_path / "step-summary"
    summary.touch()
    env = {
        "PATH": os.environ["PATH"],
        "REAL_PYTHON": sys.executable,
        "CALLS": str(calls),
        "PLAN_JSON": "" if plan is None else json.dumps(plan),
        "RELEASED_PYTHON": str(stub),
        "PR_NUMBER": "7",
        "PR_HEAD_SHA": "b" * 40,
        "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.invalid",
        "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "token",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    completed = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", _entrance_run()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    return {
        "code": completed.returncode,
        "stdout": completed.stdout,
        "calls": calls.read_text(encoding="utf-8").split(),
        "output": output.read_text(encoding="utf-8"),
        "summary": summary.read_text(encoding="utf-8"),
    }


def test_a_retained_block_on_an_unexpedited_pr_is_a_no_op(*, tmp_path: Path) -> None:
    # `normal` is what `select_ci_plan` returns for a PR without the label.
    result = _execute(tmp_path=tmp_path, plan={"mode": "normal", "selected": ["check-lint"]})
    assert result["code"] == 0, result
    assert result["calls"] == ["plan"]
    assert "omitted=" not in str(result["output"])
    assert "::notice::" in str(result["stdout"])
    assert "::error::" not in str(result["stdout"])
    assert "selected the 'normal' mode" in str(result["summary"])
    assert "complete normal policy runs" in str(result["summary"])


def test_a_plan_refusal_still_fails_the_job(*, tmp_path: Path) -> None:
    result = _execute(tmp_path=tmp_path, plan=None)
    assert result["code"] == 1, result
    assert result["calls"] == ["plan"]
    assert "::error::released plan refused" in str(result["stdout"])
    assert "omitted=" not in str(result["output"])


def test_an_expedited_plan_still_runs_and_aggregates(*, tmp_path: Path) -> None:
    result = _execute(
        tmp_path=tmp_path, plan={"mode": "expedited-repair", "selected": ["check-lint"]}
    )
    assert result["code"] == 0, result
    assert result["calls"] == ["plan", "run", "aggregate"]
    assert "omitted=[]" in str(result["output"])
