"""ci-green RUNS the required-leg reader over this run's jobs, so a never-created leg fails it.

Work-item livespec-dev-tooling-nofeol. `test_ci_green_required_legs.py` proves
the reader's verdicts; this module proves the committed `.github/workflows/ci.yml`
actually gives ci-green that verdict. It reads the `ci-green` job's text,
recovers the reader invocation its step runs, and replays it over the real job
sets of three runs (the fixtures under `tests/fixtures/ci_green_required_legs/`,
captured with the same API path and `--jq` projection the step uses).

The replay is the load-bearing assertion. Against the workflow as it stood
before this change, ci-green carried no reader step: its only failing step
reads `needs.*.result` for `failure` or `cancelled`, and on run 42673814418 the
forge recorded that step `skipped` and the job `success`. With no reader step
to replay, the modelled verdict is that recorded pass, and the first assertion
below fails. With the step wired, the same run fails, naming its four
never-created legs, while the full master run and the expedited incident run
(whose members were omitted by incident policy) still pass.

The remaining assertions pin the wiring the replay depends on: the job may read
the Actions API, it checks the tree out before the reader runs, the reader step
cannot be skipped or soft-failed, and the original needs-result step is still
there unchanged (the change only ADDS to the gate).

"Cannot be soft-failed" is pinned over the step's shell text, not assumed
(independent review of livespec-dev-tooling#3931, finding 3). An unreadable job
list must end in `exit 1`; the reader invocation must be the step's LAST
command, exactly as committed, so nothing after it (a trailing `true`) and
nothing on its line (`|| true`) can replace its exit status; and the step may
neither relax errexit (`set +e`) nor override its `shell:`. Each pin is
mutation-proved below against a copy of the committed workflow.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from livespec_dev_tooling.ci_green_required_legs import main

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "ci_green_required_legs"
_GATE_HEADER = "  ci-green:"
_NEXT_JOB = re.compile(r"\n(?=  [A-Za-z0-9_-]+:\n)")
_READER = "python3 -m livespec_dev_tooling.ci_green_required_legs"
_JOBS_PLACEHOLDER = '"$jobs_file"'
_API_READ = (
    'gh api --paginate "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs'
    "?filter=latest&per_page=100\" --jq '.jobs[] | {name, status, conclusion}'"
)
_READER_LINE = (
    "python3 -m livespec_dev_tooling.ci_green_required_legs "
    '--workflow .github/workflows/ci.yml --gate-job ci-green --jobs "$jobs_file"'
)
_READER_STEP_HEADER = "      - name: Every required leg was created and concluded success\n"
_UNREADABLE_BRANCH = (
    "          read_jobs || { sleep 5; read_jobs; } || { sleep 15; read_jobs; } || {\n"
    "            echo \"::error::ci-green: could not read this run's jobs from the Actions API;"
    ' failing closed"\n'
    "            exit 1\n"
    "          }\n"
)
_NEEDS_RESULT_STEP = (
    "      - name: All required checks passed\n"
    "        if: ${{ contains(needs.*.result, 'failure') || "
    "contains(needs.*.result, 'cancelled') }}\n"
    "        run: exit 1\n"
)


def _gate_block(*, text: str | None = None) -> str:
    """The `ci-green` job's text, from its header to the next job or the end."""
    text = _CI_YML.read_text(encoding="utf-8") if text is None else text
    rest = text[text.index(f"\n{_GATE_HEADER}\n") + 1 :]
    return _NEXT_JOB.split(rest, maxsplit=1)[0]


def _steps(*, block: str) -> list[str]:
    """Each step of the job as text, in order."""
    return ["      - name:" + part for part in block.split("      - name:")[1:]]


def _reader_steps(*, block: str) -> list[str]:
    return [step for step in _steps(block=block) if _READER in step]


def _replayed_verdict(*, jobs: Path) -> int:
    """ci-green's verdict over a fixture run, as the committed workflow wires it.

    No reader step means the needs-result step alone decides, and on every
    fixture run the forge recorded that step `skipped`: a pass (0).
    """
    lines = [
        line.strip()
        for step in _reader_steps(block=_gate_block())
        for line in step.splitlines()
        if line.strip().startswith(_READER)
    ]
    # The step runs from the checkout root; the replay runs from anywhere.
    resolved = {"$jobs_file": str(jobs), ".github/workflows/ci.yml": str(_CI_YML)}
    argv = [resolved.get(token, token) for line in lines for token in shlex.split(line)[3:]]
    return main(argv=argv) if lines else 0


def _fail_closed_findings(*, text: str) -> list[str]:
    """Every way the reader step, as written, could pass without its verdict."""
    steps = _reader_steps(block=_gate_block(text=text))
    step = steps[0] if steps else ""
    commands = [line.strip() for line in step.split("        run: |\n", 1)[-1].splitlines()]
    commands = [command for command in commands if command]
    findings = [
        ("an unreadable job list does not fail the step", _UNREADABLE_BRANCH not in step),
        ("the reader is not the step's last command", commands[-1:] != [_READER_LINE]),
        ("the step relaxes errexit", "set +e" in step or "set +o errexit" in step),
        ("the step overrides its shell", "\n        shell:" in step),
    ]
    return [finding for finding, present in findings if present]


def test_the_reader_step_fails_closed_as_committed() -> None:
    assert _fail_closed_findings(text=_CI_YML.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            'failing closed"\n            exit 1\n',
            'failing closed"\n            exit 0\n',
            ["an unreadable job list does not fail the step"],
        ),
        (
            f"          {_READER_LINE}\n",
            f"          set +e\n          {_READER_LINE}\n          true\n",
            ["the reader is not the step's last command", "the step relaxes errexit"],
        ),
        (
            f"          {_READER_LINE}\n",
            f"          {_READER_LINE} || true\n",
            ["the reader is not the step's last command"],
        ),
        (
            _READER_STEP_HEADER,
            _READER_STEP_HEADER + "        shell: bash {0}\n",
            ["the step overrides its shell"],
        ),
    ],
    ids=["unreadable-exit-0", "set-e-off-and-trailing-true", "or-true", "shell-override"],
)
def test_each_soft_fail_mutant_of_the_reader_step_is_caught(
    *, old: str, new: str, expected: list[str]
) -> None:
    committed = _CI_YML.read_text(encoding="utf-8")
    assert (committed.count(old), _fail_closed_findings(text=committed.replace(old, new))) == (
        1,
        expected,
    )


def test_the_outage_run_that_merged_now_fails_the_gate_as_wired() -> None:
    verdicts = (
        _replayed_verdict(jobs=_FIXTURES / "run-42673814418-jobs.jsonl"),
        _replayed_verdict(jobs=_FIXTURES / "run-42674666440-jobs.jsonl"),
        _replayed_verdict(jobs=_FIXTURES / "run-42632611055-jobs.jsonl"),
    )
    assert verdicts == (1, 0, 0)


def test_the_reader_step_reads_this_runs_jobs_and_cannot_be_skipped() -> None:
    steps = _reader_steps(block=_gate_block())
    step = steps[0] if steps else ""
    facts = (
        len(steps),
        _API_READ in step,
        _JOBS_PLACEHOLDER in step,
        "--workflow .github/workflows/ci.yml --gate-job ci-green" in step,
        "\n        if:" in step,
        "continue-on-error" in step,
    )
    assert facts == (1, True, True, True, False, False)


def test_the_gate_may_read_the_actions_api_and_checks_out_before_the_reader() -> None:
    block = _gate_block()
    checkout = [i for i, step in enumerate(_steps(block=block)) if "actions/checkout@" in step]
    reader = [i for i, step in enumerate(_steps(block=block)) if _READER in step]
    facts = (
        "    permissions:\n" in block,
        "      actions: read\n" in block,
        bool(checkout) and bool(reader) and checkout[0] < reader[0],
    )
    assert facts == (True, True, True)


def test_the_needs_result_step_is_still_present_unchanged() -> None:
    assert _NEEDS_RESULT_STEP in _gate_block()
