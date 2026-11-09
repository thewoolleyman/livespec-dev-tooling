"""ci-green counts a required leg as passed only when the run CREATED it and it SUCCEEDED.

Work-item livespec-dev-tooling-nofeol. Pull-request run 42673814418 was hit by
the 2026-11-09 GitHub Actions outage and created 8 of its 13 jobs. `check-types`
ran while its matrix siblings `check-lint` and `check-format` never existed, and
neither coverage job was created. ci-green's only failing step reads
`needs.*.result` for `failure` or `cancelled`, found neither, and passed; the PR
merged with no lint, format or coverage verdict on its head.

The fixtures under `tests/fixtures/ci_green_required_legs/` are the REAL job
sets of three runs of this repository, read from the Actions jobs API in the
exact projection the gate step requests (`.jobs[] | {name, status,
conclusion}`):

- 42673814418, the partial pull-request run that merged;
- 42674666440, the full master push run of the same change;
- 42632611055, an expedited incident pull-request run (livespec-dev-tooling#3870)
  in which `check-per-file-coverage`, `check-coverage` and
  `check-check-coverage-incremental` were omitted by incident policy through
  their explicit `omitted-by-incident-policy` steps, and every leg still
  concluded `success`.

Each is judged against the committed `.github/workflows/ci.yml`, so a change to
the gate's needs or to a matrix moves these verdicts with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.ci_green_required_legs import (
    NEVER_CREATED,
    NO_NEEDS,
    UNDERIVABLE,
    LegGap,
    RunJob,
    leg_gaps,
    main,
    parse_run_jobs,
    required_legs,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "ci_green_required_legs"
_PARTIAL_PR_RUN = _FIXTURES / "run-42673814418-jobs.jsonl"
_FULL_MASTER_RUN = _FIXTURES / "run-42674666440-jobs.jsonl"
_INCIDENT_OMISSION_RUN = _FIXTURES / "run-42632611055-jobs.jsonl"
_GATE = "ci-green"

# Every leg ci-green's needs create on any run of the committed workflow.
_EXPECTED_LEGS = frozenset(
    {
        "check-types",
        "check-lint",
        "check-format",
        "check-per-file-coverage",
        "check-coverage",
        "check-python-batch",
        "check-fleet-conformance",
        "check-red-green-replay",
        "check-check-coverage-incremental",
        "check-metadata-batch",
        "incident-ci",
    }
)


def _ci_text() -> str:
    return _CI_YML.read_text(encoding="utf-8")


def _jobs(*, path: Path) -> tuple[RunJob, ...]:
    return parse_run_jobs(jobs_jsonl=path.read_text(encoding="utf-8"))


def _all_success(*, legs: frozenset[str]) -> tuple[RunJob, ...]:
    return tuple(RunJob(name=leg, status="completed", conclusion="success") for leg in sorted(legs))


def test_the_committed_workflow_requires_every_matrix_leg_by_name() -> None:
    derived = required_legs(ci_yaml_text=_ci_text(), gate_job=_GATE)
    legs = frozenset(leg for _job, job_legs in derived for leg in job_legs)
    facts = (legs == _EXPECTED_LEGS, all(job_legs for _job, job_legs in derived))
    assert facts == (True, True)


def test_the_partial_outage_run_that_merged_fails_naming_each_never_created_leg() -> None:
    gaps = leg_gaps(ci_yaml_text=_ci_text(), gate_job=_GATE, run_jobs=_jobs(path=_PARTIAL_PR_RUN))
    assert set(gaps) == {
        LegGap(leg="check-lint", finding=NEVER_CREATED),
        LegGap(leg="check-format", finding=NEVER_CREATED),
        LegGap(leg="check-per-file-coverage", finding=NEVER_CREATED),
        LegGap(leg="check-coverage", finding=NEVER_CREATED),
    }


def test_the_full_master_run_passes() -> None:
    gaps = leg_gaps(ci_yaml_text=_ci_text(), gate_job=_GATE, run_jobs=_jobs(path=_FULL_MASTER_RUN))
    assert gaps == ()


def test_an_expedited_incident_run_whose_members_were_omitted_by_policy_still_passes() -> None:
    run_jobs = _jobs(path=_INCIDENT_OMISSION_RUN)
    gaps = leg_gaps(ci_yaml_text=_ci_text(), gate_job=_GATE, run_jobs=run_jobs)
    assert gaps == ()


def test_a_skipped_coverage_consumer_fails_the_gate() -> None:
    run_jobs = (
        *_all_success(legs=_EXPECTED_LEGS - {"check-coverage"}),
        RunJob(name="check-coverage", status="completed", conclusion="skipped"),
    )
    gaps = leg_gaps(ci_yaml_text=_ci_text(), gate_job=_GATE, run_jobs=run_jobs)
    assert gaps == (LegGap(leg="check-coverage", finding="status completed, conclusion skipped"),)


def test_a_leg_with_no_conclusion_fails_the_gate() -> None:
    run_jobs = (
        *_all_success(legs=_EXPECTED_LEGS - {"check-lint"}),
        RunJob(name="check-lint", status="queued", conclusion=""),
    )
    gaps = leg_gaps(ci_yaml_text=_ci_text(), gate_job=_GATE, run_jobs=run_jobs)
    assert gaps == (LegGap(leg="check-lint", finding="status queued, conclusion none"),)


_SYNTHETIC_CI = """name: CI
on:
  pull_request:
jobs:
  # a comment line at the job indent belongs to no job
  matrixed:
    name: ${{ matrix.target }}
    strategy:
      matrix:
        target:
          - leg-a  # trailing comment
          # a comment between targets

          - leg-b
    steps:
      - name: Checkout
        uses: actions/checkout@v5
  unnamed:
    runs-on: ubuntu-latest
  named:
    name: literal-name
  templated:
    name: ${{ matrix.other }}
  gate:
    needs: [matrixed, unnamed, named, templated, undefined]
    if: always()
trailing-top-level-key: true
"""


def test_leg_names_derive_from_matrix_targets_literal_names_and_job_ids() -> None:
    derived = dict(required_legs(ci_yaml_text=_SYNTHETIC_CI, gate_job="gate"))
    assert derived == {
        "matrixed": ("leg-a", "leg-b"),
        "unnamed": ("unnamed",),
        "named": ("literal-name",),
        "templated": (),
        "undefined": (),
    }


def test_an_underivable_needed_job_fails_closed() -> None:
    run_jobs = _all_success(legs=frozenset({"leg-a", "leg-b", "unnamed", "literal-name"}))
    gaps = leg_gaps(ci_yaml_text=_SYNTHETIC_CI, gate_job="gate", run_jobs=run_jobs)
    assert gaps == (
        LegGap(leg="templated", finding=UNDERIVABLE),
        LegGap(leg="undefined", finding=UNDERIVABLE),
    )


@pytest.mark.parametrize("gate_job", ["matrixed", "absent-gate"])
def test_a_gate_with_no_parseable_needs_fails_closed(*, gate_job: str) -> None:
    gaps = leg_gaps(ci_yaml_text=_SYNTHETIC_CI, gate_job=gate_job, run_jobs=())
    assert gaps == (LegGap(leg=gate_job, finding=NO_NEEDS),)


def test_a_scalar_needs_value_is_one_needed_job() -> None:
    ci_text = (
        "jobs:\n"
        "  only:\n"
        "    name: ${{ matrix.target }}\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        "          - only-leg\n"
        "  gate:\n"
        "    needs: only\n"
    )
    assert required_legs(ci_yaml_text=ci_text, gate_job="gate") == (("only", ("only-leg",)),)


def test_parse_run_jobs_reads_null_fields_and_skips_blank_lines() -> None:
    text = '{"name": "a", "status": "completed", "conclusion": "success"}\n\n{"name": "b", "status": null, "conclusion": null}\n'
    assert parse_run_jobs(jobs_jsonl=text) == (
        RunJob(name="a", status="completed", conclusion="success"),
        RunJob(name="b", status="", conclusion=""),
    )


def _argv(*, jobs: Path) -> list[str]:
    return ["--workflow", str(_CI_YML), "--gate-job", _GATE, "--jobs", str(jobs)]


def test_main_fails_the_partial_outage_run_with_one_annotation_per_gap(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(argv=_argv(jobs=_PARTIAL_PR_RUN))
    out = capsys.readouterr().out
    facts = (
        exit_code,
        out.count("::error::ci-green: required leg "),
        "::error::ci-green: required leg check-lint: never created in this run" in out,
        out.rstrip().endswith("FAILED"),
    )
    assert facts == (1, 4, True, True)


def test_main_passes_the_full_master_run(*, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(argv=_argv(jobs=_FULL_MASTER_RUN))
    out = capsys.readouterr().out
    assert (exit_code, "::error::" in out, out.rstrip().endswith("passed")) == (0, False, True)
