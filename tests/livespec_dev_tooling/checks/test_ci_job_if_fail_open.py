"""The job-level `if:` read must not fail open (livespec-dev-tooling-yzr6ad).

Coordinator re-grade fixes on livespec-dev-tooling#4468: a job key carrying a
trailing YAML comment must still start its own job, so its condition is not
merged into the previous job's; a backslash-escaped quote inside a
double-quoted `if:` must not end the string early, so a later token is still
read; and a YAML alias value cannot be read, so it counts as event-bound.
"""

from __future__ import annotations

from livespec_dev_tooling.checks._ci_job_if import event_bound_jobs
from livespec_dev_tooling.checks._ci_matrix_parse import job_blocks


def test_a_job_key_with_a_trailing_comment_starts_its_own_job():
    source = (
        "on: [push, pull_request]\n"
        "jobs:\n"
        "  first:\n"
        "    runs-on: ubuntu-latest\n"
        "    if: ${{ needs.q.result == 'success' }}\n"
        "    steps:\n"
        "      - run: just check-x\n"
        "  second: # this job runs only on push\n"
        "    runs-on: ubuntu-latest\n"
        "    if: github.event_name == 'push'\n"
        "    steps:\n"
        "      - run: just check-y\n"
    )
    assert [name for name, _ in job_blocks(source=source)] == ["first", "second"]
    assert event_bound_jobs(source=source) == frozenset({"second"})


def test_an_escaped_quote_does_not_end_a_double_quoted_condition():
    source = (
        "on: push\n"
        "jobs:\n"
        "  gated:\n"
        "    runs-on: ubuntu-latest\n"
        '    if: "x == \\" #\\" || github.ref == \'refs/heads/master\'"\n'
        "    steps:\n"
        "      - run: just check-x\n"
    )
    assert event_bound_jobs(source=source) == frozenset({"gated"})


def test_an_alias_condition_is_treated_as_event_bound():
    source = (
        "on: push\n"
        "jobs:\n"
        "  gated:\n"
        "    runs-on: ubuntu-latest\n"
        "    if: *release-only\n"
        "    steps:\n"
        "      - run: just check-x\n"
    )
    assert event_bound_jobs(source=source) == frozenset({"gated"})
