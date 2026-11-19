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
import yaml

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
# no Node), `node-fails` a count of `get node` reads that fail first, `pods` one JSON object per
# line ({"ns","name","owner"[,"phase"]}), `flavors` the existing ResourceFlavors. `patch ... -p
# <json>` applies the JSON-patch `replace` ops to `cq`. Nothing reads a local file path: like
# remote-kubectl.sh, only arguments and stdin cross to the cluster.
_STUB_KUBECTL = """#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
case "$1 $2" in
  "get clusterqueue") cat "$s/cq" ;;
  "get resourceflavor") grep -qx "$3" "$s/flavors"; exit $? ;;
  "get node") [ -f "$s/node" ] || exit 1
    n="$(cat "$s/node-fails" 2>/dev/null || echo 0)"
    if [ "$n" -gt 0 ]; then echo $((n - 1)) > "$s/node-fails"; exit 1; fi
    printf '{"status":{"conditions":[{"type":"Ready","status":"%s"}]}}' "$(<"$s/node")" ;;
  "get pods")
    python3 -c '
import json, sys
items = []
for line in open(sys.argv[1]):
    if line.strip():
        p = json.loads(line)
        owners = [{"kind": p["owner"]}] if p["owner"] else []
        items.append({"metadata": {"namespace": p["ns"], "name": p["name"], "ownerReferences": owners},
                      "status": {"phase": p.get("phase", "Running")}})
print(json.dumps({"items": items}))' "$s/pods" ;;
  "patch clusterqueue")
    python3 -c '
import json, sys
q = json.load(open(sys.argv[1]))
for op in json.loads(sys.argv[2]):
    assert op["op"] == "replace"
    node = q
    parts = op["path"].strip("/").split("/")
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    node[int(last) if isinstance(node, list) else last] = op["value"]
json.dump(q, open(sys.argv[1], "w"))' "$s/cq" "$6" ;;
esac
exit 0
"""

_STUB_SCRIPT = """#!/bin/bash
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$STUB_STATE/calls.log"
if [ "$(basename "$0")" = remove-worker.sh ]; then
  [ -z "$REMOVE_FAILS" ] || exit 1
  python3 -c '
import json, sys
for line in open(sys.argv[1]):
    if line.strip():
        p = json.loads(line)
        if p.get("phase", "Running") in ("Running", "Pending") and p["owner"] != "DaemonSet":
            sys.exit(1)' "$STUB_STATE/pods" || exit 1
fi
exit 0
"""

_CQ = {
    "apiVersion": "kueue.x-k8s.io/v1beta1",
    "kind": "ClusterQueue",
    "metadata": {"name": "gates-cq", "resourceVersion": "9", "uid": "u", "generation": 3},
    "spec": {
        "cohort": "orig",
        "resourceGroups": [{"coveredResources": ["cpu"], "flavors": [{"name": "fleet-flavor"}]}],
    },
    "status": {"pendingWorkloads": 0},
}
_FLAVORS = [{"name": "fleet-flavor"}]
_CHANGED = {
    **_CQ,
    "spec": {
        "cohort": "edited-after-snapshot",
        "resourceGroups": [
            {"coveredResources": ["cpu"], "flavors": [{"name": "worker-flavor"}, *_FLAVORS]}
        ],
    },
}


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
            "WINDOW_RETRY_SECONDS": "0",
            "REMOVE_FAILS": remove_fails,
        },
        check=False,
    )


def _calls(env: _Env) -> list[str]:
    return (env.state / "calls.log").read_text(encoding="utf-8").splitlines()


def _snapshot_path(env: _Env) -> Path:
    return env.state / "window" / "gates-cq-before.json"


def _live(env: _Env) -> dict[str, object]:
    return json.loads((env.state / "cq").read_text(encoding="utf-8"))["spec"]  # type: ignore[no-any-return]


def _live_flavors(env: _Env) -> object:
    return _live(env)["resourceGroups"][0]["flavors"]  # type: ignore[index]


def _archives(env: _Env) -> list[Path]:
    return sorted((env.state / "window").glob("gates-cq-before.2*.json"))


def _pods(env: _Env, *pods: dict[str, str]) -> None:
    (env.state / "pods").write_text("".join(json.dumps(p) + "\n" for p in pods), encoding="utf-8")


def _age_snapshot(env: _Env, *, seconds: int) -> None:
    snap = json.loads(_snapshot_path(env).read_text(encoding="utf-8"))
    snap["taken_at_epoch"] -= seconds
    _snapshot_path(env).write_text(json.dumps(snap), encoding="utf-8")


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


def test_drill_and_remove_are_fenced_to_the_node_by_name(env: _Env) -> None:
    assert _run(env=env, action="drill").returncode == 0
    assert _run(env=env, action="remove").returncode == 0
    assert _calls(env) == [
        f"departure-drill.sh {_HOST} --confirm-depart {_NODE}",
        f"remove-worker.sh {_HOST}",
    ]


def test_snapshot_strips_server_metadata_records_its_time_and_is_never_overwritten(
    env: _Env,
) -> None:
    assert _run(env=env, action="snapshot").returncode == 0
    snap = json.loads(_snapshot_path(env).read_text(encoding="utf-8"))
    assert snap["queue"]["spec"] == _CQ["spec"]
    assert "status" not in snap["queue"]
    assert set(snap["queue"]["metadata"]) == {"name"}
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", snap["taken_at"])
    (env.state / "cq").write_text(json.dumps(_CHANGED), encoding="utf-8")
    second = _run(env=env, action="snapshot")
    assert second.returncode != 0
    assert "refusing to replace" in second.stderr
    assert json.loads(_snapshot_path(env).read_text(encoding="utf-8")) == snap


def test_join_is_refused_without_a_snapshot_for_this_window(env: _Env) -> None:
    result = _run(env=env, action="join")
    assert result.returncode != 0
    assert "no before-snapshot" in result.stderr
    assert _calls(env) == []


def test_join_is_refused_on_a_stale_snapshot(env: _Env) -> None:
    assert _run(env=env, action="snapshot").returncode == 0
    _age_snapshot(env, seconds=90000)
    result = _run(env=env, action="join")
    assert result.returncode != 0
    assert "over the 86400 s window limit" in result.stderr
    assert not any(c.startswith("join-worker.sh") for c in _calls(env))


def test_join_with_a_fresh_snapshot_passes_the_inventory_values(env: _Env) -> None:
    assert _run(env=env, action="snapshot").returncode == 0
    assert _run(env=env, action="join").returncode == 0
    assert _calls(env)[-1] == (
        f"join-worker.sh {_HOST} --api-server https://api.example:6443 --server-ca /ca.crt"
    )


def test_revert_cordons_departs_restores_only_the_flavors_and_archives_the_snapshot(
    env: _Env,
) -> None:
    _snapshot_then_change_queue(env)
    result = _run(env=env, action="revert")
    assert result.returncode == 0, result.stdout + result.stderr
    calls = _calls(env)
    cordon = calls.index(f"kubectl cordon {_NODE}")
    assert cordon < calls.index(f"remove-worker.sh {_HOST}")
    assert calls.index(f"remove-worker.sh {_HOST}") < next(
        i for i, c in enumerate(calls) if c.startswith("kubectl patch clusterqueue gates-cq")
    )
    assert _live_flavors(env) == _FLAVORS
    assert _live(env)["cohort"] == "edited-after-snapshot"
    assert not _snapshot_path(env).exists()
    assert len(_archives(env)) == 1
    # The next window can snapshot again; the archived one is never a revert's source.
    assert _run(env=env, action="snapshot").returncode == 0
    assert _snapshot_path(env).exists()


def test_revert_whose_departure_is_refused_leaves_gates_cq_and_the_snapshot_alone(
    env: _Env,
) -> None:
    _snapshot_then_change_queue(env)
    _pods(env, {"ns": "ci", "name": "runner-x", "owner": "", "phase": "Running"})
    result = _run(env=env, action="revert")
    assert result.returncode != 0
    assert "REVERT INCOMPLETE" in result.stdout
    assert "evacuate" in result.stdout
    assert _live_flavors(env) == _CHANGED["spec"]["resourceGroups"][0]["flavors"]  # type: ignore[index]
    assert not any(c.startswith("kubectl patch") for c in _calls(env))
    assert _snapshot_path(env).exists()
    assert _archives(env) == []


def test_revert_after_a_failed_departure_reports_incomplete(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    result = _run(env=env, action="revert", remove_fails="1")
    assert result.returncode != 0
    assert "REVERT INCOMPLETE" in result.stdout
    assert not any(c.startswith("kubectl patch") for c in _calls(env))


def test_revert_refuses_to_restore_a_queue_naming_a_deleted_flavor(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    (env.state / "flavors").write_text("", encoding="utf-8")
    result = _run(env=env, action="revert")
    assert result.returncode != 0
    assert "RESTORE FAILED" in result.stdout
    assert not any(c.startswith("kubectl patch") for c in _calls(env))
    assert _snapshot_path(env).exists()


def test_revert_refuses_to_restore_a_stale_snapshot(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    _age_snapshot(env, seconds=90000)
    result = _run(env=env, action="revert")
    assert result.returncode != 0
    assert "over the 86400 s window limit" in result.stdout
    assert not any(c.startswith("kubectl patch") for c in _calls(env))


def test_revert_without_a_snapshot_still_departs_and_fails_loudly(env: _Env) -> None:
    result = _run(env=env, action="revert")
    assert result.returncode != 0
    assert "no before-snapshot" in result.stdout
    assert f"remove-worker.sh {_HOST}" in _calls(env)


def test_check_ignores_daemonset_pods_and_passes_on_a_ready_node(env: _Env) -> None:
    _pods(env, {"ns": "kube-system", "name": "flannel-x", "owner": "DaemonSet"})
    result = _run(env=env, action="check")
    assert result.returncode == 0, result.stdout
    assert not any("remove-worker" in c for c in _calls(env))
    assert any(f"--field-selector spec.nodeName={_NODE}" in c for c in _calls(env))


@pytest.mark.parametrize("phase", ["Succeeded", "Failed"])
def test_check_does_not_count_completed_pods_as_foreign(env: _Env, phase: str) -> None:
    _pods(env, {"ns": "ci", "name": "done-x", "owner": "Job", "phase": phase})
    result = _run(env=env, action="check")
    assert result.returncode == 0, result.stdout
    assert not any("remove-worker" in c for c in _calls(env))


@pytest.mark.parametrize("owner", ["Job", "ReplicaSet", ""])
def test_check_triggers_on_any_pod_a_daemonset_does_not_own_and_reports_the_blocked_revert(
    env: _Env, owner: str
) -> None:
    _snapshot_then_change_queue(env)
    _pods(
        env,
        {"ns": "kube-system", "name": "flannel-x", "owner": "DaemonSet"},
        {"ns": "ci", "name": "runner-x", "owner": owner},
    )
    result = _run(env=env, action="check")
    assert result.returncode == 3
    assert "ci/runner-x" in result.stdout
    assert "flannel-x" not in result.stdout
    assert "REVERT INCOMPLETE" in result.stdout
    assert f"remove-worker.sh {_HOST}" in _calls(env)
    assert not any(c.startswith("kubectl patch") for c in _calls(env))


def test_check_reverts_and_restores_when_the_node_is_not_ready_within_the_bound(
    env: _Env,
) -> None:
    _snapshot_then_change_queue(env)
    (env.state / "node").write_text("False", encoding="utf-8")
    result = _run(env=env, action="check")
    assert result.returncode == 3
    assert "not Ready within 1s" in result.stdout
    assert f"remove-worker.sh {_HOST}" in _calls(env)
    assert _live_flavors(env) == _FLAVORS


def test_check_reverts_when_the_node_cannot_be_read_within_the_bound(env: _Env) -> None:
    _snapshot_then_change_queue(env)
    (env.state / "node").unlink()
    result = _run(env=env, action="check")
    assert result.returncode == 3
    assert "could not be read" in result.stdout


def test_a_transient_failed_node_read_is_retried_and_does_not_revert(env: _Env) -> None:
    (env.state / "node-fails").write_text("2", encoding="utf-8")
    result = _run(env=env, action="check")
    assert result.returncode == 0, result.stdout
    assert not any("remove-worker" in c for c in _calls(env))
    assert len([c for c in _calls(env) if c.startswith("kubectl get node")]) == 3


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


_ROLE_DEFAULTS = _ROOT / "ansible" / "roles" / "homelab_worker_window" / "defaults" / "main.yml"


def _required_commands() -> list[str]:
    defaults = yaml.safe_load(_ROLE_DEFAULTS.read_text(encoding="utf-8"))
    return list(defaults["homelab_worker_window_required_commands"])


def _command_stubs(tmp_path: Path, *, omit: tuple[str, ...]) -> Path:
    """A directory holding one executable per required command except `omit`.

    Each forwards to the real tool when this host has one, so the stub window.sh can still use
    `cat`; a tool this host lacks (limactl, tailscale) exits 0. The shell builtins (printf) resolve
    without a file, so `omit` never names one.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir(parents=True)
    for name in _required_commands():
        if name in omit:
            continue
        real = shutil.which(name, path="/usr/bin:/bin")
        _exe(
            path=stubs / name,
            body=f'#!/bin/bash\nexec {real} "$@"\n' if real else "#!/bin/bash\nexit 0\n",
        )
    return stubs


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
    omit_commands: tuple[str, ...] = (),
) -> _Play:
    stubs = _command_stubs(tmp_path, omit=omit_commands)
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
        "homelab_worker_window_path": f"{stubs}:/opt/homebrew/bin",
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
    [("join", "", ""), ("join", _M4, ""), ("", _M4, _M4_NODE), ("join", "", _M4_NODE)],
)
def test_the_play_changes_nothing_while_a_fence_is_empty(
    tmp_path: Path, action: str, confirm: str, node_confirm: str
) -> None:
    play = _play(tmp_path, action=action, confirm=confirm, node_confirm=node_confirm)
    assert play.result.returncode == 0, play.result.stdout + play.result.stderr
    assert not play.log.exists()
    assert not play.state.exists()


@pytest.mark.parametrize(
    ("action", "confirm", "node_confirm"),
    [
        ("join", _M4, "other-homelab-worker"),
        ("join", "other", _M4_NODE),
        ("wipe", _M4, _M4_NODE),
    ],
)
def test_the_play_fails_loudly_on_a_confirmation_or_action_naming_something_else(
    tmp_path: Path, action: str, confirm: str, node_confirm: str
) -> None:
    play = _play(tmp_path, action=action, confirm=confirm, node_confirm=node_confirm)
    assert play.result.returncode != 0
    assert "nothing was changed" in play.result.stdout + play.result.stderr
    assert not play.log.exists()
    assert not play.state.exists()


def test_a_confirmed_join_runs_window_sh_with_the_inventory_path_route_and_join_values(
    tmp_path: Path,
) -> None:
    play = _play(tmp_path, action="join", confirm=_M4, node_confirm=_M4_NODE)
    assert play.result.returncode == 0, play.result.stdout + play.result.stderr
    out = play.log.read_text(encoding="utf-8")
    assert f"argv join {_M4}" in out
    assert f"PATH={play.state}/bin:{tmp_path / 'stubs'}:/opt/homebrew/bin" in out
    assert "RKT=u@api.example" in out
    assert "API=https://api.example:6443" in out
    assert f"NODE={_M4_NODE}" in out
    assert "CA=PEM-BODY" in out
    assert (play.state / "bin" / "kubectl").is_symlink()


def test_the_committed_inventory_puts_the_m4s_user_local_homebrew_first_on_the_path() -> None:
    result = run_under_hang_guard(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-inventory",
            "-i",
            str(_ROOT / "ansible" / "inventory" / "legacy.yml"),
            "--host",
            _M4,
        ],
        capture_output=True,
        text=True,
        env={
            key: value
            for key, value in os.environ.items()
            if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
        },
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    entries = json.loads(result.stdout)["homelab_worker_window_path"].split(":")
    assert entries.index("/Users/cwoolley/homebrew/bin") < entries.index("/opt/homebrew/bin")
    assert "/Users/cwoolley/.local/bin" in entries


def test_preflight_passes_when_every_command_resolves_and_does_nothing_else(
    tmp_path: Path,
) -> None:
    play = _play(tmp_path, action="preflight", confirm=_M4, node_confirm=_M4_NODE)
    assert play.result.returncode == 0, play.result.stdout + play.result.stderr
    assert "MISSING" not in play.result.stdout
    for name in _required_commands():
        assert f"OK      {name}" in play.result.stdout
    assert not play.log.exists()
    assert not play.state.exists()


def test_preflight_names_every_missing_command_in_one_failure(tmp_path: Path) -> None:
    play = _play(
        tmp_path,
        action="preflight",
        confirm=_M4,
        node_confirm=_M4_NODE,
        omit_commands=("limactl", "tailscale"),
    )
    assert play.result.returncode != 0
    output = play.result.stdout + play.result.stderr
    assert "limactl, tailscale" in output
    assert "MISSING limactl" in output
    assert "MISSING tailscale" in output
    assert not play.state.exists()


def test_preflight_runs_before_a_write_action_and_stops_it(tmp_path: Path) -> None:
    play = _play(
        tmp_path,
        action="join",
        confirm=_M4,
        node_confirm=_M4_NODE,
        omit_commands=("limactl",),
    )
    assert play.result.returncode != 0
    assert "MISSING limactl" in play.result.stdout + play.result.stderr
    assert not play.log.exists()
    assert not play.state.exists()


def test_preflight_is_a_no_op_without_both_fences(tmp_path: Path) -> None:
    for confirm, node_confirm in ((_M4, ""), ("", _M4_NODE), ("", "")):
        play = _play(
            tmp_path / (confirm or "x") / (node_confirm or "y"),
            action="preflight",
            confirm=confirm,
            node_confirm=node_confirm,
            omit_commands=("limactl",),
        )
        assert play.result.returncode == 0, play.result.stdout + play.result.stderr
        assert "MISSING" not in play.result.stdout
        assert not play.state.exists()


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
