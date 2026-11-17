"""ci-green derives the check-run names of a job whose `name:` templates its matrix axes.

Work-item livespec-dev-tooling-ymog6r (plan stale-base-merge-options). A rollout
measured that `livespec-orchestrator-beads-fabro` names its gating jobs
`${{ matrix.target }} (${{ matrix.uid }})` and
`check-per-file-coverage-shard (${{ matrix.uid }}, ${{ matrix.shard }}/4)`, so the
required-leg derivation returned nothing for them and the merge-group skip could
never fire there.

The reader now expands the CROSS PRODUCT of the matrix's plain axes into the
names the forge reports. It still never guesses: an axis the name does not use
(its legs would share one name), `include:` / `exclude:`, a dynamic matrix, a
non-scalar or YAML-ambiguous axis value, and any other expression in the name
stay underivable, so the gate and the skip fail closed.
"""

from __future__ import annotations

import pytest

from livespec_dev_tooling.ci_green_required_legs import (
    NEVER_CREATED,
    UNDERIVABLE,
    LegGap,
    RunJob,
    leg_gaps,
    required_legs,
)

__all__: list[str] = []

_GATE = "  gate:\n    needs: [matrixed]\n"
_UID = "        uid:\n          - nonroot\n"
_TARGETS = "        target:\n          - check-lint\n          - check-types\n"
_SHARDS = "        shard: [1, 2, 3, 4]\n"


def _ci(*, name: str, matrix: str) -> str:
    head = f"jobs:\n  matrixed:\n    name: {name}\n    strategy:\n      matrix:\n"
    return head + matrix + _GATE


def _legs(*, name: str, matrix: str) -> tuple[str, ...]:
    needed = required_legs(ci_yaml_text=_ci(name=name, matrix=matrix), gate_job="gate")
    assert len(needed) == 1
    return needed[0][1]


def test_target_and_uid_axes_expand_to_the_cross_product_of_names() -> None:
    legs = _legs(name="${{ matrix.target }} (${{ matrix.uid }})", matrix=_UID + _TARGETS)
    assert legs == ("check-lint (nonroot)", "check-types (nonroot)")


def test_an_inline_list_axis_expands_one_name_per_entry() -> None:
    name = "shard (${{ matrix.uid }}, ${{ matrix.shard }}/4)"
    legs = _legs(name=name, matrix=_UID + _SHARDS)
    assert legs == (
        "shard (nonroot, 1/4)",
        "shard (nonroot, 2/4)",
        "shard (nonroot, 3/4)",
        "shard (nonroot, 4/4)",
    )


def test_a_uid_only_matrix_names_one_leg() -> None:
    assert _legs(name="batch (${{ matrix.uid }})", matrix=_UID) == ("batch (nonroot)",)


def test_a_quoted_scalar_axis_value_is_unquoted() -> None:
    matrix = "        uid: ['nonroot', \"root\"]\n"
    legs = _legs(name="job (${{ matrix.uid }})", matrix=matrix)
    assert legs == ("job (nonroot)", "job (root)")


def test_a_missing_shard_leg_is_a_never_created_gap() -> None:
    ci_text = _ci(name="s (${{ matrix.shard }})", matrix=_SHARDS)
    run_jobs = tuple(
        RunJob(name=f"s ({shard})", status="completed", conclusion="success") for shard in (1, 2, 3)
    )
    gaps = leg_gaps(ci_yaml_text=ci_text, gate_job="gate", run_jobs=run_jobs)
    assert gaps == (LegGap(leg="s (4)", finding=NEVER_CREATED),)


@pytest.mark.parametrize(
    ("name", "matrix"),
    [
        ("job (${{ matrix.uid }})", _UID + _TARGETS),
        ("job (${{ matrix.uid }}, ${{ matrix.nope }})", _UID),
        ("job (${{ matrix.uid }})", _UID + "        include:\n          - uid: root\n"),
        ("job (${{ matrix.uid }})", _UID + "        exclude:\n          - uid: nonroot\n"),
        ("job (${{ matrix.uid }}, ${{ github.event_name }})", _UID),
        ("job (${{ matrix.uid }})", "        uid: ${{ fromJSON(vars.UIDS) }}\n"),
        ("job (${{ matrix.uid }})", "        uid: [true, false]\n"),
        ("job (${{ matrix.uid }})", "        uid: [1.0, 2]\n"),
        ("job (${{ matrix.uid }})", "        uid: [01]\n"),
        ("job (${{ matrix.uid }})", "        uid: [a b]\n"),
        ("job (${{ matrix.uid }})", "        uid: [a, a]\n"),
        ("job (${{ matrix.uid }})", "        uid: []\n"),
        ("job (${{ matrix.uid }})", "        uid:\n          - {k: v}\n"),
        ("job (${{ matrix.uid }})", "        uid: nonroot\n"),
        ("job (${{ matrix.uid }})", "        uid:\n          - nonroot\n        uid2:\n"),
    ],
    ids=[
        "unused-axis",
        "unknown-axis",
        "include",
        "exclude",
        "foreign-expression",
        "dynamic-matrix",
        "yaml-boolean",
        "yaml-float",
        "yaml-leading-zero",
        "value-with-space",
        "duplicate-value",
        "empty-axis",
        "mapping-value",
        "scalar-axis",
        "empty-second-axis",
    ],
)
def test_every_shape_it_cannot_name_with_certainty_is_underivable(
    *, name: str, matrix: str
) -> None:
    ci_text = _ci(name=name, matrix=matrix)
    gaps = leg_gaps(ci_yaml_text=ci_text, gate_job="gate", run_jobs=())
    assert gaps == (LegGap(leg="matrixed", finding=UNDERIVABLE),)
