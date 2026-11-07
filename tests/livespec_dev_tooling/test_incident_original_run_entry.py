"""The operator entrance prints one schema-1 reply per collection or correction."""

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_original_run_entry as entry
from livespec_dev_tooling._incident_run_types import ExpectedJob
from livespec_dev_tooling.incident_run_forge import ForgeRunReader
from tests.livespec_dev_tooling import test_incident_original_run_flows as flows
from tests.livespec_dev_tooling.test_incident_original_run_flows import REPOSITORY, World

# The shared reverted-incident fixture: a real repository, controller state and ports.
world = flows.world


def common(world: World) -> list[str]:
    return ["--state-dir", str(world.state), "--repository", REPOSITORY, "--repo", str(world.repo)]


def graph_file(world: World, rows: object) -> str:
    path = world.state.parent / "graph.json"
    path.write_text(json.dumps(rows))
    return str(path)


GRAPH_ROWS = [
    {"name": "lint"},
    {"name": "test", "needs": []},
    {"name": "coverage", "needs": ["test"]},
    {"name": "slow-leg"},
    {"name": "late-leg"},
    {"name": "other"},
]


def invoke(world: World, capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, Any]:
    code = entry.main(argv=list(argv), ports=world.ports())
    return code, json.loads(capsys.readouterr().out)


def test_collect_then_propose_through_the_entrance(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    graph = graph_file(world, GRAPH_ROWS)
    gather = ["collect", *common(world), "--revert-sha", world.shas["revert"]]
    code, collected = invoke(world, capsys, *gather, "--expected-graph", graph)
    again, repeat = invoke(world, capsys, *gather, "--expected-graph", graph)
    digest = collected["evidence_digest"]
    correct = ["propose-correction", *common(world), "--evidence-digest", digest]
    correct += [
        "--target-ref",
        "refs/heads/a2",
        "--current-generation",
        "3",
        "--base-ref",
        "master",
    ]
    correct += ["--current-attempt", "recovery-1", "--current-owner", "incident-principal"]
    relanded, reland = invoke(world, capsys, *correct, "--next-head-sha", world.shas["reland"])
    proposed, repair = invoke(
        world, capsys, *correct, "--next-head-sha", world.shas["repair"], "--resolved", "test=r1"
    )
    assert (code, again, repeat["evidence_digest"]) == (0, 0, digest)
    assert collected["status"] == "collected"
    assert collected["terminal"] is True
    assert collected["jobs"][-2:] == [
        ["late-leg", "failed", "failure"],
        ["other", "never-created", None],
    ]
    assert collected["debts"] == ["coverage", "slow-leg", "other"]
    assert (relanded, reland["code"]) == (78, "incident-original-run-invalid")
    assert (proposed, repair) == (0, {"schema": 1, "status": "proposed", "receipt": "correction-2"})
    assert len(world.comments) == 1


def test_entrance_refuses_an_unreadable_graph_or_resolution_by_name(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    gather = ["collect", *common(world), "--revert-sha", world.shas["revert"]]
    missing, unreadable = invoke(world, capsys, *gather, "--expected-graph", str(world.repo / "no"))
    bad, malformed = invoke(world, capsys, *gather, "--expected-graph", graph_file(world, {}))
    correct = ["propose-correction", *common(world), "--evidence-digest", "d"]
    correct += ["--target-ref", "r", "--current-generation", "3"]
    correct += ["--current-attempt", "recovery-1", "--current-owner", "incident-principal"]
    correct += ["--next-head-sha", world.shas["repair"]]
    loose, resolution = invoke(world, capsys, *correct, "--resolved", "test")
    absent, unretained = invoke(world, capsys, *correct)
    short, omitted = invoke(
        world, capsys, *gather, "--expected-graph", graph_file(world, GRAPH_ROWS[:3])
    )
    assert (missing, unreadable["code"]) == (78, "incident-original-run-graph-invalid")
    assert (bad, malformed["code"]) == (78, "incident-original-run-graph-invalid")
    assert (loose, resolution["code"]) == (78, "incident-original-run-invalid-request")
    assert (absent, unretained["code"]) == (78, "incident-original-run-evidence-missing")
    assert (short, omitted["status"]) == (78, "refused")
    assert omitted["detail"] == "expected graph omits late-leg"


@pytest.mark.parametrize(
    "rows",
    [{"name": "x"}, [{"name": "x", "extra": 1}], [{"name": 1}], [{"name": "x", "needs": "y"}], [3]],
)
def test_graph_rows_must_name_jobs_and_their_needs(rows: object) -> None:
    with pytest.raises(TypeError):
        _ = entry.parse_graph(value=rows)


def test_graph_keeps_declared_needs() -> None:
    assert entry.parse_graph(value=GRAPH_ROWS[1:3]) == (
        ExpectedJob(name="test"),
        ExpectedJob(name="coverage", needs=("test",)),
    )


def completed(stdout: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout)


def test_registered_ports_reach_git_bd_and_the_registered_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replies = [
        completed(b"tree\n"),
        completed(b"[]"),
        completed(
            json.dumps(
                {
                    "schema": 1,
                    "status": "verified",
                    "normal_factory_proof": False,
                    "result": {"attempt": {}},
                }
            ).encode()
        ),
        completed(
            json.dumps(
                {"schema": 1, "status": "refused", "normal_factory_proof": False, "result": {}}
            ).encode()
        ),
        completed(
            json.dumps(
                {"schema": 1, "status": "verified", "normal_factory_proof": False, "result": []}
            ).encode()
        ),
    ]
    spawn = Mock(side_effect=replies)
    monkeypatch.setattr(entry.subprocess, "run", spawn)
    monkeypatch.setattr(entry, "registered_plugin_root", Mock(return_value=tmp_path / "plugin"))
    ports = entry.registered_ports(repo=tmp_path)
    tree = ports.git(["rev-parse", "HEAD^{tree}"], b"in")
    listing = ports.canonical.ledger(["comments", "incident-1", "--json"])
    reading = ports.canonical.authority(
        "read-history", {"item": "incident-1"}, {"correction-json": "{}"}
    )
    for _ in range(2):
        with pytest.raises(ValueError, match="invalid reply"):
            _ = ports.canonical.authority("correct-attempt", {}, {})
    argv = [call.args[0] for call in spawn.call_args_list]
    assert (tree, listing, reading) == (b"tree\n", "[]", {"attempt": {}})
    assert argv[0] == ["git", "rev-parse", "HEAD^{tree}"]
    assert spawn.call_args_list[0].kwargs["input"] == b"in"
    assert argv[1] == [
        "/usr/local/bin/with-livespec-env.sh",
        "--",
        "bd",
        "comments",
        "incident-1",
        "--json",
    ]
    assert argv[2][2:] == [
        "python3",
        str(tmp_path / "plugin/scripts/bin/incident_authority.py"),
        "read-history",
        "--repo",
        str(tmp_path),
        "--item",
        "incident-1",
        "--correction-json",
        "{}",
    ]
    assert isinstance(ports.read, ForgeRunReader)


def test_main_reads_process_arguments_and_binds_registered_ports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["incident-original-run", "propose-correction", "--state-dir", str(tmp_path)]
    argv += ["--repository", REPOSITORY, "--repo", str(tmp_path), "--evidence-digest", "d"]
    argv += ["--target-ref", "r", "--current-generation", "3", "--next-head-sha", "h"]
    argv += ["--current-attempt", "recovery-1", "--current-owner", "incident-principal"]
    monkeypatch.setattr(entry.sys, "argv", argv)
    bind = Mock(wraps=entry.registered_ports)
    monkeypatch.setattr(entry, "registered_ports", bind)
    assert entry.main() == 78
    assert json.loads(capsys.readouterr().out)["code"] == "incident-original-run-unregistered"
    assert bind.call_args.kwargs == {"repo": tmp_path}
