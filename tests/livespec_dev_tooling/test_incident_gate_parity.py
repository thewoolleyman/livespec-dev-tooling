"""The expedited gate paths run and classify gates the way the normal path does.

Work-item livespec-dev-tooling-oqpw6t (plan expedited-incident-response-flag,
epic livespec-dev-tooling-bqnzcm). The maintainer's direction: the expedited
gates use the same logic as the normal ones unless a difference is necessary.

- The local hooks run their selected gates IN PARALLEL, like the normal
  aggregate, under the per-gate deadline. Two gates that each wait for the
  other's flag file can both pass only when they run at the same time: run
  serially, the first one waits out its deadline.
- The CI entrance runs its selected members in parallel too, by the same test.
- The CI entrance classifies every member exactly as the local hooks do, from
  the same `# incident-timing:` annotations in `check-targets.txt`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_ci_entry, incident_local_gates
from livespec_dev_tooling.incident_ci_inventory import load_inventory
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiOutcome, CiTarget
from livespec_dev_tooling.incident_gate_inventory import inventory_gates
from livespec_dev_tooling.incident_local_gates import GateSpec, execute_plan, select_gates
from tests.livespec_dev_tooling.test_incident_ci_payload import packet

__all__: list[str] = []

_INVENTORY = Path(__file__).resolve().parents[2] / "check-targets.txt"

# Creates its own flag ($1), then waits up to 10 s for the other gate's ($2).
_WAIT_FOR_PEER = (
    'touch "$1"; i=0; while [ ! -e "$2" ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i + 1)); done;'
    ' test -e "$2"'
)


def _peer(*, tmp_path: Path, own: str, other: str) -> GateSpec:
    return GateSpec(
        name=own,
        command=(
            "/bin/sh",
            "-c",
            _WAIT_FOR_PEER,
            "peer",
            str(tmp_path / own),
            str(tmp_path / other),
        ),
        classification="fast",
    )


def test_local_fast_gates_run_in_parallel_within_the_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(incident_local_gates, "current_allowed_cpu_count", lambda: 2, raising=False)
    report = execute_plan(
        plan=select_gates(
            gates=(
                _peer(tmp_path=tmp_path, own="check-a", other="check-b"),
                _peer(tmp_path=tmp_path, own="check-b", other="check-a"),
            )
        ),
        cwd=tmp_path,
        deadline_seconds=5.0,
    )
    assert [(result.name, result.status) for result in report.results] == [
        ("check-a", "passed"),
        ("check-b", "passed"),
    ]
    assert report.exit_status == 0


def test_ci_selected_members_run_in_parallel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(incident_ci_entry, "current_allowed_cpu_count", lambda: 2, raising=False)
    (tmp_path / "justfile").write_text(
        "".join(
            f"check-{own}:\n    /bin/sh -c '{_WAIT_FOR_PEER}' peer {own}.flag {other}.flag\n"
            for own, other in (("a", "b"), ("b", "a"))
        )
    )
    entry = incident_ci_entry.CiEntry(
        repo=tmp_path,
        targets=(
            CiTarget(name="check-a", classification="fast"),
            CiTarget(name="check-b", classification="fast"),
        ),
        current=lambda **_: True,
        observer=lambda **_: True,
    )
    event = CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=("expedited-incident-response",),
    )
    payload = json.dumps(packet())
    plan = entry.plan(event=event, payload=payload, environ=dict(os.environ))
    assert plan is not None
    report = tmp_path / "outcomes.jsonl"
    code = entry.execute(
        plan=plan,
        names=("check-a", "check-b"),
        report=report,
        payload=payload,
        environ=dict(os.environ),
    )
    rows = [CiOutcome(**json.loads(line)) for line in report.read_text().splitlines()]
    assert [(row.name, row.outcome) for row in rows] == [
        ("check-a", "passed"),
        ("check-b", "passed"),
    ]
    assert code == 0


def test_ci_entrance_classifies_every_member_as_the_local_hooks_do() -> None:
    local = {
        gate.name: gate.classification for gate in inventory_gates(inventory=_INVENTORY.read_text())
    }
    packaged = {target.name: target.classification for target in load_inventory()}
    annotated_fast_is_fast = packaged.get("check-file-lloc") == "fast"
    every_member_agrees = packaged == {name: local.get(name) for name in packaged}
    assert annotated_fast_is_fast
    assert every_member_agrees
