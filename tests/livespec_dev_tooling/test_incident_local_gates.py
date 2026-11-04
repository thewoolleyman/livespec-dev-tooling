"""Behavioral evidence for the bounded incident local gate executor."""

from __future__ import annotations

import os
import select
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from livespec_dev_tooling.incident_local_gates import (
    GateSpec,
    execute_plan,
    route_resolved_gates,
    select_gates,
)

__all__: list[str] = []

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn


def gate(name: str, classification: str, code: str = "print('ran')") -> GateSpec:
    return GateSpec(name=name, command=(sys.executable, "-c", code), classification=classification)


def test_selection_defers_slow_and_unclassified_without_launch(tmp_path: Path) -> None:
    marker = tmp_path / "should-not-exist"
    forbidden = f"from pathlib import Path; Path({str(marker)!r}).touch()"
    plan = select_gates(
        gates=(
            gate("fast", "fast"),
            gate("slow", "slow", forbidden),
            gate("unknown", "unclassified", forbidden),
        )
    )
    report = execute_plan(plan=plan, cwd=tmp_path)
    assert report.exit_status == 0
    assert [(r.name, r.status) for r in report.results] == [
        ("fast", "passed"),
        ("slow", "deferred"),
        ("unknown", "deferred"),
    ]
    assert all(r.reason for r in report.results[1:])
    assert not marker.exists()


def test_fast_failure_preserves_status_and_output(tmp_path: Path) -> None:
    report = execute_plan(
        plan=select_gates(gates=(gate("broken", "fast", "print('actual failure'); exit(7)"),)),
        cwd=tmp_path,
    )
    assert report.exit_status == 7
    assert report.results[0].status == "failed"
    assert "actual failure" in report.results[0].output


def test_timeout_kills_owned_descendants_and_records_deferral(tmp_path: Path) -> None:
    pidfile = tmp_path / "child.pid"
    lifetime = tmp_path / "child-lifetime.fifo"
    os.mkfifo(lifetime)
    # Use a shell fixture so Python's coverage startup cannot consume the
    # execution deadline before the fixture has created its child at all.
    parent = GateSpec(
        name="unexpectedly-slow",
        classification="fast",
        command=(
            "/bin/sh",
            "-c",
            'exec 3> "$2"; trap "" TERM; sleep 30 & echo $! > "$1"; wait',
            "incident-timeout-fixture",
            str(pidfile),
            str(lifetime),
        ),
    )
    child_fd = os.open(lifetime, os.O_RDONLY | os.O_NONBLOCK)
    try:
        report = execute_plan(
            plan=select_gates(gates=(parent,)),
            cwd=tmp_path,
            deadline_seconds=2.0,
        )
        assert report.exit_status == 0
        assert report.results[0].status == "deferred-timeout"
        assert report.results[0].returncode is None
        assert int(pidfile.read_text()) > 0
        # Both the shell and its child inherit the FIFO writer. EOF proves
        # neither remains alive after SIGKILL, without requiring pidfd_open
        # (absent from the delegated Python build) or racing a /proc sample.
        ready, _, _ = select.select([child_fd], [], [], 5)
        assert ready == [child_fd]
        assert os.read(child_fd, 1) == b""
    finally:
        os.close(child_fd)


def test_no_executable_is_real_failure(tmp_path: Path) -> None:
    spec = GateSpec(name="missing", command=(str(tmp_path / "missing"),), classification="fast")
    report = execute_plan(plan=select_gates(gates=(spec,)), cwd=tmp_path)
    assert report.exit_status == 127
    assert report.results[0].status == "failed"


@pytest.mark.parametrize("deadline", [0, -1, 60.01, float("inf"), float("nan")])
def test_executor_refuses_invalid_deadline(tmp_path: Path, deadline: float) -> None:
    with pytest.raises(ValueError, match="deadline"):
        _ = execute_plan(plan=select_gates(gates=()), cwd=tmp_path, deadline_seconds=deadline)


def test_unknown_classification_is_deferred(tmp_path: Path) -> None:
    report = execute_plan(plan=select_gates(gates=(gate("new", "new-category"),)), cwd=tmp_path)
    assert report.results[0].status == "deferred"


def test_empty_command_refuses_without_a_false_pass(tmp_path: Path) -> None:
    report = execute_plan(
        plan=select_gates(gates=(GateSpec(name="bad", command=(), classification="fast"),)),
        cwd=tmp_path,
    )
    assert report.exit_status != 0


def test_selection_is_deterministic_and_preserves_order() -> None:
    specs = (gate("a", "slow"), gate("b", "fast"))
    assert select_gates(gates=specs) == select_gates(gates=specs)
    assert [entry.gate.name for entry in select_gates(gates=specs)] == ["a", "b"]


def test_child_preserves_explicit_boundary_transport(tmp_path: Path) -> None:
    environment = dict(os.environ, INCIDENT_TEST_TRANSPORT="preserved")
    report = execute_plan(
        plan=select_gates(
            gates=(
                gate(
                    "env",
                    "fast",
                    "import os; print(os.getenv('INCIDENT_TEST_TRANSPORT', 'absent'))",
                ),
            )
        ),
        cwd=tmp_path,
        environment=environment,
    )
    assert report.exit_status == 0
    assert report.results[0].output.strip() == "preserved"
    assert report.evidence_kind == "expedited-local-partial"


@dataclass(frozen=True)
class ContextFixture:
    """Structural adapter fixture; mode resolution is tested by its owner."""

    mode: str
    identity: object | None = None


def test_normal_context_does_not_run_checks_or_read_ambient_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "malformed-inherited-value")
    result = route_resolved_gates(
        context=ContextFixture("normal"), gates=(gate("failure", "fast", "exit(9)"),), cwd=tmp_path
    )
    assert result is None


@pytest.mark.parametrize(
    "context", [ContextFixture("expedited-repair"), ContextFixture("typo", object())]
)
def test_unresolved_context_refuses_without_normal_fallback(
    tmp_path: Path, context: ContextFixture
) -> None:
    result = route_resolved_gates(context=context, gates=(), cwd=tmp_path)
    assert result is not None
    assert result.exit_status == 78


def test_revert_runs_no_checks_even_when_fast_would_fail(tmp_path: Path) -> None:
    result = route_resolved_gates(
        context=ContextFixture("emergency-revert", object()),
        gates=(gate("failure", "fast", "exit(9)"),),
        cwd=tmp_path,
    )
    assert result is not None
    assert result.exit_status == 0
    assert result.results[0].status == "deferred"


def test_repair_uses_fast_gate_and_real_failure(tmp_path: Path) -> None:
    result = route_resolved_gates(
        context=ContextFixture("expedited-repair", object()),
        gates=(gate("failure", "fast", "exit(9)"),),
        cwd=tmp_path,
    )
    assert result is not None
    assert result.exit_status == 9


def test_signal_failure_preserves_shell_status(tmp_path: Path) -> None:
    report = execute_plan(
        plan=select_gates(
            gates=(
                gate("signal", "fast", "import os,signal; os.kill(os.getpid(), signal.SIGTERM)"),
            )
        ),
        cwd=tmp_path,
    )
    assert report.exit_status == 143


def test_empty_plan_is_explicit_partial_evidence(tmp_path: Path) -> None:
    report = execute_plan(plan=select_gates(gates=()), cwd=tmp_path)
    assert report.results == ()
    assert report.evidence_kind == "expedited-local-partial"
