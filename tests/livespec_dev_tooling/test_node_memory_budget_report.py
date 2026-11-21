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
    _BUDGET: Path

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
        assert f"| {round(int(count) * request_gib, 1):.1f}Gi |" in row


def test_rows_use_the_committed_gate_and_repro_allocations() -> None:
    report = _load()
    rows, _ = report.report()
    for node, configured in _nodes().items():
        row = next(row for row in rows if row.startswith(f"{node} |"))
        columns = [column.strip() for column in row.split("|")]
        assert columns[2] == f"{float(configured['gate_memory_gib']):.1f}Gi"
        assert columns[3] == f"{float(configured['repro_memory_gib']):.1f}Gi"
