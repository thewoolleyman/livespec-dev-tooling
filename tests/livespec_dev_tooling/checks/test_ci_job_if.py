"""Which ci.yml jobs carry a job-level `if:` that names the triggering event or ref.

Coordinator grade fix 3 on livespec-dev-tooling#4468 (livespec-dev-tooling-yzr6ad):
the token read must see block-scalar and multi-line expressions,
`github.ref_type` / `github.ref_protected`, and the bracket form, and must not
treat a trailing YAML comment as part of the condition.
"""

from __future__ import annotations

import pytest

from livespec_dev_tooling.checks._ci_job_if import event_bound_jobs


def _workflow(*, condition: str) -> str:
    return (
        "on: [push, pull_request]\n"
        "jobs:\n"
        "  gated:\n"
        "    runs-on: ubuntu-latest\n"
        f"{condition}"
        "    steps:\n"
        "      - run: just check-x\n"
        "  plain:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: just check-y\n"
    )


@pytest.mark.parametrize(
    ("label", "condition"),
    [
        ("event name", "    if: github.event_name == 'pull_request'\n"),
        ("ref type", "    if: ${{ github.ref_type == 'tag' }}\n"),
        ("ref protected", "    if: ${{ github.ref_protected }}\n"),
        ("bracket event name", "    if: ${{ github['event_name'] == 'push' }}\n"),
        ("bracket ref", "    if: ${{ github[\"ref\"] == 'refs/heads/master' }}\n"),
        ("folded block scalar", "    if: >-\n      github.event_name == 'push'\n"),
        ("literal block scalar", "    if: |\n      github.head_ref != ''\n"),
        (
            "multi-line plain expression",
            "    if: ${{ !cancelled() &&\n      github.ref == 'refs/heads/master' }}\n",
        ),
    ],
)
def test_a_job_level_if_naming_the_event_or_ref_is_event_bound(*, label: str, condition: str):
    assert event_bound_jobs(source=_workflow(condition=condition)) == frozenset({"gated"}), label


@pytest.mark.parametrize(
    ("label", "condition"),
    [
        ("not cancelled", "    if: ${{ !cancelled() }}\n"),
        ("trailing comment", "    if: ${{ !cancelled() }}  # github.ref is ignored here\n"),
        ("needs result", "    if: ${{ needs.setup.result == 'success' }}\n"),
        ("repository is not ref", "    if: ${{ github.repository == 'o/r' }}\n"),
    ],
)
def test_a_job_level_if_without_an_event_or_ref_token_is_not_event_bound(
    *, label: str, condition: str
):
    assert event_bound_jobs(source=_workflow(condition=condition)) == frozenset(), label


def test_a_step_level_if_does_not_make_the_job_event_bound():
    source = (
        "on: push\n"
        "jobs:\n"
        "  gated:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - if: github.event_name == 'push'\n"
        "        run: just check-x\n"
    )
    assert event_bound_jobs(source=source) == frozenset()


def test_a_workflow_without_jobs_has_no_event_bound_job():
    assert event_bound_jobs(source="on: push\n") == frozenset()


def test_a_job_level_if_on_the_last_line_of_the_workflow_is_read():
    source = (
        "on: push\n"
        "jobs:\n"
        "  gated:\n"
        "    runs-on: ubuntu-latest\n"
        "    if: github.ref == 'refs/heads/master'\n"
    )
    assert event_bound_jobs(source=source) == frozenset({"gated"})


def test_a_quoted_hash_is_part_of_the_condition_not_a_comment():
    source = _workflow(condition="    if: ${{ github.head_ref == 'a #b' }}\n")
    assert event_bound_jobs(source=source) == frozenset({"gated"})
