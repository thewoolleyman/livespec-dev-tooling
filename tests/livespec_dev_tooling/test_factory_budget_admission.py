"""The factory budget admission reconciler, run for real against a faked kubectl.

The TEMPORARY fixed factory-vs-CI CPU share (maintainer ruling 2026-11-08; plan
gmktec-factory-placement, research note 003): each factory node holds at most its
committed `factory_pod_budget` sandbox pods, because the reconciler labels it
`ci-runner.io/factory-admit=true|false` and the sandbox driver selects that label.

WHY THE SCRIPT IS RUN RATHER THAN READ. Every claim here is about a DECISION:
which node is admitted, what is counted, what a missing budget file or the kill
switch does, and that a full fleet never leaves a sandbox Pending. The script runs
with a fake `kubectl` first on PATH, which serves canned JSON and logs every argv.
No cluster is reached and nothing leaves `tmp_path`.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

__all__: list[str] = []

_Json = dict[str, Any]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "factory-budget-admission"
_RECONCILE = _DIR / "reconcile-factory-budget-admit.sh"
_SERVICE = _DIR / "reconcile-factory-budget-admit.service"
_PLAY = _REPO_ROOT / "ansible" / "ci-pool.yml"
_SELECTOR_DEFAULTS = (
    _REPO_ROOT / "ansible" / "roles" / "sandbox_driver_kubernetes" / "defaults" / "main.yml"
)
_ADMIT = "ci-runner.io/factory-admit"
_GMK = "gmktec-xubuntu"
_PE = "poweredge-xubuntu"

_FAKE_KUBECTL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
case "$*" in
  "get nodes -l ci-runner.io/factory=true -o json") cat "$FAKE_DIR/nodes.json" ;;
  "get pods --all-namespaces -l app.kubernetes.io/managed-by=sandbox-driver-kubernetes -o json")
    [ -f "$FAKE_DIR/pods.json" ] || { echo 'Error from server: connection refused' >&2; exit 1; }
    cat "$FAKE_DIR/pods.json" ;;
  label*) ;;
  *) echo "fake kubectl: unexpected argv: $*" >&2; exit 1 ;;
esac
"""


def _node(name: str, *, admit: str | None = None, alloc: str = "32") -> _Json:
    labels = {"kubernetes.io/hostname": name, "ci-runner.io/factory": "true"}
    if admit is not None:
        labels[_ADMIT] = admit
    return {"metadata": {"name": name, "labels": labels}, "status": {"allocatable": {"cpu": alloc}}}


def _sandbox(
    name: str, *, node: str | None, phase: str = "Running", cleanup: bool = False
) -> _Json:
    labels = {"app.kubernetes.io/managed-by": "sandbox-driver-kubernetes"}
    if cleanup:
        labels["sandbox-driver-kubernetes/cleanup-of"] = name
    spec: _Json = {"nodeName": node} if node is not None else {}
    return {
        "metadata": {"name": name, "namespace": "factory", "labels": labels},
        "spec": spec,
        "status": {"phase": phase},
    }


def _run(
    tmp_path: Path,
    *,
    nodes: list[_Json],
    pods: list[_Json] | None,
    budgets: str | None,
    gate: str = "on",
    dry_run: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    fake = tmp_path / "fake"
    bin_dir = tmp_path / "bin"
    fake.mkdir()
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    _ = kubectl.write_text(_FAKE_KUBECTL, encoding="utf-8")
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
    _ = (fake / "nodes.json").write_text(json.dumps({"items": nodes}), encoding="utf-8")
    if pods is not None:
        _ = (fake / "pods.json").write_text(json.dumps({"items": pods}), encoding="utf-8")
    budget_file = tmp_path / "factory-pod-budgets.conf"
    if budgets is not None:
        _ = budget_file.write_text(budgets, encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_DIR": str(fake),
        "KUBECONFIG": str(tmp_path / "kubeconfig"),
        "FACTORY_BUDGET_FILE": str(budget_file),
        "FACTORY_BUDGET_GATE": gate,
        "HOME": str(tmp_path),
    }
    argv = ["bash", str(_RECONCILE)] + (["--dry-run"] if dry_run else [])
    run = subprocess.run(argv, env=env, capture_output=True, text=True, check=False)
    log_path = fake / "argv.log"
    log = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    return run, [line for line in log if line.startswith("label ")]


def _label(node: str, value: str) -> str:
    return f"label node {node} {_ADMIT}={value} --overwrite"


_BUDGETS = f"# comment\n{_GMK} 6\n{_PE} 12\n"


def test_a_node_below_its_budget_is_admitted_and_one_at_it_is_not(tmp_path: Path) -> None:
    pods = [_sandbox(f"g{i}", node=_GMK) for i in range(6)] + [
        _sandbox(f"p{i}", node=_PE) for i in range(3)
    ]
    run, labels = _run(tmp_path, nodes=[_node(_GMK), _node(_PE)], pods=pods, budgets=_BUDGETS)
    assert run.returncode == 0, run.stderr
    assert sorted(labels) == sorted([_label(_GMK, "false"), _label(_PE, "true")]), run.stdout
    assert f"ADMIT node={_GMK} count=6 budget=6 admit=false" in run.stdout


def test_cleanup_ended_and_unbound_pods_are_not_counted(tmp_path: Path) -> None:
    pods = [_sandbox(f"g{i}", node=_GMK) for i in range(5)] + [
        _sandbox("cleanup", node=_GMK, cleanup=True),
        _sandbox("done", node=_GMK, phase="Succeeded"),
        _sandbox("failed", node=_GMK, phase="Failed"),
        _sandbox("pending-unbound", node=None, phase="Pending"),
    ]
    run, labels = _run(tmp_path, nodes=[_node(_GMK), _node(_PE)], pods=pods, budgets=_BUDGETS)
    assert run.returncode == 0, run.stderr
    assert f"ADMIT node={_GMK} count=5 budget=6 admit=true" in run.stdout
    assert _label(_GMK, "true") in labels


def test_a_bound_pending_pod_counts_because_it_will_hold_cpu(tmp_path: Path) -> None:
    pods = [_sandbox(f"g{i}", node=_GMK) for i in range(5)] + [
        _sandbox("starting", node=_GMK, phase="Pending")
    ]
    run, _ = _run(tmp_path, nodes=[_node(_GMK), _node(_PE)], pods=pods, budgets=_BUDGETS)
    assert f"ADMIT node={_GMK} count=6 budget=6 admit=false" in run.stdout


def test_a_factory_node_with_no_declared_budget_takes_no_sandbox(tmp_path: Path) -> None:
    newcomer = "homelab-worker"
    run, labels = _run(
        tmp_path, nodes=[_node(_GMK), _node(newcomer)], pods=[], budgets=f"{_GMK} 6\n"
    )
    assert run.returncode == 0, run.stderr
    assert _label(newcomer, "false") in labels
    assert _label(_GMK, "true") in labels


def test_a_label_already_correct_is_not_rewritten(tmp_path: Path) -> None:
    run, labels = _run(
        tmp_path,
        nodes=[_node(_GMK, admit="true"), _node(_PE, admit="true")],
        pods=[],
        budgets=_BUDGETS,
    )
    assert run.returncode == 0, run.stderr
    assert labels == []


def test_a_full_fleet_fails_open_on_the_node_with_most_headroom(tmp_path: Path) -> None:
    pods = [_sandbox(f"g{i}", node=_GMK) for i in range(7)] + [
        _sandbox(f"p{i}", node=_PE) for i in range(12)
    ]
    run, labels = _run(
        tmp_path,
        nodes=[_node(_GMK), _node(_PE, alloc="72")],
        pods=pods,
        budgets=_BUDGETS,
    )
    assert run.returncode == 0, run.stderr
    assert "OVERFLOW" in run.stdout
    assert sorted(labels) == sorted([_label(_GMK, "false"), _label(_PE, "true")]), (
        "gmktec is one over and poweredge exactly at budget, so poweredge has the most "
        f"headroom and stays admitted; stdout={run.stdout}"
    )


def test_the_kill_switch_admits_every_factory_node_without_a_budget_file(
    tmp_path: Path,
) -> None:
    pods = [_sandbox(f"g{i}", node=_GMK) for i in range(9)]
    run, labels = _run(
        tmp_path,
        nodes=[_node(_GMK, admit="false"), _node(_PE, admit="false")],
        pods=pods,
        budgets=None,
        gate="off",
    )
    assert run.returncode == 0, run.stderr
    assert sorted(labels) == sorted([_label(_GMK, "true"), _label(_PE, "true")])


def test_a_missing_budget_file_changes_nothing(tmp_path: Path) -> None:
    run, labels = _run(tmp_path, nodes=[_node(_GMK)], pods=[], budgets=None)
    assert run.returncode != 0
    assert "budget file" in run.stderr
    assert labels == []


def test_a_failed_pod_read_changes_nothing(tmp_path: Path) -> None:
    run, labels = _run(tmp_path, nodes=[_node(_GMK)], pods=None, budgets=_BUDGETS)
    assert run.returncode != 0
    assert labels == []


def test_an_unknown_gate_value_changes_nothing(tmp_path: Path) -> None:
    run, labels = _run(tmp_path, nodes=[_node(_GMK)], pods=[], budgets=_BUDGETS, gate="maybe")
    assert run.returncode != 0
    assert labels == []


def test_dry_run_reports_the_decision_and_writes_no_label(tmp_path: Path) -> None:
    run, labels = _run(tmp_path, nodes=[_node(_GMK)], pods=[], budgets=_BUDGETS, dry_run=True)
    assert run.returncode == 0, run.stderr
    assert labels == []
    assert f"would set {_ADMIT}=true on {_GMK}" in run.stdout


def test_ci_pool_wires_the_reconciler_on_the_server_after_the_pressure_reconciler() -> None:
    play = _PLAY.read_text(encoding="utf-8")
    wiring = (
        "    - role: factory_budget_reconciler\n"
        "      tags: [factory_budget_admission]\n"
        "      when: cluster_role == 'server'\n"
    )
    assert wiring in play
    assert play.index("role: factory_pressure_reconciler") < play.index(wiring)


def test_the_committed_unit_keeps_the_gate_on_and_names_the_kill_switch() -> None:
    unit = _SERVICE.read_text(encoding="utf-8")
    assert "Environment=FACTORY_BUDGET_GATE=on\n" in unit
    assert "KILL SWITCH" in unit


def test_the_sandbox_driver_selects_the_admit_label() -> None:
    defaults = _SELECTOR_DEFAULTS.read_text(encoding="utf-8")
    assert f'  {_ADMIT}: "true"\n' in defaults
