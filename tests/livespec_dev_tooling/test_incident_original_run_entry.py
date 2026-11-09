"""The operator entrance prints one schema-1 reply per collection or correction."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
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


@pytest.fixture(autouse=True)
def installation(world: World, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The verified installation, whose file checks need the provisioned host."""
    settings = SimpleNamespace(
        repository=REPOSITORY,
        repo=world.repo,
        state=world.state,
        reader=("/opt/venv/bin/python", "/opt/reader/incident_authority.py"),
        config=world.state.parent / "controller.json",
    )
    monkeypatch.setattr(entry.ControllerInstallation, "load", Mock(return_value=settings))
    monkeypatch.setattr(entry.os, "umask", Mock(return_value=0o022))
    return settings


def common(world: World) -> list[str]:
    return ["--config", str(world.state.parent / "controller.json")]


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


def authority_reply(**fields: object) -> subprocess.CompletedProcess[str]:
    reply = {"schema": 1, "authorizes_current_effects": False, "normal_factory_proof": False}
    body = json.dumps(reply | fields)
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=body, stderr="")


def test_installed_ports_reach_git_bd_and_the_manifest_reader(
    monkeypatch: pytest.MonkeyPatch, installation: SimpleNamespace, tmp_path: Path
) -> None:
    replies = [
        completed(b"tree\n"),
        completed(b"[]"),
        authority_reply(status="verified", result={"attempt": {}}),
        authority_reply(status="refused", result={}),
        authority_reply(status="verified", result=[]),
    ]
    spawn = Mock(side_effect=replies)
    monkeypatch.setattr(subprocess, "run", spawn)
    monkeypatch.setenv("PYTHONPATH", "/candidate")
    installation.config = tmp_path / "controller.json"
    (tmp_path / "reader.env").write_text("BEADS_DOLT_PASSWORD=tenant=secret\n\n")
    ports = entry.installed_ports(installation=installation)
    tree = ports.git(["rev-parse", "HEAD^{tree}"], b"in")
    listing = ports.canonical.ledger(["comments", "incident-1", "--json"])
    reading = ports.canonical.authority(
        "read-history", {"item": "incident-1"}, {"correction-json": "{}"}
    )
    for _ in range(2):
        with pytest.raises(ValueError, match="invalid reply"):
            _ = ports.canonical.authority("correct-attempt", {}, {})
    calls = spawn.call_args_list
    argv = [call.args[0] for call in calls]
    assert (tree, listing, reading) == (b"tree\n", "[]", {"attempt": {}})
    assert argv[0] == ["git", "rev-parse", "HEAD^{tree}"]
    assert calls[0].kwargs["input"] == b"in"
    assert argv[1] == ["bd", "comments", "incident-1", "--json"]
    assert argv[2] == [
        "/opt/venv/bin/python",
        "/opt/reader/incident_authority.py",
        "read-history",
        "--repo",
        str(installation.repo),
        "--item",
        "incident-1",
        "--correction-json",
        "{}",
    ]
    assert all(call.kwargs["cwd"] == installation.repo for call in calls)
    assert set(calls[0].kwargs["env"]) == {"PATH", "HOME"}
    for call in calls[1:]:
        assert set(call.kwargs["env"]) == {"PATH", "HOME", "BEADS_DOLT_PASSWORD"}
        assert call.kwargs["env"]["BEADS_DOLT_PASSWORD"] == "tenant=secret"
    assert "/usr/local/bin" in calls[1].kwargs["env"]["PATH"].split(":")
    assert isinstance(ports.read, ForgeRunReader)


def _missing_argv(*, config: Path) -> list[str]:
    argv = ["propose-correction", "--config", str(config), "--evidence-digest", "d"]
    argv += ["--target-ref", "r", "--current-generation", "3", "--next-head-sha", "h"]
    return [*argv, "--current-attempt", "recovery-1", "--current-owner", "incident-principal"]


def test_main_binds_installed_ports_and_refreshes_the_reference_clone(
    monkeypatch: pytest.MonkeyPatch,
    installation: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installation.config = tmp_path / "controller.json"
    (tmp_path / "reader.env").write_text("BEADS_DOLT_PASSWORD=x\n")
    argv = ["incident-original-run", *_missing_argv(config=installation.config)]
    monkeypatch.setattr(entry.sys, "argv", argv)
    sequence: list[str] = []

    def fetch_spy(*_args: Any, **_kwargs: Any) -> None:
        sequence.append("fetch")
        raise subprocess.TimeoutExpired("git", 120)

    fetch = Mock(side_effect=fetch_spy)
    monkeypatch.setattr(subprocess, "run", fetch)
    propose = entry.propose

    def propose_spy(**kwargs: Any) -> Any:
        sequence.append("propose")
        return propose(**kwargs)

    monkeypatch.setattr(entry, "propose", propose_spy)
    assert entry.main() == 78
    assert json.loads(capsys.readouterr().out)["code"] == "incident-original-run-evidence-missing"
    assert fetch.call_args.args[0][:2] == ["git", "fetch"]
    # The reference clone is refreshed before the action reads git.
    assert sequence.index("fetch") < sequence.index("propose")
    entry.os.umask.assert_called_once_with(0o077)


def test_main_refuses_by_name_without_an_installation_or_its_credential(
    monkeypatch: pytest.MonkeyPatch,
    installation: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installation.config = tmp_path / "controller.json"
    argv = _missing_argv(config=installation.config)
    assert entry.main(argv=argv) == 78
    missing = json.loads(capsys.readouterr().out)
    monkeypatch.setattr(entry.ControllerInstallation, "load", Mock(return_value=None))
    assert entry.main(argv=argv) == 78
    unloaded = json.loads(capsys.readouterr().out)
    code = "incident-original-run-installation-unavailable"
    assert missing["code"] == unloaded["code"] == code


def test_installed_ports_pass_only_the_canonical_credential_from_reader_env(
    monkeypatch: pytest.MonkeyPatch, installation: SimpleNamespace, tmp_path: Path
) -> None:
    spawn = Mock(side_effect=[completed(b"tree\n"), completed(b"[]"), completed(b"[]")])
    monkeypatch.setattr(subprocess, "run", spawn)
    installation.config = tmp_path / "controller.json"
    lines = ["PATH=/tmp/evil", "HOME=/tmp/evil", "PYTHONPATH=/overrides", "GIT_DIR=/x"]
    lines.insert(2, "BEADS_DOLT_PASSWORD=tenant-secret")
    (tmp_path / "reader.env").write_text("\n".join(lines) + "\n")
    ports = entry.installed_ports(installation=installation)
    _ = ports.git(["rev-parse", "HEAD"], b"")
    _ = ports.canonical.ledger(["comments", "incident-1"])
    _ = ports.canonical.ledger(["show", "incident-1"])
    plain = spawn.call_args_list[0].kwargs["env"]
    for call in spawn.call_args_list[1:]:
        env = call.kwargs["env"]
        assert set(env) == {"PATH", "HOME", "BEADS_DOLT_PASSWORD"}
        assert (env["PATH"], env["HOME"]) == (plain["PATH"], plain["HOME"])
        assert env["BEADS_DOLT_PASSWORD"] == "tenant-secret"


def test_main_refuses_by_name_when_reader_env_carries_no_credential(
    monkeypatch: pytest.MonkeyPatch,
    installation: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installation.config = tmp_path / "controller.json"
    (tmp_path / "reader.env").write_text("PYTHONPATH=/overrides\n")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("git", 1)))
    assert entry.main(argv=_missing_argv(config=installation.config)) == 78
    code = "incident-original-run-installation-unavailable"
    assert json.loads(capsys.readouterr().out)["code"] == code
