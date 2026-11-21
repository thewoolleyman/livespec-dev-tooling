"""The memory-budget report reads committed inputs without enforcing them."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_REPORT = _ROOT / "ci-runner/k3s/phase2/report-memory-budget.py"
_BUDGET = _ROOT / "ci-runner/k3s/phase2/node-memory-budget.yaml"
_HOST_VARS = _ROOT / "ansible/inventory/host_vars"


def _nodes() -> dict[str, dict[str, Any]]:
    loaded = cast(dict[str, object], yaml.safe_load(_BUDGET.read_text(encoding="utf-8")))
    return cast(dict[str, dict[str, Any]], loaded["nodes"])


class _Report(Protocol):
    MemoryQuantityError: type[ValueError]
    _BUDGET: Path
    _GATES: Path
    _REPRO: Path

    def main(self) -> int: ...

    def report(self) -> tuple[list[str], list[tuple[str, float]]]: ...


def _load() -> _Report:
    spec = importlib.util.spec_from_file_location("node_memory_budget_report", _REPORT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_Report, module)


def test_report_lists_the_committed_nodes_and_only_the_committed_overcommitment(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _load()
    nodes = _nodes()
    monkeypatch.setattr(sys, "argv", [str(_REPORT)])

    assert report.main() == 0
    output = capsys.readouterr().out
    assert "REPORT-ONLY" in output
    assert all(node in output for node in nodes)
    assert "OVER-COMMITTED: gmktec-xubuntu" in output
    assert "OVER-COMMITTED: poweredge-xubuntu" not in output
    assert "OVER-COMMITTED: hp-xubuntu" not in output
    assert "OVER-COMMITTED: gamingpc-xubuntu" not in output
    assert "OVER-COMMITTED: macbook-m4-max-homelab-worker" not in output


def test_factory_memory_is_the_committed_pod_count_times_the_committed_request(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _load()
    nodes = _nodes()
    gmktec = cast(dict[str, Any], yaml.safe_load((_HOST_VARS / "gmktec-xubuntu.yml").read_text()))
    request_mib = gmktec["fabro_server_instances"][0]["sandbox_providers"]["kubernetes"][
        "process_spec"
    ]["memory_mb"]
    request_gib = float(request_mib) / 1024

    monkeypatch.setattr(sys, "argv", [str(_REPORT)])
    assert report.main() == 0
    output = capsys.readouterr().out
    for node, configured in nodes.items():
        count = configured.get("factory_pod_budget")
        if count is None:
            host = cast(dict[str, Any], yaml.safe_load((_HOST_VARS / f"{node}.yml").read_text()))
            count = host["factory_pod_budget"]
        row = next(row for row in output.splitlines() if row.startswith(f"{node} |"))
        assert f"| {int(count) * request_gib:.1f}Gi |" in row


def test_memory_quantity_conversion_rejects_an_unreportable_unit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = _load()
    budget = tmp_path / "budget.yaml"
    gates = tmp_path / "gates.yaml"
    repro = tmp_path / "repro.yaml"
    _ = budget.write_text(
        "\n".join(
            (
                "nodes:",
                "  fixture-node:",
                "    allocatable_memory_gib: 2",
                "    system_memory_gib: 1",
                "    factory_pod_budget: 0",
                "    gate_flavor: fixture-gates",
                "    repro_memory_gib: 0",
                "",
            )
        ),
        encoding="utf-8",
    )
    _ = gates.write_text(
        "\n".join(
            (
                "kind: ClusterQueue",
                "spec:",
                "  resourceGroups:",
                "    - flavors:",
                "        - name: fixture-gates",
                "          resources:",
                "            - name: memory",
                "              nominalQuota: 1024Mi",
                "",
            )
        ),
        encoding="utf-8",
    )
    _ = repro.write_text("---\n", encoding="utf-8")
    monkeypatch.setattr(report, "_BUDGET", budget)
    monkeypatch.setattr(report, "_GATES", gates)
    monkeypatch.setattr(report, "_REPRO", repro)

    rows, _ = report.report()
    assert "fixture-node | 2.00Gi | 1.0Gi" in rows[-1]

    _ = gates.write_text(gates.read_text(encoding="utf-8").replace("1024Mi", "1GB"))
    with pytest.raises(report.MemoryQuantityError):
        _ = report.report()
