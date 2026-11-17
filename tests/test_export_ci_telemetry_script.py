"""Static regression tests for the CI telemetry export shell script."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".github" / "scripts" / "export-ci-telemetry.sh"


def _job_span_block(script: str) -> str:
    start = script.index('--arg name "ci.job.$jname"')
    return script[start : script.index("status:{code:$code}}')", start)]


def test_job_span_carries_ci_event_and_git_branch() -> None:
    script = _SCRIPT.read_text(encoding="utf-8")
    block = _job_span_block(script)

    assert 'run_branch="$(jq -r \'.headBranch // ""\' <<<"$run_json")"' in script
    assert 'run_event="$(jq -r \'.event // ""\' <<<"$run_json")"' in script
    assert '--arg branch "$run_branch" --arg event "$run_event"' in block
    assert '{key:"git.branch",value:{stringValue:$branch}}' in block
    assert '{key:"ci.event",value:{stringValue:$event}}' in block
