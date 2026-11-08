"""The worker container step of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

The start task pipes `homelab-worker/vm/converge-worker-container.sh` into `sudo bash -s` inside
the worker VM. These run it under the system `/bin/bash` against a stub `docker` that keeps one
container's image, run state and tailscaled state in files, and assert:

- the container is the systemd-in-container worker on a digest-pinned image, with its state on the
  data disk and no enrollment material in an argument or environment variable;
- a rerun keeps a running container, starts a stopped one and replaces one on another image;
- a worker that needs its tailnet login prints the URL and waits for it, joining untagged as the
  derived name, and the tailnet IPv4 becomes the node IP;
- a worker on the tailnet always accepts the K3s nodes' advertised /32 routes (research 007);
- the kubelet starts only once enrollment has been delivered;
- the fixture's first stage puts the worker on a Docker network with no tailnet login;
- the CI work-volume storage and the fleet container hooks are data-disk binds, and a running
  worker without them is replaced with its state kept.
"""

from __future__ import annotations

import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

# Integration tier: each test runs the real script under /bin/bash against stub executables
# and mocked config, so the script's whole control flow is exercised.
pytestmark = pytest.mark.integration

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "homelab-worker" / "vm" / "converge-worker-container.sh"
)
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"
_IMAGE = "registry.test/worker@sha256:" + "a" * 64
_LAN_IP = "10.99.0.21"
_RUNNING = '{\n  "BackendState": "Running",\n  "AuthURL": ""\n}\n'
_NEEDS_LOGIN = (
    '{\n  "BackendState": "NeedsLogin",\n  "AuthURL": "https://login.tailscale.com/a/abc123"\n}\n'
)

# Every container path the worker binds from the VM, as a current worker reports them; the
# stub reports each with its read-write flag.
_DESTINATIONS = (
    "/lib/modules",
    "/var/lib/containerd",
    "/var/lib/kubelet",
    "/var/lib/tailscale",
    "/etc/homelab-worker",
    "/var/lib/rancher/k3s/storage",
    "/usr/local/lib/ci-runner-k3s/hooks",
    "/sys/kernel/security",
    "/etc/otel-collector",
    "/usr/local/lib/ci-runner-k3s/bin",
    "/srv/factory-workspaces",
)

_STUB_DOCKER = """#!/bin/bash
s="$STUB_STATE"
printf 'docker %s\\n' "$*" >> "$s/calls.log"
case "$1" in
  inspect)
    [ -f "$s/container" ] || exit 1
    case "$3" in
      *NetworkSettings*) cat "$s/network-ip" ;;
      *'"/etc/homelab-worker"'*) cat "$s/mount" ;;
      *Mounts*) cat "$s/destinations" ;;
      *) cat "$s/container" ;;
    esac ;;
  run)
    : > "$s/destinations"
    prev=""
    for a in "$@"; do
      case "$a" in *:/etc/homelab-worker) echo "${a%:/etc/homelab-worker}" > "$s/mount" ;; esac
      if [ "$prev" = --volume ]; then
        d="${a#*:}"; rw=true
        case "$d" in *:ro) rw=false ;; esac
        echo "${d%%:*} $rw" >> "$s/destinations"
      fi
      prev="$a"
      last="$a"
    done
    echo "$last true" > "$s/container" ;;
  rm) rm -f "$s/container" ;;
  start) sed -i.bak 's/ false$/ true/' "$s/container" ;;
  exec)
    shift
    [ "$1" = "--detach" ] && shift
    [ "$1" = "-i" ] && shift
    shift
    case "$*" in
      "sh -c mkdir -p /etc/systemd/system/system.slice.d && cat >/etc/systemd/system/system.slice.d/50-cpu-weight.conf") cat > "$s/system-slice-drop-in" ;;
      "systemctl daemon-reload") printf 'daemon-reload\\n' >> "$s/container-reloads" ;;
      "cat /etc/systemd/system/system.slice.d/50-cpu-weight.conf") cat "$s/system-slice-drop-in" 2>/dev/null || exit 1 ;;
      "tailscale status --json") cat "$s/ts-status" ;;
      "tailscale ip -4") echo "100.101.102.103" ;;
      "tailscale up "*) if [ -f "$s/ts-after-up" ]; then cp "$s/ts-after-up" "$s/ts-status"; fi ;;
      "tailscale set "*) printf '%s\\n' "$*" >> "$s/ts-set.log" ;;
      "systemctl start kubelet") : ;;
      "stat -c %d /var/lib/tailscale") cat "$s/ctr-dev" ;;
      "ip -4 -o addr show dev cni0") cat "$s/cni0" 2>/dev/null ;;
      "systemctl restart otel-collector") printf 'restart otel-collector\\n' >> "$s/collector.log" ;;
      *) exit 2 ;;
    esac ;;
  restart) : ;;
  update) : ;;
esac
"""

# stat -c %d <path> on the VM side reports the data disk's device number.
_STUB_STAT = """#!/bin/bash
cat "$STUB_STATE/host-dev"
"""


# modprobe "loads" br_netfilter by creating the bridge sysctl the kernel would expose.
_STUB_MODPROBE = """#!/bin/bash
printf 'modprobe %s\\n' "$*" >> "$STUB_STATE/calls.log"
[ "${STUB_MODPROBE_FAILS:-0}" = 1 ] && exit 1
[ "$1" = br_netfilter ] && mkdir -p "$STUB_STATE/proc-bridge" && touch "$STUB_STATE/proc-bridge/bridge-nf-call-iptables"
exit 0
"""

# findmnt -n -o TARGET -T <path> answers with the stub's data-disk mountpoint.
_STUB_FINDMNT = """#!/bin/bash
printf 'findmnt %s\\n' "$*" >> "$STUB_STATE/calls.log"
cat "$STUB_STATE/mount-target"
"""

_STUB_SYSTEMCTL = """#!/bin/bash
printf 'systemctl %s\\n' "$*" >> "$STUB_STATE/calls.log"
"""

_STUB_IP = """#!/bin/bash
printf 'ip %s\\n' "$*" >> "$STUB_STATE/calls.log"
cat "$STUB_STATE/ip-addrs" 2>/dev/null
"""


_READ_ONLY = frozenset(
    {"/lib/modules", "/usr/local/lib/ci-runner-k3s/hooks", "/usr/local/lib/ci-runner-k3s/bin"}
)


def _mounts(destinations: tuple[str, ...], *, read_only: frozenset[str] = _READ_ONLY) -> str:
    return "".join(f"{d} {str(d not in read_only).lower()}\n" for d in destinations)


@dataclass(frozen=True, kw_only=True)
class _Vm:
    state: Path
    bin_dir: Path
    root: Path


@pytest.fixture
def vm(tmp_path: Path) -> _Vm:
    state = tmp_path / "stub"
    state.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(_STUB_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    for name, body in (
        ("ip", _STUB_IP),
        ("systemctl", _STUB_SYSTEMCTL),
        ("modprobe", _STUB_MODPROBE),
        ("findmnt", _STUB_FINDMNT),
        ("stat", _STUB_STAT),
    ):
        exe = bin_dir / name
        exe.write_text(body, encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    (state / "calls.log").write_text("", encoding="utf-8")
    (state / "ts-status").write_text(_RUNNING, encoding="utf-8")
    (state / "mount-target").write_text("/mnt/test-data\n", encoding="utf-8")
    (state / "host-dev").write_text("2049\n", encoding="utf-8")
    (state / "ctr-dev").write_text("2049\n", encoding="utf-8")
    (state / "destinations").write_text(_mounts(_DESTINATIONS), encoding="utf-8")
    return _Vm(state=state, bin_dir=bin_dir, root=tmp_path / "hwdata" / "worker")


def _run(*, vm: _Vm, extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), _WORKER, _HOST, _IMAGE, str(vm.root), *extra],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{vm.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(vm.state),
            "SYSTEMD_UNIT_DIR": str(vm.state / "systemd"),
            "MODULES_LOAD_DIR": str(vm.state / "modules-load.d"),
            "BRIDGE_NF_SYSCTL": str(vm.state / "proc-bridge" / "bridge-nf-call-iptables"),
            "TAILNET_LOGIN_TIMEOUT": "1",
            "POLL_SECONDS": "1",
        },
        check=False,
        timeout=60,
    )


def _calls(*, vm: _Vm, verb: str) -> list[str]:
    lines = (vm.state / "calls.log").read_text(encoding="utf-8").splitlines()
    return [c for c in lines if c.startswith(f"docker {verb} ")]


def _enroll(*, vm: _Vm) -> None:
    (vm.root / "enrollment" / "bootstrap-kubeconfig").write_text("x\n", encoding="utf-8")
    (vm.root / "enrollment" / "client-ca.crt").write_text("x\n", encoding="utf-8")


def test_a_new_worker_runs_systemd_in_a_container_with_its_state_on_the_data_disk(vm: _Vm) -> None:
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    [run] = _calls(vm=vm, verb="run")
    for flag in (
        f"--name {_WORKER} --hostname {_WORKER}",
        "--privileged --cgroupns=private",
        "--tmpfs /run ",
        "--tmpfs /tmp ",
        "--device /dev/net/tun",
        "--volume /lib/modules:/lib/modules:ro",
        f"--volume {vm.root}/containerd:/var/lib/containerd",
        f"--volume {vm.root}/kubelet:/var/lib/kubelet:rshared",
        f"--volume {vm.root}/tailscale:/var/lib/tailscale",
        f"--volume {vm.root}/enrollment:/etc/homelab-worker",
        "--stop-signal SIGRTMIN+3",
    ):
        assert flag in run
    assert run.endswith(f" {_IMAGE}")
    assert [e for e in run.split("--env ")[1:] if not e.startswith("container=docker")] == []
    assert stat.S_IMODE((vm.root / "enrollment").stat().st_mode) == 0o700


def test_an_image_not_pinned_by_digest_is_refused_before_any_container_change(
    vm: _Vm, tmp_path: Path
) -> None:
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), _WORKER, _HOST, "ghcr.io/x/y:latest", str(tmp_path)],
        capture_output=True,
        text=True,
        env={"PATH": f"{vm.bin_dir}:/usr/bin:/bin", "STUB_STATE": str(vm.state)},
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert "is not pinned by digest" in result.stderr
    assert (vm.state / "calls.log").read_text(encoding="utf-8") == ""


@pytest.mark.parametrize(
    ("existing", "verb", "message"),
    [
        (f"{_IMAGE} true", None, "already running"),
        (f"{_IMAGE} false", "start", "starting existing container"),
        (
            "ghcr.io/thewoolleyman/livespec-worker-node@sha256:" + "b" * 64 + " true",
            "rm",
            "replacing",
        ),
    ],
)
def test_a_rerun_reconciles_the_existing_container(
    vm: _Vm, existing: str, verb: str | None, message: str
) -> None:
    (vm.state / "container").write_text(f"{existing}\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert message in result.stdout
    if verb is None:
        assert _calls(vm=vm, verb="run") == []
        assert _calls(vm=vm, verb="rm") == []
    else:
        assert len(_calls(vm=vm, verb=verb)) == 1
    assert (vm.state / "container").read_text(encoding="utf-8") == f"{_IMAGE} true\n"


def test_a_worker_needing_its_login_prints_the_url_and_joins_untagged_by_its_name(
    vm: _Vm,
) -> None:
    (vm.state / "ts-status").write_text(_NEEDS_LOGIN, encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode != 0
    assert (
        "approve the worker's tailnet login: https://login.tailscale.com/a/abc123" in result.stdout
    )
    assert "run the start task again" in result.stderr
    [up] = [c for c in _calls(vm=vm, verb="exec") if "tailscale up" in c]
    assert up == f"docker exec --detach {_WORKER} tailscale up --hostname={_WORKER}"
    assert not (vm.root / "enrollment" / "kubelet.env").exists()


def test_an_approved_login_makes_the_tailnet_address_the_node_ip(vm: _Vm) -> None:
    (vm.state / "ts-status").write_text(_NEEDS_LOGIN, encoding="utf-8")
    (vm.state / "ts-after-up").write_text(_RUNNING, encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (vm.root / "enrollment" / "kubelet.env").read_text(encoding="utf-8") == (
        f"NODE_NAME={_WORKER}\nNODE_IP=100.101.102.103\nWORKER_HOST={_HOST}\n"
    )
    config = (vm.root / "enrollment" / "kubelet-config.yaml").read_text(encoding="utf-8")
    for line in (
        "cgroupDriver: systemd",
        "readOnlyPort: 0",
        "serverTLSBootstrap: true",
        "    clientCAFile: /etc/homelab-worker/client-ca.crt",
    ):
        assert line in config.splitlines()
    lines = config.splitlines()
    dns = lines[lines.index("clusterDNS:") + 1]
    assert re.fullmatch(r"  - \d+\.\d+\.\d+\.\d+", dns)
    assert any(re.fullmatch(r"maxPods: \d+", line) for line in lines)


def test_the_kubelet_starts_only_once_enrollment_is_delivered(vm: _Vm) -> None:
    first = _run(vm=vm)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "awaits enrollment" in first.stdout
    assert [c for c in _calls(vm=vm, verb="exec") if "kubelet" in c] == []
    _enroll(vm=vm)
    second = _run(vm=vm)
    assert second.returncode == 0, second.stdout + second.stderr
    assert [c for c in _calls(vm=vm, verb="exec") if "kubelet" in c] == [
        f"docker exec {_WORKER} systemctl start kubelet"
    ]


def test_the_fixture_stage_joins_a_docker_network_without_a_tailnet_login(vm: _Vm) -> None:
    (vm.state / "network-ip").write_text("172.18.0.4\n", encoding="utf-8")
    (vm.state / "ts-status").write_text(_NEEDS_LOGIN, encoding="utf-8")
    result = _run(vm=vm, extra=("k3d-hw-fixture",))
    assert result.returncode == 0, result.stdout + result.stderr
    [run] = _calls(vm=vm, verb="run")
    assert "--network k3d-hw-fixture" in run
    assert [c for c in _calls(vm=vm, verb="exec") if "tailscale" in c] == []
    assert "NODE_IP=172.18.0.4\n" in (vm.root / "enrollment" / "kubelet.env").read_text(
        encoding="utf-8"
    )


def test_the_worker_explicitly_refuses_tailnet_route_acceptance(vm: _Vm) -> None:
    # A saved preference (RouteAll: true from an earlier enrollment) survives `tailscale up`
    # without the flag, so converge turns route acceptance off explicitly on every run.
    (vm.state / "ip-addrs").write_text(
        f"2: lima0    inet {_LAN_IP}/24 brd 10.99.0.255 scope global lima0\n", encoding="utf-8"
    )
    for extra in ((), (f"host:{_LAN_IP}",)):
        (vm.state / "ts-set.log").unlink(missing_ok=True)
        result = _run(vm=vm, extra=extra)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (vm.state / "ts-set.log").read_text(encoding="utf-8").splitlines() == [
            "tailscale set --accept-routes=false"
        ]
    calls = (vm.state / "calls.log").read_text(encoding="utf-8")
    assert "--accept-routes=true" not in calls


def test_lan_mode_runs_on_the_host_network_with_the_declared_address_as_node_ip(vm: _Vm) -> None:
    (vm.state / "ip-addrs").write_text(
        f"2: lima0    inet {_LAN_IP}/24 brd 10.99.0.255 scope global lima0\n", encoding="utf-8"
    )
    result = _run(vm=vm, extra=(f"host:{_LAN_IP}",))
    assert result.returncode == 0, result.stdout + result.stderr
    [run] = _calls(vm=vm, verb="run")
    assert "--network host" in run
    assert (vm.root / "enrollment" / "kubelet.env").read_text(encoding="utf-8") == (
        f"NODE_NAME={_WORKER}\nNODE_IP={_LAN_IP}\nWORKER_HOST={_HOST}\n"
    )


def test_lan_mode_refuses_a_vm_not_carrying_the_declared_address(vm: _Vm) -> None:
    (vm.state / "ip-addrs").write_text(
        "2: lima0    inet 10.99.0.77/24 brd 10.99.0.255 scope global lima0\n", encoding="utf-8"
    )
    result = _run(vm=vm, extra=(f"host:{_LAN_IP}",))
    assert result.returncode != 0
    assert _LAN_IP in result.stderr
    assert "10.99.0.77" in result.stderr
    assert _calls(vm=vm, verb="run") == []
    assert not (vm.root / "enrollment" / "kubelet.env").exists()


def test_a_container_of_another_state_root_is_refused_never_adopted(vm: _Vm) -> None:
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    other = vm.root.parent / "fixture-worker" / "enrollment"
    (vm.state / "mount").write_text(f"{other}\n", encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode != 0
    assert f"keeps its enrollment at '{other}'" in result.stderr
    for verb in ("run", "rm", "start", "exec"):
        assert _calls(vm=vm, verb=verb) == []


def test_the_worker_starts_at_boot_only_after_its_data_disk_is_mounted(vm: _Vm) -> None:
    # Lima mounts the data disk in cloud-final.service, after multi-user.target, so gating
    # docker.service on it deadlocks boot (measured on macbook-m4-max, 2026-11-06). A unit
    # ordered after cloud-final, pulled in by cloud-init.target, waits for the mountpoint and
    # starts only the worker; Docker itself no longer races to restart it.
    stale = vm.state / "systemd" / "docker.service.d" / "10-homelab-worker-state.conf"
    stale.parent.mkdir(parents=True)
    stale.write_text("[Service]\nExecStartPre=/bin/true\n", encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not stale.exists()
    unit = (vm.state / "systemd" / "homelab-worker-container.service").read_text(encoding="utf-8")
    lines = unit.splitlines()
    assert "After=cloud-final.service docker.service" in lines
    assert "Requires=docker.service" in lines
    assert "WantedBy=cloud-init.target" in lines
    [wait] = [line for line in lines if line.startswith("ExecStartPre=")]
    assert "mountpoint -q /mnt/test-data" in wait
    # systemd is the worker's only supervisor: Docker restoring it at daemon start raced the
    # data-disk mount even with --restart on-failure (macbook-m4-max, 2026-11-06).
    assert "Type=simple" in lines
    assert f"ExecStart=/usr/bin/docker start -a {_WORKER}" in lines
    assert f"ExecStop=/usr/bin/docker stop {_WORKER}" in lines
    assert "Restart=on-failure" in lines
    calls = (vm.state / "calls.log").read_text(encoding="utf-8").splitlines()
    assert "systemctl daemon-reload" in calls
    assert "systemctl enable homelab-worker-container.service" in calls


def test_docker_never_restarts_the_worker_itself(vm: _Vm) -> None:
    assert _run(vm=vm).returncode == 0
    [run] = _calls(vm=vm, verb="run")
    assert "--restart no" in run


def test_an_existing_worker_is_moved_to_the_no_restart_policy(vm: _Vm) -> None:
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    assert _run(vm=vm).returncode == 0
    assert _calls(vm=vm, verb="update") == [f"docker update --restart no {_WORKER}"]


def test_an_unchanged_worker_unit_is_not_reloaded(vm: _Vm) -> None:
    assert _run(vm=vm).returncode == 0
    (vm.state / "calls.log").write_text("", encoding="utf-8")
    assert _run(vm=vm).returncode == 0
    assert "systemctl daemon-reload" not in (vm.state / "calls.log").read_text(encoding="utf-8")


def test_br_netfilter_is_loaded_and_persisted_before_the_worker_starts(vm: _Vm) -> None:
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    [conf] = list((vm.state / "modules-load.d").glob("*.conf"))
    assert "br_netfilter" in conf.read_text(encoding="utf-8").splitlines()
    calls = (vm.state / "calls.log").read_text(encoding="utf-8").splitlines()
    assert calls.index("modprobe br_netfilter") < min(
        i for i, c in enumerate(calls) if c.startswith("docker run ")
    )


def test_a_kernel_without_bridge_netfilter_is_refused_before_any_container_change(
    vm: _Vm,
) -> None:
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), _WORKER, _HOST, _IMAGE, str(vm.root)],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{vm.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(vm.state),
            "STUB_MODPROBE_FAILS": "1",
            "SYSTEMD_UNIT_DIR": str(vm.state / "systemd"),
            "MODULES_LOAD_DIR": str(vm.state / "modules-load.d"),
            "BRIDGE_NF_SYSCTL": str(vm.state / "proc-bridge" / "bridge-nf-call-iptables"),
            "TAILNET_LOGIN_TIMEOUT": "1",
            "POLL_SECONDS": "1",
        },
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert "br_netfilter" in result.stderr
    assert _calls(vm=vm, verb="run") == []


def test_a_state_root_on_the_root_filesystem_is_refused_before_any_container_change(
    vm: _Vm,
) -> None:
    (vm.state / "mount-target").write_text("/\n", encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode != 0
    assert "data disk" in result.stderr
    assert _calls(vm=vm, verb="run") == []


def test_a_running_worker_whose_state_is_on_the_data_disk_is_kept(vm: _Vm) -> None:
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _calls(vm=vm, verb="restart") == []


def test_a_running_worker_bound_to_the_root_disk_is_restarted_before_any_tailnet_step(
    vm: _Vm,
) -> None:
    # A boot race can start the worker before the data disk mounts, binding empty root-disk
    # directories: its tailnet identity looks lost, and a login would mint a duplicate device.
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    (vm.state / "ctr-dev").write_text("64769\n", encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = (vm.state / "calls.log").read_text(encoding="utf-8").splitlines()
    restarts = [i for i, c in enumerate(calls) if c.startswith("docker restart ")]
    assert len(restarts) == 1
    tailnet = [i for i, c in enumerate(calls) if " tailscale " in c]
    assert tailnet
    assert restarts[0] < min(tailnet)


def test_the_ci_storage_and_container_hooks_are_bound_from_the_data_disk(vm: _Vm) -> None:
    # The local-path work volumes and the fleet container hook are node paths: on the worker
    # they resolve inside the container, so both must be data-disk binds (research 009).
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    [run] = _calls(vm=vm, verb="run")
    assert f"--volume {vm.root}/ci/storage:/var/lib/rancher/k3s/storage " in run
    assert f"--volume {vm.root}/ci/hooks:/usr/local/lib/ci-runner-k3s/hooks:ro " in run
    assert (vm.root / "ci" / "storage").is_dir()
    assert (vm.root / "ci" / "hooks").is_dir()


def test_a_running_worker_without_the_ci_binds_is_replaced_keeping_its_state(vm: _Vm) -> None:
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    (vm.state / "destinations").write_text(_mounts(_DESTINATIONS[:5]), encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "replacing" in result.stdout
    assert len(_calls(vm=vm, verb="rm")) == 1
    [run] = _calls(vm=vm, verb="run")
    assert ":/var/lib/rancher/k3s/storage " in run


def test_the_kubelet_sees_the_vms_apparmor_through_a_securityfs_bind(vm: _Vm) -> None:
    # The kubelet runs in the container and refuses an AppArmor-confined pod unless it can see
    # securityfs, which Docker does not mount into a container; once it is visible, containerd
    # loads its default profile through it, so the bind is writable (measured 2026-11-06: a
    # read-only bind failed every container start with exit 226).
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    [run] = _calls(vm=vm, verb="run")
    assert "--volume /sys/kernel/security:/sys/kernel/security " in run
    assert "/sys/kernel/security:ro" not in run


def test_a_running_worker_without_the_securityfs_bind_is_replaced(vm: _Vm) -> None:
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    (vm.state / "destinations").write_text(
        _mounts(tuple(d for d in _DESTINATIONS if d != "/sys/kernel/security")), encoding="utf-8"
    )
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_calls(vm=vm, verb="rm")) == 1
    [run] = _calls(vm=vm, verb="run")
    assert ":/sys/kernel/security " in run


def test_a_running_worker_with_a_read_only_securityfs_bind_is_replaced(vm: _Vm) -> None:
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    (vm.state / "destinations").write_text(
        _mounts(_DESTINATIONS, read_only=_READ_ONLY | {"/sys/kernel/security"}), encoding="utf-8"
    )
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_calls(vm=vm, verb="rm")) == 1


def _deliver_telemetry(*, vm: _Vm, key: bool = True) -> None:
    telemetry = vm.root / "telemetry"
    telemetry.mkdir(parents=True, exist_ok=True)
    (telemetry / "config.yaml").write_text("# mocked collector configuration\n", encoding="utf-8")
    if key:
        (telemetry / ".env").write_text("HONEYCOMB_INGEST_KEY_LIVESPEC=x\n", encoding="utf-8")


def test_the_host_collector_reads_its_state_from_the_data_disk(vm: _Vm) -> None:
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    [run] = _calls(vm=vm, verb="run")
    assert f"--volume {vm.root}/telemetry:/etc/otel-collector " in run
    assert stat.S_IMODE((vm.root / "telemetry").stat().st_mode) == 0o700


def test_a_delivered_collector_gets_its_node_values_and_is_restarted(vm: _Vm) -> None:
    _deliver_telemetry(vm=vm)
    (vm.state / "cni0").write_text(
        "5: cni0    inet 10.99.7.1/24 brd 10.99.7.255 scope global cni0\n", encoding="utf-8"
    )
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    node_env = (vm.root / "telemetry" / "node.env").read_text(encoding="utf-8")
    assert node_env == f"WORKER_NODE_NAME={_WORKER}\nOTLP_PODS_ENDPOINT=10.99.7.1:4319\n"
    assert (vm.state / "collector.log").read_text(encoding="utf-8") == "restart otel-collector\n"


@pytest.mark.parametrize(("key", "bridge"), [(False, True), (True, False)])
def test_the_collector_stays_off_without_its_key_or_the_bridge(
    vm: _Vm, *, key: bool, bridge: bool
) -> None:
    _deliver_telemetry(vm=vm, key=key)
    if bridge:
        (vm.state / "cni0").write_text(
            "5: cni0    inet 10.99.7.1/24 brd 10.99.7.255 scope global cni0\n", encoding="utf-8"
        )
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (vm.state / "collector.log").exists()
    assert not (vm.root / "telemetry" / "node.env").exists()
    assert "collector" in result.stdout


def test_the_pool_binaries_are_bound_read_only_from_the_data_disk(vm: _Vm) -> None:
    # A workflow pod mounts this node path idmapped (hostUsers: false); the container's overlayfs
    # root cannot take an idmapped mount, the data disk's XFS can (measured 2026-11-06).
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    [run] = _calls(vm=vm, verb="run")
    assert f"--volume {vm.root}/ci/bin:/usr/local/lib/ci-runner-k3s/bin:ro " in run
    assert (vm.root / "ci" / "bin").is_dir()


def test_a_running_worker_without_the_pool_binaries_bind_is_replaced(vm: _Vm) -> None:
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    (vm.state / "destinations").write_text(
        _mounts(tuple(d for d in _DESTINATIONS if d != "/usr/local/lib/ci-runner-k3s/bin")),
        encoding="utf-8",
    )
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_calls(vm=vm, verb="rm")) == 1


def test_the_factory_workspace_root_is_bound_from_the_data_disk(vm: _Vm) -> None:
    # The factory sandbox backend keeps each sandbox's workspace under one node path; on the
    # worker that path resolves inside the container, so it must be a data-disk bind.
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    [run] = _calls(vm=vm, verb="run")
    assert f"--volume {vm.root}/factory/workspaces:/srv/factory-workspaces " in run
    assert (vm.root / "factory" / "workspaces").is_dir()


def test_a_running_worker_without_the_factory_workspace_bind_is_replaced(vm: _Vm) -> None:
    (vm.state / "container").write_text(f"{_IMAGE} true\n", encoding="utf-8")
    (vm.state / "mount").write_text(f"{vm.root}/enrollment\n", encoding="utf-8")
    (vm.state / "destinations").write_text(
        _mounts(tuple(d for d in _DESTINATIONS if d != "/srv/factory-workspaces")),
        encoding="utf-8",
    )
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_calls(vm=vm, verb="rm")) == 1


def test_the_worker_gives_its_node_agents_the_fleet_system_slice_cpu_weight(vm: _Vm) -> None:
    assert _run(vm=vm).returncode == 0
    (vm.state / "system-slice-drop-in").unlink()
    _enroll(vm=vm)
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    drop_in = (vm.state / "system-slice-drop-in").read_text(encoding="utf-8")
    assert drop_in.splitlines() == ["[Slice]", "CPUWeight=1000"]
    calls = _calls(vm=vm, verb="exec")
    reload_at = calls.index(f"docker exec {_WORKER} systemctl daemon-reload")
    assert reload_at < calls.index(f"docker exec {_WORKER} systemctl start kubelet")


def test_a_current_system_slice_weight_is_not_rewritten_or_reloaded(vm: _Vm) -> None:
    assert _run(vm=vm).returncode == 0
    (vm.state / "calls.log").write_text("", encoding="utf-8")
    assert _run(vm=vm).returncode == 0
    assert [
        c for c in _calls(vm=vm, verb="exec") if "daemon-reload" in c or "50-cpu-weight.conf'" in c
    ] == []
