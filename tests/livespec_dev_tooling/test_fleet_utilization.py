"""Fixture-driven checks for the coordinator's read-only fleet-utilization script."""

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
_UTILIZATION = _REPO_ROOT / "scripts" / "coordinator" / "fleet-utilization.sh"
_HP = "hp-xubuntu"
_POWEREDGE = "poweredge-xubuntu"

_FAKE_SSH = r"""#!/usr/bin/env bash
set -euo pipefail
while [[ "$1" == "-o" ]]; do shift 2; done
target="$1"
remote="$2"
case "$remote" in
  *"kubectl get nodes -o json") cat "$FLEET_FIXTURES/nodes.json" ;;
  *"kubectl get resourcequota -n factory -o json") cat "$FLEET_FIXTURES/quotas.json" ;;
  *"kubectl get clusterqueues.kueue.x-k8s.io -o json") cat "$FLEET_FIXTURES/queues.json" ;;
  *"kubectl get resourceflavors.kueue.x-k8s.io -o json") cat "$FLEET_FIXTURES/flavors.json" ;;
  *"kubectl get autoscalingrunnersets.actions.github.com -n arc-runners -o json") printf '%s' '{"items": []}' ;;
  *"kubectl get ephemeralrunners.actions.github.com -n arc-runners --request-timeout=20s -o json") printf '%s' '{"items": []}' ;;
  *"kubectl get localqueues.kueue.x-k8s.io -n arc-runners -o json") printf '%s' '{"items": []}' ;;
  "sh -s")
    case "$target" in
      hp-xubuntu) idle=20 ;;
      poweredge-xubuntu) idle=75 ;;
      *) echo "unexpected fake ssh target: $target" >&2; exit 1 ;;
    esac
    printf 'nproc=8\nload=0.1 0.1 0.1\npsi=some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nidle=%s\nmemavail_kb=1048576\nswaptotal_kb=0\nswapfree_kb=0\n' "$idle"
    ;;
  *) echo "unexpected fake ssh command: $remote" >&2; exit 1 ;;
esac
"""


def _node(name: str) -> _Json:
    return {
        "metadata": {
            "name": name,
            "labels": {
                "kubernetes.io/hostname": name,
                "ci-runner.io/factory": "true",
                "ci-runner.io/factory-admit": "true",
            },
        },
        "spec": {"taints": []},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }


def _write_json(path: Path, document: _Json) -> None:
    _ = path.write_text(json.dumps(document), encoding="utf-8")


def _stranded_capacity_read(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    fixtures = tmp_path / "fixtures"
    bin_dir = tmp_path / "bin"
    fixtures.mkdir()
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    _ = ssh.write_text(_FAKE_SSH, encoding="utf-8")
    ssh.chmod(ssh.stat().st_mode | stat.S_IXUSR)
    _write_json(fixtures / "nodes.json", {"items": [_node(_HP), _node(_POWEREDGE)]})
    _write_json(fixtures / "quotas.json", {"items": []})
    _write_json(
        fixtures / "queues.json",
        {
            "items": [
                {
                    "metadata": {"name": "gates-repro-cq"},
                    "spec": {
                        "resourceGroups": [
                            {
                                "flavors": [
                                    {
                                        "name": "repro-hp",
                                        "resources": [{"name": "cpu", "nominalQuota": "1"}],
                                    },
                                    {
                                        "name": "repro-poweredge",
                                        "resources": [{"name": "cpu", "nominalQuota": "0"}],
                                    },
                                ]
                            }
                        ]
                    },
                    "status": {
                        "pendingWorkloads": 1,
                        "flavorsUsage": [
                            {"name": "repro-hp", "resources": [{"name": "cpu", "total": "0"}]},
                            {
                                "name": "repro-poweredge",
                                "resources": [{"name": "cpu", "total": "0"}],
                            },
                        ],
                    },
                }
            ]
        },
    )
    _write_json(
        fixtures / "flavors.json",
        {
            "items": [
                {
                    "metadata": {"name": "repro-hp"},
                    "spec": {"nodeLabels": {"kubernetes.io/hostname": _HP}},
                },
                {
                    "metadata": {"name": "repro-poweredge"},
                    "spec": {"nodeLabels": {"kubernetes.io/hostname": _POWEREDGE}},
                },
            ]
        },
    )
    return subprocess.run(
        ["bash", str(_UTILIZATION), "--stranded-only"],
        capture_output=True,
        check=False,
        env=os.environ
        | {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FLEET_FIXTURES": str(fixtures),
            "HOME": str(tmp_path),
        },
        text=True,
        timeout=120,
    )


def test_a_pending_clusterqueue_limited_to_one_node_flags_an_idle_peer(tmp_path: Path) -> None:
    """A zero-quota peer cannot hide a pending ClusterQueue's stranded capacity."""
    result = _stranded_capacity_read(tmp_path)
    assert result.returncode == 0, result.stderr
    flagged = [line for line in result.stdout.splitlines() if line.strip().startswith("FLAGGED")]
    assert any(
        "gates-repro-cq" in line and _HP in line and _POWEREDGE in line for line in flagged
    ), result.stdout
