"""Review findings on livespec-dev-tooling#3854 (work-item livespec-dev-tooling-oqpw6t).

- `fast` means fast AND APPLICABLE: a gate that encodes a normal-path
  precondition an incident commit cannot meet is `not-applicable`, deferred
  with a reason naming that precondition, never run.
- A target with no deadline (the normal aggregate) stays in the caller's
  process group, so a group kill still takes it.
- A termination signal the caller ignores stays ignored.
- A deadline deferral names the concurrency it ran under, because the timing
  classes were measured with each gate alone.
- The CI entrance shares one confirmed launch-time recheck across members,
  retries a single transient refusal once, and echoes each member's output as
  that member completes.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_ci_entry
from livespec_dev_tooling._check_target_runner import TargetRun, run_targets
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiOutcome, CiTarget
from livespec_dev_tooling.incident_gate_inventory import inventory_gates
from livespec_dev_tooling.incident_local_gates import GateSpec, execute_plan, select_gates
from tests.livespec_dev_tooling.test_incident_ci_payload import packet

__all__: list[str] = []

_INVENTORY = Path(__file__).resolve().parents[2] / "check-targets.txt"
_NOT_APPLICABLE = (
    "check-commit-pairs-source-and-test",
    "check-master-ci-green",
    "check-red-green-replay",
)


def test_not_applicable_gates_are_deferred_naming_their_precondition() -> None:
    gates = inventory_gates(
        inventory=(
            "check-ci # incident-timing: not-applicable # incident-precondition: green-master-ci\n"
            "check-lint # incident-timing: fast\n"
        )
    )
    selections = select_gates(gates=gates)
    real = {
        gate.name: gate.classification for gate in inventory_gates(inventory=_INVENTORY.read_text())
    }
    facts = (
        [gate.classification for gate in gates] == ["not-applicable", "fast"],
        [selection.selected for selection in selections] == [False, True],
        "green-master-ci" in selections[0].reason,
        "not applicable" in selections[0].reason,
        [real[name] for name in _NOT_APPLICABLE] == ["not-applicable"] * 3,
    )
    assert facts == (True, True, True, True, True)


def test_a_target_without_a_deadline_stays_in_the_callers_process_group(tmp_path: Path) -> None:
    (outcome,) = run_targets(
        runs=[TargetRun(name="pgid", argv=("/bin/sh", "-c", "ps -o pgid= -p $$"))],
        cwd=tmp_path,
        max_workers=1,
    )
    assert int(outcome.output) == os.getpgrp()


def test_a_termination_signal_the_caller_ignores_stays_ignored(tmp_path: Path) -> None:
    seen: list[object] = []

    def record(*_args: object, **_kwargs: object) -> None:
        seen.append(signal.getsignal(signal.SIGTERM))

    previous = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        _ = run_targets(
            runs=[TargetRun(name="t", argv=("/bin/sh", "-c", "true"))],
            cwd=tmp_path,
            max_workers=1,
            deadline_seconds=5.0,
            on_complete=record,
        )
    finally:
        _ = signal.signal(signal.SIGTERM, previous)
    assert seen == [signal.SIG_IGN]


def test_a_deadline_deferral_names_its_concurrency(tmp_path: Path) -> None:
    report = execute_plan(
        plan=select_gates(
            gates=(
                GateSpec(name="slow", command=("/bin/sh", "-c", "sleep 30"), classification="fast"),
            )
        ),
        cwd=tmp_path,
        deadline_seconds=1.0,
    )
    assert report.results[0].status == "deferred-timeout"
    assert report.results[0].reason == "local gate deadline reached under 1-way concurrency"


def _event() -> CiEvent:
    return CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=("expedited-incident-response",),
    )


def _entry(*, tmp_path: Path, names: tuple[str, ...], current) -> incident_ci_entry.CiEntry:
    return incident_ci_entry.CiEntry(
        repo=tmp_path,
        targets=tuple(CiTarget(name=name, classification="fast") for name in names),
        current=current,
        observer=lambda **_: True,
    )


def _execute(*, entry: incident_ci_entry.CiEntry, tmp_path: Path, echo=None) -> int:
    payload = json.dumps(packet())
    plan = entry.plan(event=_event(), payload=payload, environ=dict(os.environ))
    assert plan is not None
    return entry.execute(
        plan=plan,
        names=tuple(target.name for target in entry.targets),
        report=tmp_path / "outcomes.jsonl",
        payload=payload,
        environ=dict(os.environ),
        echo=echo,
    )


def test_ci_members_share_one_confirmed_recheck(tmp_path: Path) -> None:
    names = ("check-a", "check-b", "check-c", "check-d")
    (tmp_path / "justfile").write_text("".join(f"{name}:\n    true\n" for name in names))
    reads: list[int] = []

    def current(**_: object) -> bool:
        reads.append(1)
        return True

    code = _execute(
        entry=_entry(tmp_path=tmp_path, names=names, current=current), tmp_path=tmp_path
    )
    # One read for the plan the caller holds, one for the shared recheck.
    assert (code, len(reads)) == (0, 2)


def test_ci_retries_one_transient_refusal(tmp_path: Path) -> None:
    (tmp_path / "justfile").write_text("check-a:\n    true\n")
    (tmp_path / "outcomes.jsonl").touch()
    answers = iter([True, False])
    code = _execute(
        entry=_entry(
            tmp_path=tmp_path, names=("check-a",), current=lambda **_: next(answers, True)
        ),
        tmp_path=tmp_path,
    )
    rows = [
        CiOutcome(**json.loads(line))
        for line in (tmp_path / "outcomes.jsonl").read_text().splitlines()
    ]
    assert (code, [row.outcome for row in rows]) == (0, ["passed"])


def test_ci_echoes_each_member_as_it_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(incident_ci_entry, "current_allowed_cpu_count", lambda: 2)
    # check-b finishes only once check-a's output has reached the job log.
    (tmp_path / "justfile").write_text(
        "check-a:\n    @echo a-finished\n"
        "check-b:\n"
        "    i=0; while [ ! -e echoed ] && [ $i -lt 100 ]; do sleep 0.1; i=$((i + 1)); done; test -e echoed\n"
    )
    logged: list[str] = []

    def echo(*, text: str) -> None:
        logged.append(text)
        (tmp_path / "echoed").touch()

    code = _execute(
        entry=_entry(tmp_path=tmp_path, names=("check-a", "check-b"), current=lambda **_: True),
        tmp_path=tmp_path,
        echo=echo,
    )
    assert (code, logged[0]) == (0, "::: just check-a [exit 0]\na-finished\n")
