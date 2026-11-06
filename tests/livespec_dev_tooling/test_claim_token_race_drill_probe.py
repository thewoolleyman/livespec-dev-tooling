"""`ansible/files/claim_token_race_drill_probe.py` — one claim writer, its barrier and its read-back.

Orchestrator work item bd-ib-4eeefv (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm). The probe is the writer
`ansible/claim-token-race-drill.yml` runs on each host. These tests load the
committed script and drive each verb in-process against the fixture plugin
(`fixtures/claim_token_race_drill_plugin`), whose file-locked store gives the
released package's verbs real compare-and-swap semantics, so a loser here loses
the way a loser loses on the server: its close reason is not the one read back.
`test_claim_token_race_drill_playbook.py` runs the same probe as two processes
through the committed play.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from shutil import copytree
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "ansible" / "files" / "claim_token_race_drill_probe.py"
_FIXTURE_PLUGIN = Path(__file__).resolve().parent / "fixtures" / "claim_token_race_drill_plugin"
_SCRIPTS_ROOT = _FIXTURE_PLUGIN / ".claude-plugin" / "scripts"
_CREDENTIAL_ENV = "BEADS_DOLT_PASSWORD"
_CONTROL = "claim-token-race-drill/control-node"
_REMOTE = "claim-token-race-drill/target"


def _load() -> ModuleType:
    assert _SCRIPT.is_file(), f"{_SCRIPT.relative_to(_REPO_ROOT)} must exist"
    name = "claim_token_race_drill_probe_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


probe = _load()
ledger = sys.modules["claim_token_race_drill_ledger"]
barrier = sys.modules["claim_token_race_drill_barrier"]
plugin = probe.load_plugin(scripts_root=_SCRIPTS_ROOT)


@pytest.fixture
def clone(*, tmp_path: Path) -> Path:
    """A clone of the fixture plugin whose store lives under this test's tmp_path."""
    repo = tmp_path / "plugin"
    copytree(_FIXTURE_PLUGIN, repo)
    (repo / ".beads" / "fake-store-path").write_text(f"{tmp_path / 'store.json'}\n")
    return repo


@pytest.fixture
def client(*, clone: Path) -> Any:
    return plugin.make_client(
        config=probe.store_config(plugin=plugin, repo_root=clone, bd_path="bd")
    )


def _create(*, client: Any) -> dict[str, Any]:
    args = argparse.Namespace(title="probe", description="drill")
    return probe.run_create(args=args, plugin=plugin, client=client, prefix="bd-ib")


def _writer_args(
    *, tmp_path: Path, item: str, writer: str, case: str, point: str, go: str
) -> argparse.Namespace:
    case_dir = tmp_path / writer.rsplit("/", 1)[-1] / case
    case_dir.mkdir(parents=True)
    (case_dir / "go").write_text(go + "\n")
    return argparse.Namespace(
        item=item,
        writer=writer,
        case=case,
        host="host-under-test",
        run_id=f"drill-{case}-{writer.rsplit('/', 1)[-1]}",
        go_fifo=case_dir / "go",
        barrier_point=point,
        decided=case_dir / "decided.json",
        report=case_dir / "report.json",
    )


# --- loading the released package ---------------------------------------------


def test_the_plugin_is_loaded_from_the_clone_and_its_token_key_checked() -> None:
    assert plugin.change_claim is not None
    assert str(_SCRIPTS_ROOT) in sys.path
    probe.load_plugin(scripts_root=_SCRIPTS_ROOT)  # a second load inserts nothing twice
    assert sys.path.count(str(_SCRIPTS_ROOT)) == 1


def test_a_package_naming_another_token_key_is_refused(*, monkeypatch: pytest.MonkeyPatch) -> None:
    real = probe.importlib.import_module

    def mismatched(name: str) -> Any:
        if name.endswith("_store_claim_tokens"):
            return SimpleNamespace(CLAIM_TOKEN_METADATA_KEY="other", change_claim=None)  # noqa: S106 - a key name
        return real(name)

    monkeypatch.setattr(probe.importlib, "import_module", mismatched)
    with pytest.raises(RuntimeError, match="token key 'other'"):
        probe.load_plugin(scripts_root=_SCRIPTS_ROOT)


def test_the_store_config_is_read_from_the_clone_with_no_credential_wrapper(*, clone: Path) -> None:
    config = probe.store_config(plugin=plugin, repo_root=clone, bd_path="/x/bd")

    assert config.database == "livespec-orch-beads-fabro"
    assert config.prefix == "bd-ib"
    assert config.server_user == "livespec-orch-beads-fabro"
    assert (config.server_host, config.server_port) == ("127.0.0.1", 3307)
    assert config.credential_wrapper == ()
    assert config.repo_root == clone
    assert config.bd_path == "/x/bd"


def test_a_pointer_without_host_and_port_takes_the_loopback_defaults(*, tmp_path: Path) -> None:
    (tmp_path / ".beads").mkdir()
    (tmp_path / ".beads" / "config.yaml").write_text(
        "# comment: ignored\ndolt.server-user: u\ndolt.database: d\ndolt.prefix: p\n"
    )
    config = probe.store_config(plugin=plugin, repo_root=tmp_path, bd_path="bd")
    assert (config.server_host, config.server_port, config.tenant) == ("127.0.0.1", 3307, "d")


# --- the credential --------------------------------------------------------------


def test_the_credential_is_taken_from_the_fifo_into_the_process_environment(
    *, tmp_path: Path
) -> None:
    fifo = tmp_path / "cred"
    fifo.write_text("secret-value\n")
    environ: dict[str, str] = {}
    probe.take_credential(fifo=fifo, environ=environ)
    assert environ == {_CREDENTIAL_ENV: "secret-value"}


def test_without_a_fifo_the_environment_must_already_carry_the_credential() -> None:
    probe.take_credential(fifo=None, environ={_CREDENTIAL_ENV: "x"})
    with pytest.raises(SystemExit, match="not set"):
        probe.take_credential(fifo=None, environ={})


# --- the go signal -----------------------------------------------------------------


def test_now_releases_at_once_and_an_instant_is_waited_for(*, tmp_path: Path) -> None:
    now = tmp_path / "go"
    now.write_text("now\n")
    assert barrier.wait_for_go(fifo=now, clock=lambda: 10.0) == 10.0

    later = tmp_path / "later"
    later.write_text("at 100.0\n")
    ticks = iter([98.0, 99.0, 99.99, 100.01, 100.01])
    assert barrier.wait_for_go(fifo=later, clock=lambda: next(ticks)) == 100.01


def test_an_instant_already_past_is_a_missed_barrier(*, tmp_path: Path) -> None:
    past = tmp_path / "go"
    past.write_text("at 5\n")
    with pytest.raises(barrier.BarrierMissedError, match="clock read 20.000") as raised:
        barrier.wait_for_go(fifo=past, clock=lambda: 20.0)
    assert "named instant 5.000" in str(raised.value)
    assert "gave up at 20.000" in str(raised.value)


def test_the_barrier_client_delegates_and_pauses_once_at_the_first_close(*, client: Any) -> None:
    created = _create(client=client)
    released: list[int] = []
    trace: dict[str, Any] = {}

    def pause() -> float:
        released.append(1)
        return 42.0

    racer = barrier.BarrierClient(inner=client, barrier=pause, trace=trace)
    assert racer.show_issue(issue_id=created["item_id"])["status"] == "active"
    successor = racer.create_no_history_issue(title="t", description="d")
    racer.close_issue_without_verdict(issue_id=created["token_id"], reason="one")
    racer.close_issue_without_verdict(issue_id=successor, reason="two")

    assert released == [1]
    assert trace["released_at"] == 42.0
    assert trace["successors_created"] == [successor]
    assert [c["reason"] for c in trace["closes"]] == ["one", "two"]
    assert client.show_issue(issue_id=created["token_id"])["close_reason"] == "one"

    quiet = barrier.BarrierClient(inner=client, barrier=None, trace={})
    quiet.close_issue_without_verdict(issue_id=successor, reason="three")
    assert client.show_issue(issue_id=successor)["close_reason"] == "two"


# --- create, writer, inspect, dispose -------------------------------------------


def test_create_makes_an_active_claim_naming_its_first_token(*, client: Any) -> None:
    created = _create(client=client)

    assert created["item_id"].startswith("bd-ib-")
    assert created["status"] == "active"
    record = client.show_issue(issue_id=created["item_id"])
    assert record["assignee"] == "claim-token-race-drill"
    assert record["metadata"]["dispatch_claim_token"] == created["token_id"]
    assert client.show_issue(issue_id=created["token_id"])["status"] != "closed"


def test_a_lone_writer_applies_and_a_second_that_decided_on_the_same_read_stands_down(
    *, client: Any, tmp_path: Path
) -> None:
    created = _create(client=client)
    first = _writer_args(
        tmp_path=tmp_path,
        item=created["item_id"],
        writer=_CONTROL,
        case="seq",
        point="start",
        go="now",
    )
    second = _writer_args(
        tmp_path=tmp_path,
        item=created["item_id"],
        writer=_REMOTE,
        case="seq",
        point="start",
        go="now",
    )

    # Both decide now; only then does the first write.
    second_record = client.show_issue(issue_id=created["item_id"])
    report_one = probe.run_writer(args=first, plugin=plugin, client=client)
    assert report_one["outcome"] == "applied"
    assert report_one["token"] == created["token_id"]
    assert json.loads(first.decided.read_text())["token"] == created["token_id"]
    assert (
        client.show_issue(issue_id=created["item_id"])["metadata"]["dispatch_claim"]["run_id"]
        == first.run_id
    )

    # The second writer's decision read happened before the first write.
    decided_row = plugin.claim_row_from_record(record=second_record)
    result = plugin.change_claim(
        client=client,
        work_item_id=created["item_id"],
        writer=_REMOTE,
        intent="x",
        claim_tokens=True,
        still_as_decided=plugin.same_claim_row(row=decided_row),
    )
    assert result.outcome == "claim-changed"

    # And a writer reading fresh after the first finished writes too: nothing stale.
    report_two = probe.run_writer(args=second, plugin=plugin, client=client)
    assert report_two["outcome"] == "applied"
    assert report_two["trace"]["released_at"] > 0


def test_a_writer_whose_close_barrier_is_already_past_reports_barrier_missed(
    *, client: Any, tmp_path: Path
) -> None:
    created = _create(client=client)
    args = _writer_args(
        tmp_path=tmp_path,
        item=created["item_id"],
        writer=_CONTROL,
        case="late",
        point="close",
        go="at 1",
    )

    report = probe.run_writer(args=args, plugin=plugin, client=client)

    assert report["outcome"] == "barrier-missed"
    assert "clock read" in report["detail"]
    marker = json.loads(args.go_fifo.with_name("at-barrier.json").read_text())
    assert marker["writer"] == _CONTROL
    assert marker["clock"] == report["trace"]["barrier_reached_at"]
    assert report["trace"]["closes"] == []
    assert len(report["trace"]["successors_created"]) == 1
    assert client.show_issue(issue_id=created["token_id"])["status"] != "closed"
    assert json.loads(args.report.read_text())["outcome"] == "barrier-missed"


def test_inspect_grades_a_won_token_and_a_stood_down_loser(*, client: Any, tmp_path: Path) -> None:
    created = _create(client=client)
    winner = _writer_args(
        tmp_path=tmp_path,
        item=created["item_id"],
        writer=_CONTROL,
        case="c",
        point="close",
        go="now",
    )
    loser = _writer_args(
        tmp_path=tmp_path,
        item=created["item_id"],
        writer=_REMOTE,
        case="c",
        point="close",
        go="now",
    )
    loser_record = client.show_issue(issue_id=created["item_id"])
    probe.run_writer(args=winner, plugin=plugin, client=client)
    # The loser: decided on the earlier read, closes the token it read, and loses
    # the compare-and-swap exactly as it would on the server.
    trace: dict[str, Any] = {}
    racer = barrier.BarrierClient(inner=client, barrier=None, trace=trace)
    successor = racer.create_no_history_issue(title="t", description="d")
    racer.close_issue_without_verdict(issue_id=created["token_id"], reason="late-reason")
    racer.close_issue_without_verdict(
        issue_id=successor, reason=json.dumps({"kind": "claim-token-discard", "writer": _REMOTE})
    )
    loser.report.write_text(
        json.dumps(
            {"writer": _REMOTE, "outcome": "claim-changed", "writer_run_id": "r", "trace": trace}
        )
    )
    _ = loser_record

    verdict = probe.run_inspect(
        args=argparse.Namespace(
            item=created["item_id"],
            token=created["token_id"],
            reports=[str(winner.report), str(loser.report)],
        ),
        client=client,
    )

    assert verdict["ok"] is True, verdict
    assert verdict["winner"] == _CONTROL
    assert verdict["writers"] == {_CONTROL: "applied", _REMOTE: "claim-changed"}
    assert verdict["item_run_id"] == winner.run_id
    assert verdict["release_skew_seconds"] == 0.0
    assert verdict["attempted_reasons"][_REMOTE] == "late-reason"


def test_grade_fails_a_chain_where_nobody_won_or_a_loser_kept_its_successor() -> None:
    item = {
        "id": "i",
        "metadata": {"dispatch_claim_token": "s1", "dispatch_claim": {"run_id": "r1"}},
    }
    reason = json.dumps({"kind": "claim-token-transition", "writer": "a", "successor": "s1"})
    token = {"id": "t", "status": "closed", "close_reason": reason}
    won = {
        "writer": "a",
        "outcome": "applied",
        "writer_run_id": "r1",
        "successor_token_id": "s1",
        "trace": {"closes": [{"reason": reason}], "successors_created": ["s1"]},
    }
    kept = {
        "writer": "b",
        "outcome": "claim-changed",
        "trace": {"closes": [{"reason": "other"}], "successors_created": ["s2"]},
    }

    open_successor = ledger.grade(
        item=item, token=token, reports=[won, kept], successors={"s2": {"status": "backlog"}}
    )
    assert open_successor["checks"]["losers_stood_down"] is False
    assert open_successor["ok"] is False

    nobody = ledger.grade(
        item=item,
        token={"id": "t", "status": "closed", "close_reason": "{}"},
        reports=[kept],
        successors={},
    )
    assert nobody["winner"] is None
    assert nobody["checks"]["exactly_one_writer_reason_on_token"] is False
    assert nobody["checks"]["token_closed_once_with_a_transition_reason"] is False
    assert nobody["token_close_reason"] == "{}"

    unparsable = ledger.grade(
        item={"metadata": "no"}, token={"close_reason": "not json"}, reports=[], successors={}
    )
    assert unparsable["token_close_reason"] == "not json"
    assert unparsable["item_run_id"] is None
    assert unparsable["release_skew_seconds"] is None
    not_an_object = ledger.grade(item={}, token={"close_reason": "[1]"}, reports=[], successors={})
    assert not_an_object["token_close_reason"] == "[1]"
    unset = ledger.grade(item={}, token={"close_reason": None}, reports=[], successors={})
    assert unset["token_close_reason"] is None


def test_dispose_holds_the_token_once_more_and_closes_the_item(*, client: Any) -> None:
    created = _create(client=client)
    args = argparse.Namespace(item=created["item_id"], writer=_CONTROL, reason="drill finished")

    disposed = probe.run_dispose(args=args, plugin=plugin, client=client)

    assert disposed == {"item": created["item_id"], "hold_outcome": "applied", "closed": True}
    assert client.show_issue(issue_id=created["item_id"])["status"] == "closed"
    assert client.show_issue(issue_id=created["token_id"])["status"] == "closed"


def test_dispose_leaves_an_item_whose_token_it_cannot_win(*, client: Any) -> None:
    created = _create(client=client)
    client.close_issue_without_verdict(issue_id=created["token_id"], reason="someone else")
    args = argparse.Namespace(item=created["item_id"], writer=_CONTROL, reason="drill finished")

    disposed = probe.run_dispose(args=args, plugin=plugin, client=client)

    assert disposed["closed"] is False
    assert disposed["hold_outcome"] == "claim-transition-pending"
    assert client.show_issue(issue_id=created["item_id"])["status"] == "active"


# --- the command line ----------------------------------------------------------------


def _common(*, clone: Path) -> list[str]:
    return ["--scripts-root", str(_SCRIPTS_ROOT), "--repo-root", str(clone), "--bd-path", "bd"]


def test_main_runs_every_verb_and_prints_json(
    *,
    clone: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(_CREDENTIAL_ENV, "x")
    assert (
        probe.main(argv=[*_common(clone=clone), "create", "--title", "t", "--description", "d"])
        == 0
    )
    created = json.loads(capsys.readouterr().out)

    go = tmp_path / "go"
    go.write_text("now\n")
    writer = [
        *_common(clone=clone),
        "writer",
        "--item",
        created["item_id"],
        "--writer",
        _CONTROL,
        "--case",
        "c",
        "--run-id",
        "r",
        "--go-fifo",
        str(go),
        "--barrier-point",
        "start",
        "--decided",
        str(tmp_path / "d.json"),
        "--report",
        str(tmp_path / "r.json"),
    ]
    assert probe.main(argv=writer) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "applied"

    inspect = [
        *_common(clone=clone),
        "inspect",
        "--item",
        created["item_id"],
        "--token",
        created["token_id"],
        "--reports",
        str(tmp_path / "r.json"),
    ]
    assert probe.main(argv=inspect) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

    dispose = [
        *_common(clone=clone),
        "dispose",
        "--item",
        created["item_id"],
        "--writer",
        _CONTROL,
        "--reason",
        "done",
    ]
    assert probe.main(argv=dispose) == 0
    assert json.loads(capsys.readouterr().out)["closed"] is True


def test_main_reads_the_credential_fifo_and_defaults_argv_to_the_process(
    *,
    clone: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(_CREDENTIAL_ENV, raising=False)
    fifo = tmp_path / "cred"
    fifo.write_text("from-fifo\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe",
            *_common(clone=clone),
            "--credential-fifo",
            str(fifo),
            "create",
            "--title",
            "t",
            "--description",
            "d",
        ],
    )
    assert probe.main() == 0
    assert os.environ[_CREDENTIAL_ENV] == "from-fifo"
    assert json.loads(capsys.readouterr().out)["status"] == "active"
    monkeypatch.delenv(_CREDENTIAL_ENV)


# --- the fixture's own corners the play never reaches ---------------------------------


def test_the_fixture_store_refuses_a_missing_token_and_merges_metadata_like_the_server(
    *, client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.create_record(issue_id="bd-ib-bare", metadata={}, labels=["x"])
    result = plugin.change_claim(
        client=client, work_item_id="bd-ib-bare", writer="w", intent="i", claim_tokens=True
    )
    assert result.outcome == "claim-token-missing"

    client.update_issue(
        issue_id="bd-ib-bare",
        assignee="a",
        add_labels=["y"],
        remove_labels=["x"],
        metadata={"k": 1, "dispatch_claim_token": "stale"},
    )
    record = client.show_issue(issue_id="bd-ib-bare")
    assert (record["assignee"], record["labels"], record["metadata"]) == ("a", ["y"], {"k": 1})
    client.update_issue(issue_id="bd-ib-bare", clear_assignee=True)
    assert client.show_issue(issue_id="bd-ib-bare")["assignee"] is None
    client.close_issue(issue_id="bd-ib-bare", reason=None)
    assert client.show_issue(issue_id="bd-ib-bare")["status"] == "closed"

    created = _create(client=client)
    # A rival closes the token between this writer's read and its close: the
    # loser path, which discards the successor it had already created.
    rival_trace: dict[str, Any] = {}

    def rival_closes_first() -> float:
        client.close_issue_without_verdict(issue_id=created["token_id"], reason="rival")
        return 0.0

    racer = barrier.BarrierClient(inner=client, barrier=rival_closes_first, trace=rival_trace)
    lost = plugin.change_claim(
        client=racer, work_item_id=created["item_id"], writer="w", intent="i", claim_tokens=True
    )
    assert lost.outcome == "claim-changed"
    (discarded,) = rival_trace["successors_created"]
    assert "claim-token-discard" in client.show_issue(issue_id=discarded)["close_reason"]

    bare = plugin.work_item(
        id="bd-ib-notoken",
        type="task",
        status="backlog",
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a",
        assignee=None,
        depends_on=(),
        captured_at="now",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    plugin.create_work_item(client=client, item=bare, claim_tokens=False)
    assert "dispatch_claim_token" not in client.show_issue(issue_id="bd-ib-notoken")["metadata"]

    created = _create(client=client)
    tokens = sys.modules["livespec_orchestrator_beads_fabro._store_claim_tokens"]
    monkeypatch.setenv("DRILL_FAKE_HANG_INTENT", "held")
    monkeypatch.setattr(tokens.time, "sleep", lambda _s: os.environ.pop("DRILL_FAKE_HANG_INTENT"))
    held = plugin.change_claim(
        client=client, work_item_id=created["item_id"], writer="w", intent="held", claim_tokens=True
    )
    assert held.outcome == "applied"
    assert time.monotonic() > 0
