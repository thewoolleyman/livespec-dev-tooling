"""The report reads committed memory sources without becoming an enforcement gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_REPORT = _ROOT / "ci-runner/k3s/phase2/report-memory-budget.py"
_BUDGET = _ROOT / "ci-runner/k3s/phase2/node-memory-budget.yaml"


def _load():
    spec = importlib.util.spec_from_file_location("node_memory_budget_report", _REPORT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_reads_each_committed_node_and_reports_only_the_actual_shortfalls(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _load()
    monkeypatch.setattr("sys.argv", [str(_REPORT)])

    assert report.main() == 0
    output = capsys.readouterr().out
    rows, findings = report.report()

    assert "REPORT-ONLY" in output
    assert "committed ceiling, not live pod demand" in output
    budget = yaml.safe_load(_BUDGET.read_text(encoding="utf-8"))["nodes"]
    assert all(node in output for node in budget)
    assert [node for node, _ in findings] == ["gmktec-xubuntu"]
    assert "OVER-COMMITTED: gmktec-xubuntu" in output
    assert all("|" in row for row in rows[3:])


def test_factory_memory_is_derived_from_the_committed_ceiling_and_provider_request() -> None:
    report = _load()
    budget = yaml.safe_load(_BUDGET.read_text(encoding="utf-8"))["nodes"]
    request = report.factory_pod_request_gib()
    rows, _ = report.report()

    for node, configured in budget.items():
        expected = report.factory_pod_budget(node, configured) * request
        row = next(row for row in rows if row.startswith(f"{node} |"))
        assert f"| {expected:.1f}Gi |" in row


def test_runner_memory_is_the_committed_slot_count_times_the_committed_runner_request() -> None:
    report = _load()
    budget = yaml.safe_load(_BUDGET.read_text(encoding="utf-8"))["nodes"]
    rows, _ = report.report()
    header = [cell.strip() for cell in rows[2].split("|")]
    assert "runners" in header
    column = header.index("runners")
    request = report.runner_request_gib()
    assert request > 0

    for node, configured in budget.items():
        if "runner_memory_gib" in configured:
            continue
        expected = report.runner_slots(node) * request
        row = next(row for row in rows if row.startswith(f"{node} |"))
        assert row.split("|")[column].strip() == f"{expected:.1f}Gi"


def test_a_node_without_committed_slots_claims_no_runner_memory() -> None:
    report = _load()
    rows, _ = report.report()
    header = [cell.strip() for cell in rows[2].split("|")]
    assert "runners" in header
    column = header.index("runners")
    row = next(row for row in rows if row.startswith("gmktec-xubuntu |"))
    assert report.runner_slots("gmktec-xubuntu") == 0
    assert row.split("|")[column].strip() == "0.0Gi"


def test_report_rejects_an_unreportable_committed_memory_unit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = _load()
    budget = tmp_path / "budget.yaml"
    invalid_gates = tmp_path / "invalid-gates.yaml"
    empty_repro = tmp_path / "empty-repro.yaml"
    budget.write_text(
        """\
nodes:
  fixture-node:
    allocatable_memory_gib: 2
    system_memory_gib: 1
    factory_pod_budget: 0
    gate_flavor: fixture-gates
    repro_memory_gib: 0
    runner_memory_gib: 0
""",
        encoding="utf-8",
    )
    invalid_gates.write_text(
        """\
kind: ClusterQueue
spec:
  resourceGroups:
    - flavors:
        - name: fixture-gates
          resources:
            - name: memory
              nominalQuota: 1024Mi
""",
        encoding="utf-8",
    )
    empty_repro.write_text("---\n", encoding="utf-8")
    monkeypatch.setattr(report, "_BUDGET", budget)
    monkeypatch.setattr(report, "_GATES", invalid_gates)
    monkeypatch.setattr(report, "_REPRO", empty_repro)

    rows, _ = report.report()
    assert "fixture-node | 2.00Gi | 1.0Gi" in rows[-1]

    invalid_gates.write_text(
        invalid_gates.read_text(encoding="utf-8").replace("1024Mi", "1GB"),
        encoding="utf-8",
    )

    with pytest.raises(report.MemoryQuantityError):
        report.report()
