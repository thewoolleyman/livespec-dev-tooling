"""ci-green derives required legs from a block-sequence ``needs:`` list.

Work-item livespec-dev-tooling-acapf4. The reader already treats every inline
``needs: [a, b]`` member as required; this pins the same fail-closed result for
the block-list spelling used by fleet ci-green workflows.
"""

from __future__ import annotations

from livespec_dev_tooling.ci_green_required_legs import (
    NEVER_CREATED,
    LegGap,
    RunJob,
    leg_gaps,
    required_legs,
)

__all__: list[str] = []

_BLOCK_NEEDS = """jobs:
  absent-leg:
    runs-on: ubuntu-latest
  failed-leg:
    runs-on: ubuntu-latest
  ci-green:
    needs:
      - absent-leg
      - failed-leg
"""


def test_a_block_needs_list_derives_each_leg_and_reports_absent_or_failed_legs() -> None:
    run_jobs = (RunJob(name="failed-leg", status="completed", conclusion="failure"),)
    assert (
        required_legs(ci_yaml_text=_BLOCK_NEEDS, gate_job="ci-green"),
        leg_gaps(ci_yaml_text=_BLOCK_NEEDS, gate_job="ci-green", run_jobs=run_jobs),
    ) == (
        (("absent-leg", ("absent-leg",)), ("failed-leg", ("failed-leg",))),
        (
            LegGap(leg="absent-leg", finding=NEVER_CREATED),
            LegGap(leg="failed-leg", finding="status completed, conclusion failure"),
        ),
    )
