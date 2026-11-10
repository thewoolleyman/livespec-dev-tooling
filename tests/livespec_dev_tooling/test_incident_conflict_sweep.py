"""A journaled rollback-conflict reaches the chain without an operator, and without the fence.

The observer never calls recovery again for a retained action, so a conflict journaled
while the canonical tenant was unavailable would wait for a manual reconcile. The sweep
is the automatic trigger: at service start, when a recovery journals a conflict, and on
a timer it settles every action that owes the chain through the reconcile route, which
holds the observer's repository fence only for short local steps. A first-failure
callback that arrives mid-sweep therefore still gets the fence within its five seconds.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import livespec_dev_tooling.incident_conflict_sweep as sweep_module
import livespec_dev_tooling.incident_observer_service as service
from livespec_dev_tooling._incident_observer_store import repository_lock
from livespec_dev_tooling.incident_conflict_sweep import ConflictSweep
from tests.livespec_dev_tooling import test_incident_conflict_chain as chain_tests
from tests.livespec_dev_tooling import test_incident_observer_control as control_tests
from tests.livespec_dev_tooling.test_incident_conflict_chain import (
    REPOSITORY,
    Clock,
    _journal,
    _recover,
    _use_reader,
    failing,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen

controller = control_tests.controller
world = chain_tests.world
__all__ = ["controller", "failing", "world"]

# The first-failure callback's own fence wait (incident_observer_endpoint._FENCE_WAIT_SECONDS).
_CALLBACK_FENCE_WAIT = 5.0


def _action(*, world):
    return json.loads(world.record.read_text())["actions"][world.intent.action_id]


def _write_action(*, world, **fields):
    record = json.loads(world.record.read_text())
    record["actions"][world.intent.action_id].update(fields)
    world.record.write_text(json.dumps(record))


def _sweep(world, clock=None, **kwargs):
    return ConflictSweep(installation=world.installation, clock=clock or Clock(), **kwargs)


def test_a_journaled_conflict_is_pending_until_the_chain_accepts_it(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    sweep = _sweep(world)
    assert sweep.pending() == (world.intent.action_id,)
    assert sweep.sweep() == (world.intent.action_id,)
    assert chain.status() == "blocked" and len(chain.transitions()) == 1
    assert sweep.pending() == ()


def test_a_reconciled_conflict_is_never_written_again(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    _ = _sweep(world).sweep()
    calls = len(chain.calls())
    assert _sweep(world).sweep() == ()
    assert len(chain.calls()) == calls


def test_an_unavailable_tenant_backs_the_action_off_until_its_retry_is_due(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    clock = Clock()
    chain.down(down=True)
    assert _sweep(world, clock).sweep() == ()
    assert _action(world=world).get("sweep", {}).get("next_at") == clock.now + 300
    chain.down(down=False)
    assert _sweep(world, clock).pending() == ()
    clock.now += 300
    assert _sweep(world, clock).sweep() == (world.intent.action_id,)
    assert chain.status() == "blocked"


def test_a_terminal_conflict_is_never_pending(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    _ = _sweep(world).sweep()
    _write_action(world=world, reconciled=False, sweep={"terminal": "half-reopen: x"})
    assert _sweep(world).pending() == ()


def test_an_action_with_no_journaled_effect_is_looked_up_then_backed_off(failing, monkeypatch):
    world, chain = failing
    _use_reader(world=world, chain=chain)
    world.client(monkeypatch)
    clock = Clock()
    assert _sweep(world, clock).sweep() == ()
    state = _action(world=world).get("sweep", {})
    assert (state.get("last"), state.get("attempts"), state.get("next_at")) == (
        "receipt-unavailable",
        1,
        clock.now + 300,
    )
    assert chain.calls() == [] and _sweep(world, clock).pending() == ()


def test_an_unreadable_state_directory_has_nothing_pending(tmp_path, world):
    installation = replace(world.installation, state=tmp_path / "absent")
    assert ConflictSweep(installation=installation).pending() == ()


def test_a_raising_settlement_is_contained_to_that_action(failing, monkeypatch, capsys):
    world, chain = failing
    _journal(world, chain, monkeypatch)

    def boom(_self, **_):
        raise OSError("state unavailable")

    monkeypatch.setattr(sweep_module.ObserverReconcile, "settle", boom)
    assert _sweep(world).sweep() == ()
    assert f"{world.intent.action_id}: OSError: state unavailable" in capsys.readouterr().err


def test_the_loop_survives_an_expected_failure_and_keeps_sweeping(failing, monkeypatch, capsys):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    stop = Event()
    passes = []
    real = ConflictSweep.pending

    def flaky(self):
        passes.append(len(passes))
        if passes == [0]:
            raise KeyError("corrupt action")
        stop.set()
        return real(self)

    monkeypatch.setattr(ConflictSweep, "pending", flaky)
    _sweep(world, interval_seconds=0.01).run(stop=stop)
    assert passes == [0, 1]
    assert "sweep pass failed: KeyError: 'corrupt action'" in capsys.readouterr().err
    assert chain.status() == "blocked"


def test_a_wake_runs_a_pass_at_once_and_stop_ends_the_loop(failing, monkeypatch):
    world, _ = failing
    stop = Event()
    sweep = _sweep(world, interval_seconds=3600)
    first, second = Event(), Event()
    passes = []

    def counted(_self):
        passes.append(1)
        (first if len(passes) == 1 else second).set()
        return ()

    monkeypatch.setattr(ConflictSweep, "sweep", counted)
    on_crash = Mock()
    thread = sweep.start(stop=stop, on_crash=on_crash)
    assert first.wait(10) and thread.daemon
    sweep.wake.set()
    assert second.wait(10) and len(passes) == 2
    stop.set()
    sweep.wake.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert on_crash.call_count == 0 and not sweep.crashed.is_set()


def test_an_unexpected_exception_crashes_the_sweep_loudly_and_brings_the_service_down(
    failing, monkeypatch
):
    """No broad catch in a daemon loop: the thread dies with its traceback, the service exits."""
    world, _ = failing
    seen = []
    monkeypatch.setattr(threading, "excepthook", lambda args: seen.append(args.exc_type))

    def broken(_self):
        raise RuntimeError("a defect, not an expected failure")

    monkeypatch.setattr(ConflictSweep, "sweep", broken)
    sweep = _sweep(world, interval_seconds=3600)
    on_crash = Mock()
    thread = sweep.start(stop=Event(), on_crash=on_crash)
    thread.join(timeout=10)
    assert not thread.is_alive() and seen == [RuntimeError]
    assert on_crash.call_count == 1 and sweep.crashed.is_set()


def test_a_callback_arriving_mid_sweep_gets_the_fence_within_its_wait(failing, monkeypatch):
    """The chain write runs outside the fence: each slow authority call leaves it free."""
    world, chain = failing
    _journal(world, chain, monkeypatch)
    chain.mode("slow-6")
    thread = Thread(target=_sweep(world).sweep, daemon=True)
    thread.start()
    busy = chain.directory / "busy"
    deadline = time.monotonic() + 60
    while not busy.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert busy.exists()
    started = time.monotonic()
    with repository_lock(
        directory=world.installation.state,
        repository=REPOSITORY,
        wait_seconds=_CALLBACK_FENCE_WAIT,
    ):
        waited = time.monotonic() - started
    assert waited < _CALLBACK_FENCE_WAIT and thread.is_alive()
    thread.join(timeout=60)
    assert not thread.is_alive() and chain.status() == "blocked"


def _serve(controller, monkeypatch, *, crash: bool):
    application, _, _, _, _ = controller
    monkeypatch.setattr(service.sys, "argv", ["observer-service", "--config", "/etc/host-config"])
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(service.ControllerService, "installed", lambda **_: application)
    started = []

    class Sweep:
        def __init__(self, *, installation, wake):
            started.append((installation, wake))
            self.crashed = Event()

        def start(self, *, stop, on_crash):
            started.append(stop.is_set())
            if crash:
                self.crashed.set()
                on_crash()

    class Server:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def shutdown(self):
            started.append("shutdown")

        def serve_forever(self):
            started.append("serve")

    class Watcher:
        failed = Event()

        def start(self, *, on_exit):
            started.append(("watcher", on_exit.__name__))

    captured = {}
    monkeypatch.setattr(service, "installed_watcher", lambda **_: Watcher())
    monkeypatch.setattr(service, "make_server", lambda *_args, **_kwargs: Server())
    monkeypatch.setattr(service, "ConflictSweep", Sweep)
    monkeypatch.setattr(service, "Event", lambda: captured.setdefault("stop", Event()))
    return application, started, captured, service.main()


def test_the_isolated_service_starts_the_sweep_with_its_wake_and_stops_it_with_the_server(
    controller, monkeypatch
):
    application, started, captured, code = _serve(controller, monkeypatch, crash=False)
    assert code == 0
    assert started == [
        (application.installation, application.conflict_journaled),
        ("watcher", "shutdown"),
        False,
        "serve",
    ]
    assert captured["stop"].is_set() and application.conflict_journaled.is_set()


def test_a_crashed_sweep_shuts_the_server_down_and_the_service_exits_non_zero(
    controller, monkeypatch
):
    _, started, _, code = _serve(controller, monkeypatch, crash=True)
    assert code == 1 and started[-2:] == ["shutdown", "serve"]


@pytest.mark.parametrize("receipt", [None, "", "recovery-inverse:a:commit:b"])
def test_only_a_conflict_receipt_makes_a_settled_action_pending(failing, receipt):
    world, _ = failing
    _write_action(world=world, status="completed", receipt=receipt)
    assert ConflictSweep(installation=world.installation).pending() == ()


def test_a_reverted_action_is_never_written_as_a_conflict_by_the_sweep(failing, monkeypatch):
    world, chain = failing
    outcome = _recover(world, monkeypatch)
    _use_reader(world=world, chain=chain)
    assert outcome.status == "reverted"
    assert _sweep(world).sweep() == () and chain.calls() == []


def test_a_refused_settlement_is_not_counted_and_never_stops_the_sweep(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    monkeypatch.setattr(
        sweep_module.ObserverReconcile,
        "settle",
        lambda _self, **_: SimpleNamespace(status="refused"),
    )
    assert _sweep(world).sweep() == () and chain.calls() == []
