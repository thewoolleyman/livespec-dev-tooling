"""Unit tests for the retained cluster record behind reusable pre-push evidence."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandNotRun,
    GateCommandOutcome,
    GateCommandResult,
)

__all__: list[str] = []


def _runner(*, replies: list[object]):
    """Return a runner that yields each canned invocation outcome in order."""

    def run(
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = argv, cwd, stdin, stream
        reply = replies.pop(0)
        if reply == "not-run":
            return Failure(GateCommandNotRun(argv=("with-gates-kubeconfig",), detail="missing"))
        if isinstance(reply, int):
            return Success(GateCommandResult(returncode=reply, stdout="", stderr="refused"))
        return Success(GateCommandResult(returncode=0, stdout=str(reply), stderr=""))

    return run


def _job(
    *, tree_hash: str, conditions: list[dict[str, str]] | None = None, tree: str | None = None
) -> str:
    """Render the retained Job response with independently controllable confirmation facts."""
    return json.dumps(
        {
            "metadata": {"labels": {"livespec.gate/tree-hash": tree or tree_hash}},
            "status": {"conditions": conditions or [{"type": "Complete", "status": "True"}]},
        }
    )


@pytest.mark.parametrize(
    ("replies", "expected"),
    [
        (["not-run"], False),
        (["not json"], False),
        (["job", json.dumps({"items": []})], False),
        (
            ["job", json.dumps({"items": [{"metadata": {"name": "pod"}}]}), 1],
            False,
        ),
        (
            [
                "job",
                json.dumps({"items": [{"metadata": {"name": "pod"}}]}),
                'LIVESPEC_GATE_MEMBERS {"check-alpha": "passed", "check-beta": "passed"}\n',
            ],
            True,
        ),
        (
            [
                "failed-job",
                json.dumps({"items": [{"metadata": {"name": "pod"}}]}),
                'LIVESPEC_GATE_MEMBERS {"check-alpha": "passed", "check-beta": "passed"}\n',
            ],
            False,
        ),
        (
            [
                "wrong-tree",
                json.dumps({"items": [{"metadata": {"name": "pod"}}]}),
                'LIVESPEC_GATE_MEMBERS {"check-alpha": "passed", "check-beta": "passed"}\n',
            ],
            False,
        ),
        (
            [
                "job",
                json.dumps({"items": [{"metadata": {"name": "pod"}}]}),
                'LIVESPEC_GATE_MEMBERS {"check-alpha": "failed"}\n',
            ],
            False,
        ),
    ],
)
def test_cluster_record_requires_a_complete_matching_job(
    *, tmp_path: Path, replies: list[object], expected: bool
) -> None:
    """Missing and contradictory records cannot stand in for a fresh pre-push Job."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "_pre_push_cluster_record.py"
    assert module_path.is_file()
    module = importlib.import_module("livespec_dev_tooling._pre_push_cluster_record")
    evidence = module.Evidence(
        tree_hash="a" * 40,
        gate_job="gate-widget-abcde",
        members_passed=("check-alpha", "check-beta"),
    )
    expanded_replies = [
        _job(tree_hash=evidence.tree_hash)
        if reply == "job"
        else _job(
            tree_hash=evidence.tree_hash,
            conditions=[
                {"type": "Complete", "status": "False"},
                {"type": "Failed", "status": "True"},
            ],
        )
        if reply == "failed-job"
        else _job(tree_hash=evidence.tree_hash, tree="b" * 40)
        if reply == "wrong-tree"
        else reply
        for reply in replies
    ]
    assert (
        module.cluster_record_confirms(
            evidence=evidence, cwd=tmp_path, runner=_runner(replies=expanded_replies)
        )
        is expected
    )
