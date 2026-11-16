"""ci-green accepts skipped gating legs only when the SAME run's guard output skip=true.

Work-item livespec-dev-tooling-ymog6r (the merge-group tree-equality skip). A
gating job that carries the guard's skip condition in its `if:` is skippable; a
job that does not, and the guard itself, must still be created and succeed. The
guard is a signal-only need: ci-green reads its `skip` output through `needs`
and the reader never counts it as a leg.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.ci_green_required_legs import (
    NEVER_CREATED,
    LegGap,
    RunJob,
    leg_gaps,
    main,
    required_legs,
)

__all__: list[str] = []

_SKIP_IF = "${{ !cancelled() && needs.merge-group-guard.outputs.skip != 'true' }}"
_WORKFLOW = f"""name: CI
jobs:
  merge-group-guard:
    name: merge-group-guard
  check-lint:
    name: ${{{{ matrix.target }}}}
    needs: [merge-group-guard]
    if: {_SKIP_IF}
    strategy:
      matrix:
        target:
          - check-lint
          - check-format
  check-batch:
    name: check-batch
    needs: [merge-group-guard]
    if: {_SKIP_IF}
  incident-ci:
    name: incident-ci
    needs: [merge-group-guard]
    if: ${{{{ !cancelled() }}}}
  ci-green:
    name: ci-green
    needs: [merge-group-guard, check-lint, check-batch, incident-ci]
    if: always()
"""


def _job(*, name: str, conclusion: str) -> RunJob:
    return RunJob(name=name, status="completed", conclusion=conclusion)


def _gaps(*, jobs: list[RunJob], guard_skip: bool) -> tuple[LegGap, ...]:
    return leg_gaps(
        ci_yaml_text=_WORKFLOW, gate_job="ci-green", run_jobs=tuple(jobs), guard_skip=guard_skip
    )


_FULL = [
    _job(name="check-lint", conclusion="success"),
    _job(name="check-format", conclusion="success"),
    _job(name="check-batch", conclusion="success"),
    _job(name="incident-ci", conclusion="success"),
]
_SKIPPED = [
    _job(name="${{ matrix.target }}", conclusion="skipped"),
    _job(name="check-batch", conclusion="skipped"),
    _job(name="incident-ci", conclusion="success"),
]


def test_the_guard_is_a_signal_only_need_and_never_a_leg() -> None:
    legs = dict(required_legs(ci_yaml_text=_WORKFLOW, gate_job="ci-green"))
    assert "merge-group-guard" not in legs
    assert set(legs) == {"check-lint", "check-batch", "incident-ci"}


def test_a_full_run_passes_with_or_without_the_skip_signal() -> None:
    assert (_gaps(jobs=_FULL, guard_skip=False), _gaps(jobs=_FULL, guard_skip=True)) == ((), ())


def test_a_skipped_suite_passes_only_under_the_skip_signal() -> None:
    assert _gaps(jobs=_SKIPPED, guard_skip=True) == ()


def test_a_skipped_suite_without_the_skip_signal_fails_closed_naming_each_leg() -> None:
    gaps = _gaps(jobs=_SKIPPED, guard_skip=False)
    assert {gap.leg for gap in gaps} == {"check-lint", "check-format", "check-batch"}


def test_under_the_skip_signal_a_failed_or_unskippable_leg_still_fails() -> None:
    failed = [_job(name="check-batch", conclusion="failure"), *_SKIPPED[:1], *_SKIPPED[2:]]
    missing_incident = _SKIPPED[:2]
    assert (
        [gap.leg for gap in _gaps(jobs=failed, guard_skip=True)],
        [gap for gap in _gaps(jobs=missing_incident, guard_skip=True)],
    ) == (["check-batch"], [LegGap(leg="incident-ci", finding=NEVER_CREATED)])


def _cli_argv(*, tmp_path: Path) -> list[str]:
    workflow = tmp_path / "ci.yml"
    _ = workflow.write_text(_WORKFLOW, encoding="utf-8")
    jobs = tmp_path / "jobs.jsonl"
    _ = jobs.write_text(
        "".join(
            f'{{"name": "{job.name}", "status": "completed", "conclusion": "{job.conclusion}"}}\n'
            for job in _SKIPPED
        ),
        encoding="utf-8",
    )
    return ["--workflow", str(workflow), "--gate-job", "ci-green", "--jobs", str(jobs)]


def test_the_cli_takes_the_skip_signal_as_a_flag(tmp_path: Path) -> None:
    base = _cli_argv(tmp_path=tmp_path)
    assert (
        main(argv=base),
        main(argv=[*base, "--guard-skip", "false"]),
        main(argv=[*base, "--guard-skip", "true"]),
    ) == (1, 1, 0)


@pytest.mark.parametrize("value", ["", "yes", "TRUE "])
def test_only_the_exact_text_true_counts_as_the_skip_signal(value: str, tmp_path: Path) -> None:
    assert main(argv=[*_cli_argv(tmp_path=tmp_path), "--guard-skip", value]) == 1
