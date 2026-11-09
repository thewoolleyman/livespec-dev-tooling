"""The expected job graph of an original run is derived from workflow source, never typed in."""

from pathlib import Path

import pytest

from livespec_dev_tooling._incident_run_types import EvidenceRefusal, ExpectedJob
from livespec_dev_tooling.incident_workflow_graph import derive_graph

PLAIN = b"""\
name: CI
on:
  push:
# a comment between sections
jobs:
  lint:
    runs-on: ubuntu-latest   # trailing comment
    steps:
      - run: |
          needs: [ghost]
          jobs:
  test:
    needs: lint
    runs-on: ubuntu-latest
  coverage:
    needs: [lint, "test"]
  gate:
    name: 'All green'
    needs:
      - lint
      - coverage
  dashed:
    needs:
    - gate
"""

MATRIX = b"""\
jobs:
  check:
    name: ${{ matrix.target }}
    strategy:
      fail-fast: false
      matrix:
        target:
          # first leg
          - check-types   # trailing
          - "check-lint"
  pair:
    strategy:
      matrix:
        os: [linux, mac]
        py: ['3.10', 3.12]
  batch:
    name: batch-${{ matrix.os }}-${{ matrix.os }}
    needs: [check, pair]
    strategy:
      matrix:
        os: [linux]
  single:
    strategy:
      fail-fast: false
  final:
    needs: [batch, single]
"""


def names(graph: object) -> list[str]:
    assert isinstance(graph, tuple), graph
    return [job.name for job in graph]


def test_plain_jobs_keep_declaration_order_and_every_form_of_needs() -> None:
    graph = derive_graph(source=PLAIN)
    assert graph == (
        ExpectedJob(name="lint"),
        ExpectedJob(name="test", needs=("lint",)),
        ExpectedJob(name="coverage", needs=("lint", "test")),
        ExpectedJob(name="All green", needs=("lint", "coverage")),
        ExpectedJob(name="dashed", needs=("All green",)),
    )


def test_matrix_legs_are_expanded_with_their_names_and_dependents_need_every_leg() -> None:
    graph = derive_graph(source=MATRIX)
    assert names(graph) == [
        "check-types",
        "check-lint",
        "pair (linux, 3.10)",
        "pair (linux, 3.12)",
        "pair (mac, 3.10)",
        "pair (mac, 3.12)",
        "batch-linux-linux",
        "single",
        "final",
    ]
    assert isinstance(graph, tuple)
    by_name = {job.name: job for job in graph}
    assert by_name["batch-linux-linux"].needs == (
        "check-types",
        "check-lint",
        "pair (linux, 3.10)",
        "pair (linux, 3.12)",
        "pair (mac, 3.10)",
        "pair (mac, 3.12)",
    )
    assert by_name["final"].needs == ("batch-linux-linux", "single")


def test_an_empty_jobs_mapping_declares_no_job() -> None:
    assert derive_graph(source=b"name: CI\njobs: {}\n") == ()


def test_the_repository_own_workflow_resolves_to_a_closed_graph() -> None:
    source = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_bytes()
    graph = derive_graph(source=source)
    assert isinstance(graph, tuple)
    declared = {job.name for job in graph}
    assert {"check-types", "check-lint", "check-coverage", "incident-ci", "ci-green"} <= declared
    assert all(set(job.needs) <= declared for job in graph)
    assert next(job for job in graph if job.name == "check-coverage").needs == (
        "check-per-file-coverage",
        "incident-ci",
    )


UNSUPPORTED = {
    "no jobs section": b"name: CI\n",
    "inline jobs": b"jobs: {a: 1}\n",
    "not utf-8": b"jobs:\n  \xff:\n",
    "reusable workflow": b"jobs:\n  a:\n    uses: ./.github/workflows/x.yml\n",
    "matrix include": b"jobs:\n  a:\n    strategy:\n      matrix:\n        include:\n          - x: 1\n",
    "matrix exclude": b"jobs:\n  a:\n    strategy:\n      matrix:\n        os: [a]\n        exclude: []\n",
    "dynamic matrix": b"jobs:\n  a:\n    strategy:\n      matrix: ${{ fromJSON(x) }}\n",
    "dynamic dimension": b"jobs:\n  a:\n    strategy:\n      matrix:\n        os: ${{ x }}\n",
    "empty dimension": b"jobs:\n  a:\n    strategy:\n      matrix:\n        os: []\n",
    "mapping dimension": b"jobs:\n  a:\n    strategy:\n      matrix:\n        os:\n          - k: v\n",
    "unknown need": b"jobs:\n  a:\n    needs: ghost\n",
    "foreign expression in name": b"jobs:\n  a:\n    name: ${{ github.ref }}\n",
    "unknown matrix key in name": b"jobs:\n  a:\n    name: ${{ matrix.x }}\n",
    "duplicate names": b"jobs:\n  a:\n    name: same\n  b:\n    name: same\n",
    "open flow list": b"jobs:\n  a:\n    needs: [b,\n  b: {}\n",
    "stray item": b"jobs:\n  - a\n",
    "unkeyed job entry": b"jobs:\n  a:\n    needs: [a]\n    - b\n",
}


@pytest.mark.parametrize("label", sorted(UNSUPPORTED))
def test_a_workflow_it_cannot_resolve_refuses_instead_of_omitting_jobs(label: str) -> None:
    refusal = derive_graph(source=UNSUPPORTED[label])
    assert isinstance(refusal, EvidenceRefusal), label
    assert refusal.code == "incident-original-run-graph-unsupported"
    assert refusal.detail
