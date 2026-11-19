"""The M4 window route (livespec-dev-tooling-nn4yxt): `homelab-worker/window.sh` and its play.

`window.sh` runs on the worker's Mac and wraps remove-worker.sh, join-worker.sh and
departure-drill.sh. These run it under the system `/bin/bash` against a stub `kubectl` that keeps
gates-cq, the node and its pods as files, and stub worker scripts that log their argv, and assert
the fence, the inventory-derived join arguments, the snapshot and its restore, and the
revert trigger's DaemonSet exclusion. A last group RUNS `ansible/homelab-worker-window.yml`
through the pinned ansible-core against a local one-host inventory whose window.sh is a logging
stand-in, and asserts the play's fence, PATH, kubectl route and join values.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.hang_guard import run_under_hang_guard

__all__: list[str] = []

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "homelab-worker" / "window.sh"
_HOST = "alpha"
_NODE = f"{_HOST}-homelab-worker"
_M4 = "macbook-m4-max"
_M4_NODE = f"{_M4}-homelab-worker"

# State files under $STUB_STATE: `cq` is gates-cq's JSON, `node` the Node's Ready status (absent =
# no Node), `pods` one JSON object per line ({"ns","name","owner"}), `flavors` the existing
# ResourceFlavors. `replace -f <file>` copies the file over `cq`.
_STUB_KUBECTL = """#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
case "$1 $2" in
  "get clusterqueue") cat "$s/cq" ;;
  "get resourceflavor") grep -qx "$3" "$s/flavors"; exit $? ;;
  "get node") [ -f "$s/node" ] || exit 1
    printf '{"status":{"conditions":[{"type":"Ready","status":"%s"}]}}' "$(<"$s/node")" ;;
  "get pods")
    python3 -c '
import json, sys
items = []
for line in open(sys.argv[1]):
    if line.strip():
        p = json.loads(line)
        owners = [{"kind": p["owner"]}] if p["owner"] else []
        items.append({"metadata": {"namespace": p["ns"], "name": p["name"], "ownerReferences": owners}})
print(json.dumps({"items": items}))' "$s/pods" ;;
  "replace -f") cp "$3" "$s/cq" ;;
esac
exit 0
"""

_STUB_SCRIPT = """#!/bin/bash
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$STUB_STATE/calls.log"
[ "$(basename "$0")" != remove-worker.sh ] || [ -z "$REMOVE_FAILS" ] || exit 1
exit 0
"""

_CQ = {
    "apiVersion": "kueue.x-k8s.io/v1beta1",
    "kind": "ClusterQueue",
    "metadata": {"name": "gates-cq", "resourceVersion": "9", "uid": "u", "generation": 3},
    "spec": {
        "resourceGroups": [{"coveredResources": ["cpu"], "flavors": [{"name": "fleet-flavor"}]}]
    },
    "status": {"pendingWorkloads": 0},
}
_CHANGED = {**_CQ, "spec": {"resourceGroups": []}}


@dataclass(frozen=True, kw_only=True)
class _Env:
    state: Path
    bin_dir: Path
    scripts: Path


def _exe(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _python3() -> str:
    found = shutil.which("python3")
    assert found
    return found


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    state = tmp_path / "stub"
    (state / "hosts").mkdir(parents=True)
    (state / "hosts" / f"{_HOST}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    (state / "calls.log").write_text("", encoding="utf-8")
    (state / "cq").write_text(json.dumps(_CQ), encoding="utf-8")
    (state / "node").write_text("True", encoding="utf-8")
    (state / "pods").write_text("", encoding="utf-8")
    (state / "flavors").write_text("fleet-flavor\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(path=bin_dir / "kubectl", body=_STUB_KUBECTL)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("remove-worker.sh", "join-worker.sh", "departure-drill.sh"):
        _exe(path=scripts / name, body=_STUB_SCRIPT)
    return _Env(state=state, bin_dir=bin_dir, scripts=scripts)


def _run(
    *, env: _Env, action: str, host: str = _HOST, confirm: str = _NODE, remove_fails: str = ""
) -> subprocess.CompletedProcess[str]:
    return run_under_hang_guard(
        ["/bin/bash", str(_SCRIPT), action, host],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{env.bin_dir}:/usr/bin:/bin:{Path(_python3()).parent}",
            "STUB_STATE": str(env.state),
            "HOMELAB_WORKER_HOSTS_DIR": str(env.state / "hosts"),
            "WINDOW_SCRIPTS_DIR": str(env.scripts),
            "WINDOW_NODE_CONFIRM": confirm,
            "WINDOW_STATE_DIR": str(env.state / "window"),
            "WINDOW_API_SERVER": "https://api.example:6443",
            "WINDOW_SERVER_CA": "/ca.crt",
            "WINDOW_BOUND_SECONDS": "1",
            "WINDOW_POLL_SECONDS": "1",
            "REMOVE_FAILS": remove_fails,
        },
        check=False,
    )


def _calls(env: _Env) -> list[str]:
    return (env.state / "calls.log").read_text(encoding="utf-8").splitlines()


def _snapshot_path(env: _Env) -> Path:
    return env.state / "window" / "gates-cq-before.json"


def _live_spec(env: _Env) -> object:
    return json.loads((env.state / "cq").read_text(encoding="utf-8"))["spec"]


def _snapshot_then_change_queue(env: _Env) -> None:
    assert _run(env=env, action="snapshot").returncode == 0
    (env.state / "cq").write_text(json.dumps(_CHANGED), encoding="utf-8")


@pytest.mark.parametrize("action", ["snapshot", "join", "drill", "remove", "check", "revert"])
def test_every_action_refuses_a_node_confirm_that_is_not_the_workers_name(
    env: _Env, action: str
) -> None:
    for wrong in ("", "other-homelab-worker", _HOST):
        result = _run(env=env, action=action, confirm=wrong)
        assert result.returncode != 0
        assert "nothing was changed" in result.stderr
    assert _calls(env) == []


def test_an_undeclared_host_is_refused(env: _Env) -> None:
    result = _run(env=env, action="remove", host="zulu", confirm="zulu-homelab-worker")
    assert result.returncode != 0
    assert "not declared" in result.stderr
    assert _calls(env) == []


def test_join_passes_the_inventory_values_and_nothing_else(env: _Env) -> None:
    assert _run(env=env, action="join").returncode == 0
    assert _calls(env) == [
        f"join-worker.sh {_HOST} --api-server https://api.example:6443 --server-ca /ca.crt"
    ]


def test_drill_and_remove_are_fenced_to_the_node_by_name(env: _Env) -> None:
    assert _run(env=env, action="drill").returncode == 0
    assert _run(env=env, action="remove").returncode == 0
    assert _calls(env) == [
        f"departure-drill.sh {_HOST} --confirm-depart {_NODE}",
        f"remove-worker.sh {_HOST}",
    ]


def test_snapshot_strips_server_metadata_and_is_never_overwritten(env: _Env) -> None:
    assert _run(env=env, action="snapshot").returncode == 0
    snap = json.loads(_snapshot_path(env).read_text(encoding="utf-8"))
    assert snap["spec"] == _CQ["spec"]
    assert "status" not in snap
    assert set(snap["metadata"]) == {"name"}
    (env.state / "cq").write_text(json.dumps(_CHANGED), encoding="utf-8")
    second = _run(env=env, action="snapshot")
    assert second.returncode != 0
    assert "refusing to replace" in second.stderr
    assert json.loads(_snapshot_path(env).read_text(encoding="utf-8"))["spec"] == _CQ["spec"]


def test_revert_cordons_departs_and_restores_gates_cq_to_the_snapshot(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    result = _run(env=env, action="revert")
    assert result.returncode == 0, result.stdout + result.stderr
    calls = _calls(env)
    assert (
        calls.index(f"kubectl cordon {_NODE}")
        < calls.index(f"remove-worker.sh {_HOST}")
        < calls.index(f"kubectl replace -f {_snapshot_path(env)}")
    )
    assert _live_spec(env) == _CQ["spec"]


def test_revert_restores_even_when_the_departure_fails_and_reports_it(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    result = _run(env=env, action="revert", remove_fails="1")
    assert result.returncode != 0
    assert "departure of" in result.stdout
    assert _live_spec(env) == _CQ["spec"]


def test_revert_refuses_to_restore_a_queue_naming_a_deleted_flavor(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    (env.state / "flavors").write_text("", encoding="utf-8")
    result = _run(env=env, action="revert")
    assert result.returncode != 0
    assert "RESTORE FAILED" in result.stdout
    assert not any(c.startswith("kubectl replace") for c in _calls(env))


def test_revert_without_a_snapshot_still_departs_and_fails_loudly(env: _Env) -> None:
    result = _run(env=env, action="revert")
    assert result.returncode != 0
    assert "no before-snapshot" in result.stdout
    assert f"remove-worker.sh {_HOST}" in _calls(env)


def test_check_ignores_daemonset_pods_and_passes_on_a_ready_node(env: _Env) -> None:
    (env.state / "pods").write_text(
        json.dumps({"ns": "kube-system", "name": "flannel-x", "owner": "DaemonSet"}) + "\n",
        encoding="utf-8",
    )
    result = _run(env=env, action="check")
    assert result.returncode == 0, result.stdout
    assert not any("remove-worker" in c for c in _calls(env))
    assert any(f"--field-selector spec.nodeName={_NODE}" in c for c in _calls(env))


@pytest.mark.parametrize("owner", ["Job", "ReplicaSet", ""])
def test_check_reverts_on_any_pod_a_daemonset_does_not_own(env: _Env, owner: str) -> None:
    _snapshot_then_change_queue(env)
    (env.state / "pods").write_text(
        json.dumps({"ns": "kube-system", "name": "flannel-x", "owner": "DaemonSet"})
        + "\n"
        + json.dumps({"ns": "ci", "name": "runner-x", "owner": owner})
        + "\n",
        encoding="utf-8",
    )
    result = _run(env=env, action="check")
    assert result.returncode == 3
    assert "ci/runner-x" in result.stdout
    assert "flannel-x" not in result.stdout
    assert f"remove-worker.sh {_HOST}" in _calls(env)
    assert _live_spec(env) == _CQ["spec"]


def test_check_reverts_when_the_node_is_not_ready_within_the_bound(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    (env.state / "node").write_text("False", encoding="utf-8")
    result = _run(env=env, action="check")
    assert result.returncode == 3
    assert "not Ready within 1s" in result.stdout
    assert f"remove-worker.sh {_HOST}" in _calls(env)
    assert _live_spec(env) == _CQ["spec"]


def test_check_reverts_when_the_node_is_absent(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    (env.state / "node").unlink()
    assert _run(env=env, action="check").returncode == 3


# --- the play, run through the pinned ansible-core --------------------------------------------


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        (_ROOT / "justfile").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe
    pin = re.search(r"ansible-core==[0-9][0-9A-Za-z.]*", recipe["body"])
    assert pin
    return pin[0]


@dataclass(frozen=True, kw_only=True)
class _Play:
    result: subprocess.CompletedProcess[str]
    log: Path
    state: Path


def _play(
    tmp_path: Path,
    *,
    action: str,
    confirm: str,
    node_confirm: str,
    extra_vars: dict[str, str] | None = None,
) -> _Play:
    release = tmp_path / "release"
    state = tmp_path / "state"
    (release / "homelab-worker").mkdir(parents=True)
    log = tmp_path / "window.log"
    _exe(
        path=release / "homelab-worker" / "window.sh",
        body=(
            "#!/bin/bash\n"
            '{ echo "argv $*"; echo "PATH=$PATH"; echo "RKT=$REMOTE_KUBECTL_TARGET";\n'
            ' echo "KUBECONFIG=$KUBECONFIG"; echo "API=$WINDOW_API_SERVER";\n'
            ' echo "NODE=$WINDOW_NODE_CONFIRM"; echo "CA=$(cat "$WINDOW_SERVER_CA" 2>/dev/null)"; }'
            f" >> {log}\n"
        ),
    )
    _exe(path=release / "homelab-worker" / "remote-kubectl.sh", body="#!/bin/bash\n")
    values = {
        "homelab_worker_window_release_dir": str(release),
        "homelab_worker_window_state_dir": str(state),
        "homelab_worker_window_remote_kubectl_target": "u@api.example",
        "homelab_worker_window_api_server": "https://api.example:6443",
        "homelab_worker_window_server_ca_pem": "PEM-BODY",
        **(extra_vars or {}),
    }
    lines = "\n".join(f"          {k}: {json.dumps(v)}" for k, v in values.items())
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(
        f"all:\n  children:\n    homelab_workers:\n      hosts:\n        {_M4}:\n"
        f"          ansible_connection: local\n          ansible_python_interpreter: {_python3()}\n"
        f"{lines}\n",
        encoding="utf-8",
    )
    result = run_under_hang_guard(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(inventory),
            str(_ROOT / "ansible" / "homelab-worker-window.yml"),
            "-e",
            f"homelab_worker_window_action={action}",
            "-e",
            f"homelab_worker_window_confirm={confirm}",
            "-e",
            f"homelab_worker_window_node_confirm={node_confirm}",
        ],
        capture_output=True,
        text=True,
        env={
            **{
                key: value
                for key, value in os.environ.items()
                if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
            },
            "ANSIBLE_ROLES_PATH": str(_ROOT / "ansible" / "roles"),
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp"),
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
        },
        check=False,
    )
    return _Play(result=result, log=log, state=state)


@pytest.mark.parametrize(
    ("action", "confirm", "node_confirm"),
    [
        ("join", "", ""),
        ("join", _M4, ""),
        ("join", _M4, "other-homelab-worker"),
        ("join", "other", _M4_NODE),
        ("", _M4, _M4_NODE),
        ("wipe", _M4, _M4_NODE),
    ],
)
def test_the_play_changes_nothing_unless_both_fences_name_their_target(
    tmp_path: Path, action: str, confirm: str, node_confirm: str
) -> None:
    play = _play(tmp_path, action=action, confirm=confirm, node_confirm=node_confirm)
    assert play.result.returncode == 0, play.result.stdout + play.result.stderr
    assert not play.log.exists()
    assert not play.state.exists()


def test_a_confirmed_join_runs_window_sh_with_the_inventory_path_route_and_join_values(
    tmp_path: Path,
) -> None:
    play = _play(tmp_path, action="join", confirm=_M4, node_confirm=_M4_NODE)
    assert play.result.returncode == 0, play.result.stdout + play.result.stderr
    out = play.log.read_text(encoding="utf-8")
    assert f"argv join {_M4}" in out
    assert f"PATH={play.state}/bin:/opt/homebrew/bin:" in out
    assert "RKT=u@api.example" in out
    assert "API=https://api.example:6443" in out
    assert f"NODE={_M4_NODE}" in out
    assert "CA=PEM-BODY" in out
    assert (play.state / "bin" / "kubectl").is_symlink()


def test_a_kubeconfig_in_inventory_replaces_the_remote_kubectl_shim(tmp_path: Path) -> None:
    play = _play(
        tmp_path,
        action="check",
        confirm=_M4,
        node_confirm=_M4_NODE,
        extra_vars={
            "homelab_worker_window_kubeconfig": "/k/config",
            "homelab_worker_window_remote_kubectl_target": "",
        },
    )
    assert play.result.returncode == 0, play.result.stdout + play.result.stderr
    out = play.log.read_text(encoding="utf-8")
    assert "KUBECONFIG=/k/config" in out
    assert f"{play.state}/bin" not in out
    assert not (play.state / "bin" / "kubectl").exists()


def test_a_window_with_no_kubectl_route_is_refused_before_any_command(tmp_path: Path) -> None:
    play = _play(
        tmp_path,
        action="snapshot",
        confirm=_M4,
        node_confirm=_M4_NODE,
        extra_vars={"homelab_worker_window_remote_kubectl_target": ""},
    )
    assert play.result.returncode != 0
    assert not play.log.exists()


def test_committed_inventory_supplies_the_route_and_the_api_server() -> None:
    text = (_ROOT / "ansible" / "inventory" / "group_vars" / "homelab_workers.yml").read_text(
        encoding="utf-8"
    )
    assert (
        "homelab_worker_window_remote_kubectl_target: cwoolley@poweredge-xubuntu.perch-rudd.ts.net"
        in text
    )
    assert (
        "homelab_worker_window_api_server: https://poweredge-xubuntu.perch-rudd.ts.net:6443" in text
    )
