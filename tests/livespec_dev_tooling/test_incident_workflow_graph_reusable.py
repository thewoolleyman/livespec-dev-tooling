"""A same-repository, SHA-pinned reusable-workflow job joins the original run's graph.

livespec-dev-tooling-jw4a4v: the publisher job ci.yml calls at a master commit SHA
(livespec-dev-tooling-bqnzcm.4) must not make original-run collection unsupported.
Every other reusable-workflow call still refuses by name.
"""

from unittest.mock import Mock

import pytest

from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_original_run_declared import declared_graph
from livespec_dev_tooling._incident_run_types import EvidenceRefusal, ExpectedJob
from livespec_dev_tooling.incident_workflow_graph import derive_graph

_REPOSITORY = "livespec-ai/livespec-dev-tooling"
_SHA = "8e9ed73ba03718d6060db6f9ebe725c4a6154922"
_PATH = ".github/workflows/reusable-incident-ci-publish.yml"

_PINNED = f"livespec-ai/livespec-dev-tooling/{_PATH}@{_SHA}"

CALLER = f"""\
jobs:
  incident-ci:
    runs-on: x
  incident-ci-publish:
    name: incident-ci-publish
    needs: [incident-ci]
    uses: {_PINNED}
    with:
      release: v1
  after:
    needs: incident-ci-publish
""".encode()

CALLED = b"""\
on:
  workflow_call:
jobs:
  publish:
    name: publish
    runs-on: x
  confirm:
    needs: publish
"""


def _caller(*, uses: str) -> bytes:
    return b"jobs:\n  call:\n    uses: " + uses.encode() + b"\n"


def test_a_same_repository_sha_pinned_call_expands_into_the_called_jobs() -> None:
    reader = Mock(return_value=CALLED)
    graph = derive_graph(source=CALLER, repository=_REPOSITORY, read_called=reader)
    expected = (
        ExpectedJob(name="incident-ci", needs=()),
        ExpectedJob(name="incident-ci-publish / publish", needs=("incident-ci",)),
        ExpectedJob(
            name="incident-ci-publish / confirm",
            needs=("incident-ci", "incident-ci-publish / publish"),
        ),
        ExpectedJob(
            name="after",
            needs=("incident-ci-publish / publish", "incident-ci-publish / confirm"),
        ),
    )
    facts = [graph == expected, reader.call_args.args == (_PATH, _SHA), reader.call_count == 1]
    assert all(facts), graph


def test_an_unnamed_caller_prefixes_the_called_jobs_with_its_job_id() -> None:
    reader = Mock(return_value=b"jobs:\n  publish:\n    runs-on: x\n")
    uses = f"LIVESPEC-AI/livespec-dev-tooling/{_PATH}@{_SHA}"
    graph = derive_graph(source=_caller(uses=uses), repository=_REPOSITORY, read_called=reader)
    assert graph == (ExpectedJob(name="call / publish", needs=()),)


REFUSED_CALLS = {
    "another repository": f"livespec-ai/livespec/{_PATH}@{_SHA}",
    "a branch ref": f"livespec-ai/livespec-dev-tooling/{_PATH}@master",
    "a tag ref": f"livespec-ai/livespec-dev-tooling/{_PATH}@v1.213.0",
    "a short SHA": f"livespec-ai/livespec-dev-tooling/{_PATH}@{_SHA[:12]}",
    "a local path": f"./{_PATH}",
}


@pytest.mark.parametrize("label", sorted(REFUSED_CALLS))
def test_any_other_reusable_workflow_call_refuses_naming_the_job(label: str) -> None:
    reader = Mock(return_value=CALLED)
    refusal = derive_graph(
        source=_caller(uses=REFUSED_CALLS[label]), repository=_REPOSITORY, read_called=reader
    )
    facts = [
        isinstance(refusal, EvidenceRefusal),
        getattr(refusal, "code", "") == "incident-original-run-graph-unsupported",
        getattr(refusal, "detail", "").startswith("call job calls a reusable workflow"),
        reader.call_count == 0,
    ]
    assert all(facts), (label, refusal)


def test_a_pinned_call_with_no_reader_refuses_naming_the_job() -> None:
    uses = _PINNED
    refusal = derive_graph(source=_caller(uses=uses), repository=_REPOSITORY)
    assert refusal == EvidenceRefusal(
        code="incident-original-run-graph-unsupported",
        detail="call job calls a reusable workflow and no reader was given",
    )


def test_a_called_workflow_that_itself_calls_one_refuses_without_recursing() -> None:
    nested = b"jobs:\n  inner:\n    uses: ./" + _PATH.encode() + b"\n  plain:\n    runs-on: x\n"
    reader = Mock(return_value=nested)
    uses = _PINNED
    refusal = derive_graph(source=_caller(uses=uses), repository=_REPOSITORY, read_called=reader)
    facts = [
        refusal
        == EvidenceRefusal(
            code="incident-original-run-graph-unsupported",
            detail=(
                "inner in the called workflow calls a reusable workflow; "
                "nested calls are not resolved"
            ),
        ),
        reader.call_count == 1,
    ]
    assert all(facts), refusal


def test_a_called_workflow_that_cannot_be_read_refuses_naming_path_and_sha() -> None:
    reader = Mock(side_effect=OSError("fatal: path does not exist"))
    uses = _PINNED
    refusal = derive_graph(source=_caller(uses=uses), repository=_REPOSITORY, read_called=reader)
    assert refusal == EvidenceRefusal(
        code="incident-original-run-graph-unsupported",
        detail=f"{_PATH}@{_SHA} called workflow cannot be read",
    )


def test_a_reusable_call_from_a_matrix_job_refuses() -> None:
    source = (
        "jobs:\n  call:\n    strategy:\n      matrix:\n        os: [x]\n" f"    uses: {_PINNED}\n"
    ).encode()
    refusal = derive_graph(source=source, repository=_REPOSITORY, read_called=Mock())
    assert refusal == EvidenceRefusal(
        code="incident-original-run-graph-unsupported",
        detail="call job calls a reusable workflow from a matrix",
    )


def test_the_declared_graph_reads_the_called_workflow_at_its_pin_from_the_clone() -> None:
    merge = "a" * 40
    registration = ObserverRegistration(
        repository=_REPOSITORY,
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="repair-operation-1",
        generation=1,
        owner="controller",
        phase="repair",
        head_sha=merge,
        run_id=91,
        required_jobs=("incident-ci-publish / publish",),
        controller_release="v1.213.0",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"receipt",
    )
    git = Mock(side_effect=[b"", CALLER, CALLED])
    declared = declared_graph(
        registration=registration,
        revert_sha="d" * 40,
        workflow_path=".github/workflows/ci.yml",
        supplied=None,
        git=git,
    )
    names = [job.name for job in declared[1]] if isinstance(declared, tuple) else declared
    reads = [call.args[0] for call in git.call_args_list]
    facts = [
        names
        == [
            "incident-ci",
            "incident-ci-publish / publish",
            "incident-ci-publish / confirm",
            "after",
        ],
        ["cat-file", "blob", f"{_SHA}:{_PATH}"] in reads,
    ]
    assert all(facts), (names, reads)
