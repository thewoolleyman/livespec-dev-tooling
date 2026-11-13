"""The repository's one hang guard: its value, its expiry report, and its sole definition.

Covers `SPECIFICATION/non-functional-requirements.md`, "Load-independent
concurrency waits", for the part plan homelab-k8s-worker-nodes owns: every
`tests/spec/test_homelab_worker_*.py` call that waits on a script is bounded by
the one guard in `tests/hang_guard.py`, and no such file carries a bound of its
own.
"""

from __future__ import annotations

import re
import sys
from concurrent.futures import Future
from pathlib import Path
from threading import Barrier

import pytest

from tests import hang_guard
from tests.hang_guard import (
    HANG_GUARD_SECONDS,
    future_result_under_hang_guard,
    run_under_hang_guard,
    wait_for_barrier,
)

_TESTS = Path(__file__).resolve().parent
_SPEC_TESTS = _TESTS / "spec"
_CONCURRENCY_WAIT_TESTS = (
    *_SPEC_TESTS.glob("test_homelab_worker_*.py"),
    _TESTS / "consumer" / "test_fabro_settings_drift_scenario.py",
    *(
        _TESTS / "livespec_dev_tooling" / name
        for name in (
            "test_dev_host_retention.py",
            "test_dev_host_retention_tmpfs.py",
            "test_dispatcher_coverage_namespaces_signals.py",
            "test_incident_ci_job_collection.py",
            "test_incident_conflict_chain.py",
            "test_incident_conflict_sweep.py",
            "test_incident_observer.py",
            "test_incident_observer_control.py",
            "test_incident_observer_endpoint.py",
            "test_incident_observer_invalidation.py",
            "test_incident_observer_invalidation_edges.py",
            "test_incident_observer_reconciler_window.py",
            "test_incident_observer_target_branch.py",
            "test_incident_original_run_watch.py",
            "test_incident_recovery_journal_service.py",
            "test_incident_repository_fence.py",
            "test_local_gate_slots.py",
        )
    ),
    _TESTS / "livespec_dev_tooling" / "fleet" / "test_tag_adopt.py",
)
_SPEC_MINIMUM_SECONDS = 120
_OWN_CONCURRENCY_TIMEOUT = re.compile(
    r"\.(?:acquire|join|wait)\(\s*(?:timeout\s*=\s*)?[0-9][0-9.]*\s*\)"
)


def test_the_guard_is_no_shorter_than_the_specification_allows() -> None:
    assert HANG_GUARD_SECONDS >= _SPEC_MINIMUM_SECONDS


def test_a_finished_command_returns_its_result_unchanged() -> None:
    result = run_under_hang_guard(
        [sys.executable, "-c", "import sys; print('done'); sys.exit(3)"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3
    assert result.stdout == "done\n"


def test_a_finished_future_returns_its_result_unchanged() -> None:
    future: Future[str] = Future()
    future.set_result("done")
    assert future_result_under_hang_guard(future=future, waiting_for="a finished future") == "done"


def test_a_future_timeout_fails_as_a_named_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hang_guard, "HANG_GUARD_SECONDS", 0)
    with pytest.raises(pytest.fail.Exception, match="HANG: waiting for the future"):
        future_result_under_hang_guard(future=Future(), waiting_for="the future")


def test_a_barrier_returns_its_party_index_when_all_parties_arrive() -> None:
    assert wait_for_barrier(barrier=Barrier(1), waiting_for="a one-party barrier") == 0


def test_a_barrier_timeout_fails_as_a_named_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hang_guard, "HANG_GUARD_SECONDS", 0)
    with pytest.raises(pytest.fail.Exception, match="HANG: waiting for the barrier"):
        wait_for_barrier(barrier=Barrier(2), waiting_for="the barrier")


def test_expiry_fails_the_test_as_a_hang_that_names_the_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The expiry is the outcome under test, so this one wait is bounded on purpose.
    monkeypatch.setattr(hang_guard, "HANG_GUARD_SECONDS", 1)
    with pytest.raises(pytest.fail.Exception) as raised:
        run_under_hang_guard([sys.executable, "-c", "import time; time.sleep(600)"])
    message = str(raised.value)
    assert message.startswith("HANG: ")
    assert "import time; time.sleep(600)" in message
    assert "after 1 s" in message


def test_no_concurrency_wait_test_file_keeps_a_bound_of_its_own() -> None:
    files = sorted(_CONCURRENCY_WAIT_TESTS)
    assert files
    offenders = [
        f"{path.name}:{number}"
        for path in files
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _OWN_CONCURRENCY_TIMEOUT.search(line)
    ]
    assert offenders == []
