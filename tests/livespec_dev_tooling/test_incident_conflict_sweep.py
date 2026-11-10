"""A journaled rollback-conflict reaches the chain without an operator calling `/reconcile`.

The observer never calls recovery again for a retained action, so a conflict journaled
while the canonical tenant was unavailable would wait for a manual reconcile. The sweep
is the automatic trigger: at service start and on a timer it replays every journaled,
unreconciled conflict through the same reconcile route.
"""

from __future__ import annotations

import json
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest

import livespec_dev_tooling.incident_conflict_sweep as sweep_module
import livespec_dev_tooling.incident_observer_service as service
from livespec_dev_tooling.incident_conflict_sweep import ConflictSweep
from tests.livespec_dev_tooling import test_incident_conflict_chain as chain_tests
from tests.livespec_dev_tooling import test_incident_observer_control as control_tests
from tests.livespec_dev_tooling.test_incident_conflict_chain import (
    _overlap,
    _recover,
    _use_reader,
    failing,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen

controller = control_tests.controller
world = chain_tests.world
__all__ = ["controller", "failing", "world"]


def _journal_overlap(failing, monkeypatch):
    world, chain = failing
    _overlap(world)
    outcome = _recover(world, monkeypatch, chain=None)
    _use_reader(world=world, chain=chain)
    return world, chain, outcome


def _action(*, world):
    return json.loads(world.record.read_text())["actions"][world.intent.action_id]


def test_a_journaled_conflict_is_pending_until_the_chain_accepts_it(failing, monkeypatch):
    world, chain, outcome = _journal_overlap(failing, monkeypatch)
    sweep = ConflictSweep(installation=world.installation)
    assert sweep.pending() == (world.intent.action_id,)
    chain.down(down=True)
    assert sweep.sweep() == ()
    assert sweep.pending() == (world.intent.action_id,) and chain.transitions() == []
    chain.down(down=False)
    assert sweep.sweep() == (world.intent.action_id,)
    assert sweep.pending() == () and chain.status() == "blocked"
    assert _action(world=world)["receipt"] == outcome.receipt
    assert len(chain.transitions()) == 1


def test_a_reconciled_conflict_is_not_replayed_again(failing, monkeypatch):
    world, chain, _ = _journal_overlap(failing, monkeypatch)
    sweep = ConflictSweep(installation=world.installation)
    assert sweep.sweep() == (world.intent.action_id,)
    calls = len(chain.calls())
    assert sweep.sweep() == () and len(chain.calls()) == calls


def test_a_reverted_action_is_never_replayed_as_a_conflict(failing, monkeypatch):
    world, chain = failing
    outcome = _recover(world, monkeypatch, chain=None)
    assert outcome.status == "reverted"
    sweep = ConflictSweep(installation=world.installation)
    assert sweep.sweep() == () and chain.calls() == []
    assert sweep.pending() == ()


def test_an_action_with_no_journaled_effect_stays_pending_and_writes_nothing(failing, monkeypatch):
    world, chain = failing
    world.client(monkeypatch)
    sweep = ConflictSweep(installation=world.installation)
    assert sweep.pending() == (world.intent.action_id,)
    assert sweep.sweep() == () and chain.calls() == []
    assert sweep.pending() == (world.intent.action_id,)


def test_an_unreadable_state_directory_has_nothing_pending(tmp_path, world):
    absent = replace(world.installation, state=tmp_path / "no-such-state")
    sweep = ConflictSweep(installation=absent)
    assert sweep.pending() == () and sweep.sweep() == ()


def test_a_refused_reconcile_is_not_counted_and_never_stops_the_sweep(failing, monkeypatch):
    world, chain, _ = _journal_overlap(failing, monkeypatch)
    monkeypatch.setattr(
        sweep_module.ObserverReconcile,
        "execute",
        lambda _self, **_: {"status": "refused", "reason": "state changed"},
    )
    assert ConflictSweep(installation=world.installation).sweep() == ()
    assert chain.calls() == []


def test_a_raising_reconcile_is_contained_to_that_action(failing, monkeypatch, capsys):
    world, _, _ = _journal_overlap(failing, monkeypatch)

    def boom(_self, **_):
        raise OSError("state unavailable")

    monkeypatch.setattr(sweep_module.ObserverReconcile, "execute", boom)
    assert ConflictSweep(installation=world.installation).sweep() == ()
    assert "incident-conflict-sweep: state unavailable" in capsys.readouterr().err


def test_the_loop_sweeps_at_once_then_on_every_interval_until_stopped(failing, monkeypatch):
    world, chain, _ = _journal_overlap(failing, monkeypatch)
    waits = []

    class Stop:
        def wait(self, timeout):
            waits.append(timeout)
            return len(waits) >= 2

    ConflictSweep(installation=world.installation, interval_seconds=7).run(stop=Stop())
    assert waits == [7, 7]
    assert chain.status() == "blocked" and len(chain.transitions()) == 1


def test_start_runs_the_loop_in_a_daemon_thread_until_stopped(failing, monkeypatch):
    world, _ = failing
    swept = Event()
    monkeypatch.setattr(ConflictSweep, "sweep", lambda _self: swept.set() or ())
    stop = Event()
    thread = ConflictSweep(installation=world.installation, interval_seconds=0.01).start(stop=stop)
    assert thread.daemon is True
    assert swept.wait(10)
    stop.set()
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_the_isolated_service_starts_the_sweep_and_stops_it_with_the_server(
    controller, monkeypatch
):
    application, _, _, _, _ = controller
    monkeypatch.setattr(service.sys, "argv", ["observer-service", "--config", "/etc/host-config"])
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(service.ControllerService, "installed", lambda **_: application)
    started = []

    class Sweep:
        def __init__(self, *, installation):
            started.append(installation)

        def start(self, *, stop):
            started.append(stop.is_set())

    class Server:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def serve_forever(self):
            started.append("serve")

    captured = {}

    def make(*_args, **_kwargs):
        return Server()

    monkeypatch.setattr(service, "make_server", make)
    monkeypatch.setattr(service, "ConflictSweep", Sweep)
    monkeypatch.setattr(service, "Event", lambda: captured.setdefault("stop", Event()))
    assert service.main() == 0
    assert started == [application.installation, False, "serve"]
    assert captured["stop"].is_set()


@pytest.mark.parametrize("receipt", [None, "", "recovery-inverse:a:commit:b"])
def test_only_a_conflict_receipt_makes_an_action_pending(failing, receipt):
    world, _ = failing
    record = json.loads(world.record.read_text())
    record["actions"][world.intent.action_id].update(status="completed", receipt=receipt)
    world.record.write_text(json.dumps(record))
    assert ConflictSweep(installation=world.installation).pending() == ()
