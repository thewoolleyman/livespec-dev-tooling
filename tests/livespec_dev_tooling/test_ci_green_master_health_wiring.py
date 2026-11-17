"""ci.yml wires the gate-result upload and the master-health publishing steps.

Work-item livespec-dev-tooling-bk2d73, `SPECIFICATION/contracts.md` section
"Master-green gate and external red", paragraphs "What a failed gating job
publishes" and "The master-health check run". These read the committed
`.github/workflows/ci.yml`:

- every gating job (the `needs:` of `ci-green`) ends with an `always()` step that
  publishes its result through the `publish-gate-result` composite Action;
- `ci-green` carries its own checkout, forge-read, artifact-download and
  master-health steps, each running only on a push to master and on every outcome,
  master-health last, after the pinned reader step;
- the token carries `checks: write` and no `issues: write` (nothing here uses it);
- the pinned reader step is not the publishing invocation (distinct module).
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_CI = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
_ACTION = _ROOT / ".github" / "actions" / "publish-gate-result" / "action.yml"
_NEXT_JOB = re.compile(r"\n(?=  [A-Za-z0-9_-]+:\n)")
_COND = "if: ${{ always() && github.event_name == 'push' && github.ref == 'refs/heads/master' }}"


def _job(*, name: str) -> str:
    rest = _CI[_CI.index(f"\n  {name}:\n") + 1 :]
    return _NEXT_JOB.split(rest, maxsplit=1)[0]


def _steps(*, block: str) -> list[str]:
    return ["      - name:" + part for part in block.split("      - name:")[1:]]


def _gating_jobs() -> list[str]:
    needs = re.search(r"\n  ci-green:\n(?:.*\n)*?    needs: \[([^\]]*)\]", _CI)
    assert needs is not None
    return [member.strip() for member in needs.group(1).split(",")]


def test_every_gating_job_ends_with_an_always_publishing_step() -> None:
    last_steps = {job: _steps(block=_job(name=job))[-1] for job in _gating_jobs()}
    bad = [
        job
        for job, step in last_steps.items()
        if "if: ${{ always() }}" not in step
        or "uses: ./.github/actions/publish-gate-result" not in step
        or "job-status: ${{ job.status }}" not in step
    ]
    assert bad == []


def test_matrix_gating_jobs_name_the_artifact_by_the_leg() -> None:
    matrix_jobs = [job for job in _gating_jobs() if "name: ${{ matrix.target }}" in _job(name=job)]
    named = [
        job
        for job in matrix_jobs
        if "name: ${{ matrix.target }}" in _steps(block=_job(name=job))[-1]
    ]
    assert (sorted(matrix_jobs), sorted(named)) == (
        ["check-coverage", "check-metadata", "check-python"],
        ["check-coverage", "check-metadata", "check-python"],
    )


def test_the_composite_action_uploads_by_job_and_run_attempt_on_every_outcome() -> None:
    text = _ACTION.read_text(encoding="utf-8")
    facts = (
        "name: gate-result-${{ inputs.name }}-${{ github.run_attempt }}" in text,
        "python3 -m livespec_dev_tooling.gate_results write" in text,
        "uses: actions/upload-artifact@v4" in text,
    )
    assert facts == (True, True, True)


def test_ci_green_publishing_steps_follow_the_reader_and_end_with_master_health() -> None:
    steps = _steps(block=_job(name="ci-green"))
    names = [step.splitlines()[0] for step in steps]
    reader = next(i for i, name in enumerate(names) if "Every required leg was created" in name)
    tail = names[reader + 1 :]
    assert [name.split("name: ", 1)[1] for name in tail] == [
        "Checkout (for the master-health publishing steps)",
        "Put the retrying forge call on the path (master-health publishing)",
        "Download the gating jobs' result artifacts",
        "Publish master-health on the head commit",
    ]


def test_every_publishing_step_runs_only_on_a_master_push_and_on_every_outcome() -> None:
    steps = _steps(block=_job(name="ci-green"))
    publishing = steps[-4:]
    assert [_COND in step for step in publishing] == [True, True, True, True]


def test_the_publishing_invocation_is_distinct_from_the_pinned_reader() -> None:
    steps = _steps(block=_job(name="ci-green"))
    publish = steps[-1]
    facts = (
        "python3 -m livespec_dev_tooling.master_health_publish" in publish,
        "ci_green_required_legs" in publish,
        publish.index("livespec-forge-read") < publish.index("master_health_publish"),
        publish.index("master_health_publish") < publish.index("gh api --method POST"),
        "--read-failed" in publish,
    )
    assert facts == (True, False, True, True, True)


def test_the_gate_token_may_publish_the_check_run_and_gains_no_unused_permission() -> None:
    # issues: write arrives with the alert item (cslfje), which is the first step to use it.
    block = _job(name="ci-green")
    assert ("      checks: write\n" in block, "      issues: write\n" in block) == (True, False)
