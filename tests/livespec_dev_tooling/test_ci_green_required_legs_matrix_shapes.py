"""ci-green's leg reader fails CLOSED on every matrix shape it does not model.

Work-item livespec-dev-tooling-nofeol, independent review of
livespec-dev-tooling#3931 (findings 1 and 2). The reader names one leg per
`matrix.target` entry for a job named `${{ matrix.target }}`. That holds only
for a matrix whose single key is a block-list `target:`:

- a second axis (`os: [linux, mac]`) creates several legs that share each
  target's name, so "a job of that name exists" would pass while one of them
  was never created;
- `include:` can add a target the list does not name, and `exclude:` can drop
  one, so the list is not the leg set.

Each such shape is therefore UNDERIVABLE, and the gate names the job and fails,
rather than counting a partial leg set. The last test pins that every job
reported under one leg name is judged, not only the first, since duplicate
names are exactly what a second axis or a renamed job would produce.
"""

from __future__ import annotations

import pytest

from livespec_dev_tooling.ci_green_required_legs import (
    UNDERIVABLE,
    LegGap,
    RunJob,
    leg_gaps,
)

__all__: list[str] = []

_PREFIX = "jobs:\n  matrixed:\n    name: ${{ matrix.target }}\n"
_GATE = "  gate:\n    needs: [matrixed]\n"

_SECOND_AXIS = (
    "    strategy:\n"
    "      matrix:\n"
    "        target:\n"
    "          - leg-a\n"
    "        os:\n"
    "          - linux\n"
    "          - mac\n"
)
_INCLUDE = (
    "    strategy:\n"
    "      matrix:\n"
    "        target:\n"
    "          - leg-a\n"
    "        include:\n"
    "          - target: leg-b\n"
)
_EXCLUDE = (
    "    strategy:\n"
    "      matrix:\n"
    "        target:\n"
    "          - leg-a\n"
    "        exclude:\n"
    "          - target: leg-a\n"
)
_FLOW_LIST = "    strategy:\n      matrix:\n        target: [leg-a]\n"
_NO_MATRIX = "    runs-on: ubuntu-latest\n"
_EMPTY_MATRIX = "    strategy:\n      matrix:\n    steps:\n      - name: Checkout\n"


def _created_leg_a() -> tuple[RunJob, ...]:
    return (RunJob(name="leg-a", status="completed", conclusion="success"),)


@pytest.mark.parametrize(
    "matrix_shape",
    [_SECOND_AXIS, _INCLUDE, _EXCLUDE, _FLOW_LIST, _NO_MATRIX, _EMPTY_MATRIX],
    ids=["second-axis", "include", "exclude", "flow-list", "no-matrix", "empty-matrix"],
)
def test_an_unmodelled_matrix_shape_is_underivable_and_fails_the_gate(*, matrix_shape: str) -> None:
    ci_text = _PREFIX + matrix_shape + _GATE
    gaps = leg_gaps(ci_yaml_text=ci_text, gate_job="gate", run_jobs=_created_leg_a())
    assert gaps == (LegGap(leg="matrixed", finding=UNDERIVABLE),)


def test_a_failed_job_under_a_leg_name_fails_the_gate_even_after_a_passing_one() -> None:
    ci_text = _PREFIX + "    strategy:\n      matrix:\n        target:\n          - leg-a\n" + _GATE
    run_jobs = (
        RunJob(name="leg-a", status="completed", conclusion="success"),
        RunJob(name="leg-a", status="completed", conclusion="failure"),
    )
    gaps = leg_gaps(ci_yaml_text=ci_text, gate_job="gate", run_jobs=run_jobs)
    assert gaps == (LegGap(leg="leg-a", finding="status completed, conclusion failure"),)
