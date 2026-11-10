"""The gate placement publisher, and the wiring that lets the reconciler cover every pool node.

Work item livespec-dev-tooling-gvo7fa. `publish-gate-lane-readings.sh` runs for real
against a faked `kubectl`; the reconciler's decisions are covered at the consumer
tier (`tests/consumer/test_gate_lane_placement_scenarios.py`).
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, cast

import yaml

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO / "ci-runner" / "k3s" / "phase2"
_DIR = _PHASE2 / "gate-placement"
_PUBLISH = _DIR / "publish-gate-lane-readings.sh"
_RECONCILE = _DIR / "reconcile-gate-lane-order.sh"
_PLAY = _REPO / "ansible" / "ci-pool.yml"
_NOW = 1_800_000_000
_NODE = "poweredge-xubuntu"

_FAKE_KUBECTL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
case "$1" in
  patch)
    if [ -f "$FAKE_DIR/reject-once" ]; then
      rm -f "$FAKE_DIR/reject-once"
      echo 'error: You must be logged in to the server (Unauthorized)' >&2
      exit 1
    fi
    if [ -f "$FAKE_DIR/reject-always" ]; then
      echo 'error: You must be logged in to the server (Unauthorized)' >&2
      exit 1
    fi
    if [ -f "$FAKE_DIR/fail" ]; then echo 'connection refused' >&2; exit 1; fi
    printf '%s' "$7" >"$FAKE_DIR/patch.json" ;;
  *) echo "fake kubectl: unexpected argv: $*" >&2; exit 1 ;;
esac
"""


def _stat(*, idle: int, busy: int) -> str:
    """A /proc/stat whose cpu line is `busy` ticks busy and `idle` ticks idle."""
    return f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\ncpu0 1 2 3 4 5 6 7 8 9 10\nintr 1\n"


class _Host:
    def __init__(self, tmp_path: Path, *, role: str = "agent") -> None:
        self.tmp = tmp_path
        self.fake = tmp_path / "fake"
        self.fake.mkdir()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        kubectl = bin_dir / "kubectl"
        _ = kubectl.write_text(_FAKE_KUBECTL, encoding="utf-8")
        kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
        kubeconfig = tmp_path / "kubeconfig"
        _ = kubeconfig.write_text("apiVersion: v1\n", encoding="utf-8")
        self.profile = tmp_path / "profile.env"
        _ = self.profile.write_text(
            f"NODE_NAME={_NODE}\nCLUSTER_ROLE={role}\nCHURN_KUBECONFIG_FILE={kubeconfig}\n",
            encoding="utf-8",
        )
        self.stat_file = tmp_path / "stat"
        self.slice_file = tmp_path / "cpu.pressure"
        self.env = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_DIR": str(self.fake),
            "KUBECONFIG": str(kubeconfig),
            "GATE_LANE_STAT_FILE": str(self.stat_file),
            "GATE_LANE_SLICE_PRESSURE_FILE": str(self.slice_file),
            "GATE_LANE_STATE_DIR": str(tmp_path / "state"),
            "NODE_STATUS_REFRESH_BIN": str(tmp_path / "no-refresh"),
            "HOME": str(tmp_path),
        }

    def sample(
        self, *, now: int, idle: int, busy: int, pressure: float | None = 3.5
    ) -> subprocess.CompletedProcess[str]:
        _ = self.stat_file.write_text(_stat(idle=idle, busy=busy), encoding="utf-8")
        if pressure is not None:
            _ = self.slice_file.write_text(
                f"some avg10=1.00 avg60={pressure} avg300=2.00 total=1\n"
                "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
                encoding="utf-8",
            )
        env = {**self.env, "GATE_LANE_NOW": str(now)}
        return subprocess.run(
            ["bash", str(_PUBLISH), str(self.profile)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def message(self) -> str:
        patch = json.loads((self.fake / "patch.json").read_text(encoding="utf-8"))
        condition = patch["status"]["conditions"][0]
        assert condition["type"] == "LivespecGateLaneCPU"
        return str(condition["message"])


def test_the_first_sample_publishes_idle_as_unreadable_never_zero(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    run = host.sample(now=_NOW, idle=1000, busy=1000)
    assert run.returncode == 0, run.stderr
    assert host.message() == "cpu.idle60=unreadable ci.slice.some.avg60=3.5"
    assert "cpu.idle60 unreadable: no usable /proc/stat sample" in run.stderr
    argv = (host.fake / "argv.log").read_text(encoding="utf-8")
    assert f"patch node {_NODE} --subresource=status --type=strategic -p" in argv


def test_idle_is_the_share_over_the_last_sixty_seconds(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    assert host.sample(now=_NOW, idle=1000, busy=1000).returncode == 0
    run = host.sample(now=_NOW + 60, idle=1000 + 60, busy=1000 + 940, pressure=41.25)
    assert run.returncode == 0, run.stderr
    assert host.message() == "cpu.idle60=6.0 ci.slice.some.avg60=41.25"
    assert run.stderr == ""


def test_the_window_uses_the_newest_sample_at_least_fifty_five_seconds_old(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    assert host.sample(now=_NOW, idle=0, busy=0).returncode == 0
    assert host.sample(now=_NOW + 30, idle=3000, busy=0).returncode == 0
    assert host.sample(now=_NOW + 60, idle=3000, busy=1000).returncode == 0
    # baseline = the sample at NOW+0 (60 s old); the NOW+30 one is too young.
    assert host.message() == "cpu.idle60=75.0 ci.slice.some.avg60=3.5"


def test_samples_older_than_the_window_are_not_a_baseline(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    assert host.sample(now=_NOW, idle=0, busy=0).returncode == 0
    run = host.sample(now=_NOW + 400, idle=100, busy=100)
    assert run.returncode == 0, run.stderr
    assert host.message().startswith("cpu.idle60=unreadable ")


def test_a_counter_that_did_not_advance_is_unreadable(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    assert host.sample(now=_NOW, idle=500, busy=500).returncode == 0
    run = host.sample(now=_NOW + 60, idle=500, busy=500)
    assert run.returncode == 0, run.stderr
    assert host.message().startswith("cpu.idle60=unreadable ")


def test_an_unreadable_slice_pressure_is_published_as_unreadable_with_its_cause(
    tmp_path: Path,
) -> None:
    host = _Host(tmp_path)
    assert host.sample(now=_NOW, idle=0, busy=0, pressure=None).returncode == 0
    run = host.sample(now=_NOW + 60, idle=100, busy=100, pressure=None)
    assert run.returncode == 0, run.stderr
    assert host.message() == "cpu.idle60=50.0 ci.slice.some.avg60=unreadable"
    assert "ci.slice.some.avg60 unreadable: " in run.stderr
    assert "is not readable" in run.stderr


def test_a_slice_pressure_file_without_a_some_avg60_field_is_unreadable(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    _ = host.slice_file.write_text("full avg10=0.00\n", encoding="utf-8")
    _ = host.stat_file.write_text(_stat(idle=1, busy=1), encoding="utf-8")
    run = subprocess.run(
        ["bash", str(_PUBLISH), str(host.profile)],
        env={**host.env, "GATE_LANE_NOW": str(_NOW)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert host.message().endswith("ci.slice.some.avg60=unreadable")
    assert "no usable 'some avg60' field" in run.stderr


def test_a_stat_file_without_a_cpu_line_leaves_idle_unreadable(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    _ = host.stat_file.write_text("intr 1\n", encoding="utf-8")
    _ = host.slice_file.write_text("some avg60=2.0\n", encoding="utf-8")
    run = subprocess.run(
        ["bash", str(_PUBLISH), str(host.profile)],
        env={**host.env, "GATE_LANE_NOW": str(_NOW)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert host.message() == "cpu.idle60=unreadable ci.slice.some.avg60=2.0"
    assert "is not readable or has no cpu line" in run.stderr


def test_the_heartbeat_names_the_sample_time(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    assert host.sample(now=_NOW, idle=1, busy=1).returncode == 0
    patch = json.loads((host.fake / "patch.json").read_text(encoding="utf-8"))
    assert patch["status"]["conditions"][0]["lastHeartbeatTime"] == "2027-01-15T08:00:00Z"


def test_a_rejected_credential_without_a_refresh_tool_fails_loudly(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    _ = (host.fake / "reject-once").write_text("", encoding="utf-8")
    run = host.sample(now=_NOW, idle=1, busy=1)
    assert run.returncode == 1
    assert "no refresh tool is executable" in run.stderr


def test_a_rejected_credential_is_refreshed_once_and_the_publish_retried(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    refresh = tmp_path / "refresh"
    _ = refresh.write_text(f"#!/bin/sh\necho refreshed >>{tmp_path}/refreshed\n", encoding="utf-8")
    refresh.chmod(refresh.stat().st_mode | stat.S_IEXEC)
    host.env["NODE_STATUS_REFRESH_BIN"] = str(refresh)
    _ = (host.fake / "reject-once").write_text("", encoding="utf-8")
    run = host.sample(now=_NOW, idle=1, busy=1)
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "refreshed").read_text(encoding="utf-8") == "refreshed\n"


def test_a_credential_rejected_again_after_the_refresh_fails(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    refresh = tmp_path / "refresh"
    _ = refresh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    refresh.chmod(refresh.stat().st_mode | stat.S_IEXEC)
    host.env["NODE_STATUS_REFRESH_BIN"] = str(refresh)
    _ = (host.fake / "reject-always").write_text("", encoding="utf-8")
    run = host.sample(now=_NOW, idle=1, busy=1)
    assert run.returncode == 1
    assert "failed again after one credential refresh" in run.stderr


def test_a_failed_refresh_is_reported(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    refresh = tmp_path / "refresh"
    _ = refresh.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
    refresh.chmod(refresh.stat().st_mode | stat.S_IEXEC)
    host.env["NODE_STATUS_REFRESH_BIN"] = str(refresh)
    _ = (host.fake / "reject-once").write_text("", encoding="utf-8")
    run = host.sample(now=_NOW, idle=1, busy=1)
    assert run.returncode == 1
    assert "refresh FAILED" in run.stderr


def test_a_server_never_refreshes_a_rejected_admin_kubeconfig(tmp_path: Path) -> None:
    host = _Host(tmp_path, role="server")
    _ = (host.fake / "reject-once").write_text("", encoding="utf-8")
    run = host.sample(now=_NOW, idle=1, busy=1)
    assert run.returncode == 1
    assert "REJECTED the admin kubeconfig" in run.stderr


def test_another_publish_failure_is_not_retried(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    _ = (host.fake / "fail").write_text("", encoding="utf-8")
    run = host.sample(now=_NOW, idle=1, busy=1)
    assert run.returncode == 1
    assert "publishing LivespecGateLaneCPU on poweredge-xubuntu failed" in run.stderr


def test_a_bad_profile_is_refused(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    _ = host.profile.write_text("NODE_NAME=\nCLUSTER_ROLE=agent\n", encoding="utf-8")
    run = host.sample(now=_NOW, idle=1, busy=1)
    assert run.returncode == 1
    assert "NODE_NAME is empty" in run.stderr
    _ = host.profile.write_text("NODE_NAME=x\nCLUSTER_ROLE=laptop\n", encoding="utf-8")
    assert "CLUSTER_ROLE must be" in host.sample(now=_NOW, idle=1, busy=1).stderr
    missing = subprocess.run(
        ["bash", str(_PUBLISH), str(tmp_path / "absent.env")],
        env=host.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "profile not found" in missing.stderr


def test_an_agent_profile_without_a_credential_is_refused(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    _ = host.profile.write_text(f"NODE_NAME={_NODE}\nCLUSTER_ROLE=agent\n", encoding="utf-8")
    env = {k: v for k, v in host.env.items() if k != "KUBECONFIG"}
    run = subprocess.run(
        ["bash", str(_PUBLISH), str(host.profile)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 1
    assert "CHURN_KUBECONFIG_FILE is empty" in run.stderr


def test_a_server_profile_defaults_to_the_admin_kubeconfig(tmp_path: Path) -> None:
    host = _Host(tmp_path, role="server")
    env = {k: v for k, v in host.env.items() if k != "KUBECONFIG"}
    run = subprocess.run(
        ["bash", str(_PUBLISH), str(host.profile)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 1
    assert "/etc/rancher/k3s/k3s.yaml not found" in run.stderr


def test_a_missing_kubeconfig_is_refused(tmp_path: Path) -> None:
    host = _Host(tmp_path)
    host.env["KUBECONFIG"] = str(tmp_path / "gone")
    run = host.sample(now=_NOW, idle=1, busy=1)
    assert run.returncode == 1
    assert "not found" in run.stderr


def test_the_reconciler_static_order_parser_agrees_with_the_committed_queue(
    tmp_path: Path,
) -> None:
    """The reconciler's line parse of cluster-queue-gates.yaml equals a real YAML parse."""
    documents = list(
        yaml.safe_load_all(
            (_PHASE2 / "kueue" / "cluster-queue-gates.yaml").read_text(encoding="utf-8")
        )
    )
    queue = next(d for d in documents if d.get("kind") == "ClusterQueue")
    expected = [f["name"] for f in queue["spec"]["resourceGroups"][0]["flavors"]]
    scratch = _scratch_cluster(tmp_path, expected)
    run = subprocess.run(
        ["bash", str(_RECONCILE), "--dry-run"],
        env=scratch,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    # Every lane free and live in the committed order: nothing to change.
    assert "none-saturated:static-order" in run.stdout
    assert f"desired={','.join(expected)}" in run.stdout


def _scratch_cluster(tmp_path: Path, flavors: list[str]) -> dict[str, str]:
    fake = tmp_path / "fake"
    fake.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    _ = kubectl.write_text(
        "#!/usr/bin/env bash\n"
        'case "$2" in\n'
        '  nodes) cat "$FAKE_DIR/nodes.json" ;;\n'
        '  clusterqueue) cat "$FAKE_DIR/cq.json" ;;\n'
        '  resourceflavors) cat "$FAKE_DIR/flavors.json" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
    nodes = []
    resource_flavors = []
    for flavor in flavors:
        host = f"host-{flavor}"
        nodes.append(
            {
                "metadata": {
                    "name": host,
                    "labels": {"kubernetes.io/hostname": host, "kubernetes.io/arch": "amd64"},
                },
                "status": {
                    "conditions": [
                        {
                            "type": "LivespecGateLaneCPU",
                            "message": "cpu.idle60=50 ci.slice.some.avg60=1",
                            "lastHeartbeatTime": "2027-01-15T08:00:00Z",
                        }
                    ]
                },
            }
        )
        resource_flavors.append(
            {
                "metadata": {"name": flavor},
                "spec": {"nodeLabels": {"kubernetes.io/hostname": host}},
            }
        )
    queue = {
        "metadata": {"resourceVersion": "1"},
        "spec": {
            "resourceGroups": [
                {
                    "coveredResources": ["cpu", "memory"],
                    "flavors": [{"name": n, "resources": []} for n in flavors],
                }
            ]
        },
    }
    for name, document in (
        ("nodes.json", {"items": nodes}),
        ("cq.json", queue),
        ("flavors.json", {"items": resource_flavors}),
    ):
        _ = (fake / name).write_text(json.dumps(document), encoding="utf-8")
    return {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_DIR": str(fake),
        "KUBECONFIG": str(tmp_path / "kubeconfig"),
        "GATE_LANE_NOW": str(_NOW),
        "GATE_LANE_STATIC_QUEUE_FILE": str(_PHASE2 / "kueue" / "cluster-queue-gates.yaml"),
        "GATE_LANE_ARCH_CONF": str(_PHASE2 / "workload-arch.conf"),
        "HOME": str(tmp_path),
    }


def _play_roles() -> list[dict[str, Any]]:
    plays = cast(list[dict[str, Any]], yaml.safe_load(_PLAY.read_text(encoding="utf-8")))
    return [
        cast(dict[str, Any], role)
        for play in plays
        for role in cast(list[Any], play.get("roles", []))
        if isinstance(role, dict)
    ]


def test_the_publisher_role_runs_on_every_pool_node_and_the_reconciler_on_the_server() -> None:
    roles = {cast(str, r["role"]): r for r in _play_roles() if "role" in r}
    publisher = roles["gate_placement_publisher"]
    reconciler = roles["gate_placement_reconciler"]
    assert "when" not in publisher, "a node that joins ci_pool must publish with no gate edit"
    assert reconciler["when"] == "cluster_role == 'server'"
    for role in (publisher, reconciler):
        assert role["tags"] == ["gate_placement"]
    names = [cast(str, r["role"]) for r in _play_roles() if "role" in r]
    assert names.index("node_status_credential") < names.index("gate_placement_publisher")


def test_the_roles_install_the_scripts_and_units_the_directory_ships() -> None:
    shipped = {p.name for p in _DIR.iterdir()}
    for role, files in (
        (
            "gate_placement_publisher",
            [
                "publish-gate-lane-readings.sh",
                "publish-gate-lane-readings.service",
                "publish-gate-lane-readings.timer",
            ],
        ),
        (
            "gate_placement_reconciler",
            [
                "reconcile-gate-lane-order.sh",
                "reconcile-gate-lane-order.service",
                "reconcile-gate-lane-order.timer",
            ],
        ),
    ):
        defaults = (_REPO / "ansible" / "roles" / role / "defaults" / "main.yml").read_text(
            encoding="utf-8"
        )
        for name in files:
            assert name in shipped
            assert name in defaults


def test_the_reconciler_never_names_a_node_the_pool_could_outgrow() -> None:
    """No hostname is written into the reconciler: lanes come from the live queue."""
    inventory = cast(
        dict[str, Any],
        yaml.safe_load(
            (_REPO / "ansible" / "inventory" / "legacy.yml").read_text(encoding="utf-8")
        ),
    )
    pool = cast(dict[str, Any], inventory["all"]["children"]["legacy"]["children"]["ci_pool"])
    text = _RECONCILE.read_text(encoding="utf-8")
    for host in cast(dict[str, Any], pool["hosts"]):
        assert host not in text


def test_the_reconciler_does_not_touch_the_factory_admit_label_or_a_runner_request() -> None:
    text = "\n".join(
        re.sub(r"(?m)^\s*#.*$", "", p.read_text(encoding="utf-8")) for p in (_RECONCILE, _PUBLISH)
    )
    assert "factory-admit" not in text
    assert "resources.requests" not in text
    assert "PriorityClass" not in text
